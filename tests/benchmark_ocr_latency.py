"""EXP-OCR-LATENCY-001: OCR wall-time and text-identity benchmark.

Runs the production OCR function (`extract_text_with_ocr`) on every certificate in a
directory, records wall time per document and a SHA-256 of the OCR text, and stores
the raw text so two runs (baseline vs candidate) can be compared byte-for-byte.

Identical OCR text means Gemini and the offline extractor receive identical input,
so extraction accuracy cannot change; only latency is being evaluated.

Usage (run inside the worker image so CPU quota and libraries match production):
    python -m tests.benchmark_ocr_latency run --certs-dir /data/certs --label baseline
    python -m tests.benchmark_ocr_latency compare --a baseline --b candidate

Outputs go to tests/benchmark_runs/ocr_latency/<label>/ (gitignored: raw OCR text is private).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))

from app.config import settings
from app.services.field_extractor import extract_certificate_fields
from app.services.ocr_fallback import _load_rapidocr, extract_text_with_ocr
from app.services.pdf_fast_path import extract_text_with_pymupdf

RUNS_DIR = Path(__file__).resolve().parent / "benchmark_runs" / "ocr_latency"
SUPPORTED = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}


def _pipeline_runs_ocr(file_bytes: bytes) -> bool:
    """Mirror the OCR trigger in extraction_pipeline.run_extraction_pipeline."""
    is_image = (
        file_bytes.startswith(b"\xff\xd8\xff")
        or file_bytes.startswith(b"\x89PNG\r\n\x1a\n")
        or (len(file_bytes) >= 12 and file_bytes.startswith(b"RIFF") and file_bytes[8:12] == b"WEBP")
    )
    raw_text = extract_text_with_pymupdf(file_bytes).text
    extracted = extract_certificate_fields(raw_text)
    date_missing = not (
        extracted.get("waktu_mulai_pelaksanaan")
        and extracted["waktu_mulai_pelaksanaan"].value
        and extracted.get("waktu_selesai_pelaksanaan")
        and extracted["waktu_selesai_pelaksanaan"].value
    )
    return is_image or len(raw_text.strip()) < settings.min_text_length or date_missing


def run(certs_dir: Path, label: str) -> None:
    out_dir = RUNS_DIR / label
    text_dir = out_dir / "texts"
    text_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in certs_dir.iterdir() if p.suffix.lower() in SUPPORTED)
    if not files:
        raise SystemExit(f"Tidak ada sertifikat di {certs_dir}")

    # Worker produksi berjalan lama, jadi ukur dalam kondisi warm: model ONNX sudah
    # dimuat dan satu inferensi pemanasan tidak dihitung.
    _load_rapidocr()
    extract_text_with_ocr(files[0].read_bytes())

    records = []
    started = time.perf_counter()
    for idx, path in enumerate(files, 1):
        data = path.read_bytes()
        t0 = time.perf_counter()
        text = extract_text_with_ocr(data)
        elapsed = time.perf_counter() - t0
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        (text_dir / f"{digest[:16]}_{idx:03d}.txt").write_text(text, encoding="utf-8")
        records.append(
            {
                "file": path.name,
                "ocr_seconds": round(elapsed, 4),
                "text_sha256": digest,
                "text_chars": len(text),
                "pipeline_runs_ocr": _pipeline_runs_ocr(data),
            }
        )
        print(f"[{idx:3d}/{len(files)}] {elapsed:6.2f}s  {path.name[:60]}", flush=True)

    meta = {
        "label": label,
        "documents": len(records),
        "wall_seconds": round(time.perf_counter() - started, 2),
        "cpu_count": os.cpu_count(),
        "env": {k: os.getenv(k) for k in ("OMP_NUM_THREADS", "OCR_RAPID_THREADS")},
    }
    (out_dir / "results.json").write_text(
        json.dumps({"meta": meta, "records": records}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(_stats(records), indent=2))


def _stats(records: list[dict]) -> dict:
    def summarize(values: list[float]) -> dict:
        if not values:
            return {"n": 0}
        ordered = sorted(values)
        return {
            "n": len(values),
            "total_s": round(sum(values), 2),
            "mean_s": round(statistics.mean(values), 3),
            "median_s": round(statistics.median(values), 3),
            "p90_s": round(ordered[max(0, int(round(0.9 * len(ordered))) - 1)], 3),
            "max_s": round(ordered[-1], 3),
        }

    return {
        "all_docs": summarize([r["ocr_seconds"] for r in records]),
        "docs_where_pipeline_runs_ocr": summarize(
            [r["ocr_seconds"] for r in records if r["pipeline_runs_ocr"]]
        ),
    }


def compare(label_a: str, label_b: str) -> None:
    a = json.loads((RUNS_DIR / label_a / "results.json").read_text(encoding="utf-8"))
    b = json.loads((RUNS_DIR / label_b / "results.json").read_text(encoding="utf-8"))
    by_file_a = {r["file"]: r for r in a["records"]}
    by_file_b = {r["file"]: r for r in b["records"]}
    common = sorted(set(by_file_a) & set(by_file_b))
    diffs = [f for f in common if by_file_a[f]["text_sha256"] != by_file_b[f]["text_sha256"]]

    report = {
        "a": label_a,
        "b": label_b,
        "documents_compared": len(common),
        "identical_text": len(common) - len(diffs),
        "different_text": len(diffs),
        "different_files": diffs,
        "stats_a": _stats([by_file_a[f] for f in common]),
        "stats_b": _stats([by_file_b[f] for f in common]),
        "wall_seconds_a": a["meta"]["wall_seconds"],
        "wall_seconds_b": b["meta"]["wall_seconds"],
    }
    out = RUNS_DIR / f"compare_{label_a}_vs_{label_b}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_run = sub.add_parser("run")
    p_run.add_argument("--certs-dir", type=Path, required=True)
    p_run.add_argument("--label", required=True)
    p_cmp = sub.add_parser("compare")
    p_cmp.add_argument("--a", required=True)
    p_cmp.add_argument("--b", required=True)
    args = parser.parse_args()
    if args.cmd == "run":
        run(args.certs_dir, args.label)
    else:
        compare(args.a, args.b)


if __name__ == "__main__":
    main()
