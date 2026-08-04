"""Benchmark OCR eksperimen (handoff v9 §2). EXPERIMENT ONLY — tidak menyentuh
pipeline produksi.

Dua subcommand:
  build  : bikin korpus teks dari manifest (74 stem) pakai satu engine OCR
           (rapid / tess / paddle / rapid_tess). Catat latency per sertifikat
           dan kegagalan. Output: extracted_texts/*.txt + ocr_meta.json.
  eval   : evaluasi korpus teks dengan EKSTRAKTOR PRODUKSI
           (extract_certificate_fields + organizer_v2 + map_fields_to_form)
           terhadap Ground_Truth_Sertifikat_v8.csv. Output: field accuracy
           keseluruhan + subset scan/embedded.

Usage:
  uv run python -m tests.benchmark_ocr build --engine rapid \
      --out tests/benchmark_runs/ocr_experiment/baseline_rapid/extracted_texts
  uv run python -m tests.benchmark_ocr eval \
      --texts tests/benchmark_runs/ocr_experiment/baseline_rapid/extracted_texts \
      --out tests/benchmark_runs/ocr_experiment/baseline_rapid/eval.json
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

from tqdm import tqdm

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

os.environ.setdefault("APP_ENV", "development")

from tests import ocr_engine
from tests.ocr_engine import classify_manifest, ocr_path
from tests.evaluation_framework import (
    EVAL_FIELDS,
    aggregate_results,
    evaluate_row,
    load_csv,
    print_report,
)

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MANIFEST = os.path.join(REPO, "tests", "layout_manifest.json")
DEFAULT_CSV = os.path.join(REPO, "Ground_Truth_Sertifikat_v8.csv")
RUNS_DIR = os.path.join(REPO, "tests", "benchmark_runs", "ocr_experiment")


def _load_manifest() -> dict[str, str]:
    with open(MANIFEST) as f:
        return json.load(f)


def _run_dir(label: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(RUNS_DIR, f"{label}_{stamp}")


def _ocr_per_cert(args, stem: str, path: str) -> str:
    """OCR 1 sertifikat di SUBPROCESS fresh (lewat paddle_probe_safe --full-text).

    Proses fresh membebaskan semua memori C++ engine tiap cert — mencegah
    akumulasi RSS paddle yang bisa membekukan WSL. Mengembalikan teks OCR."""
    import subprocess
    proc = subprocess.run(
        [
            sys.executable, "-m", "tests.paddle_probe_safe",
            "--path", os.path.join(REPO, path),
            "--engine", args.engine,
            "--zoom", str(args.zoom),
            "--max-side", str(args.max_side),
            "--threads", str(args.threads),
            "--batch", str(args.batch),
            "--mem-cap-gb", str(args.mem_cap_gb),
            "--full-text",
        ],
        capture_output=True, text=True, timeout=600,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"probe exit {proc.returncode}: {proc.stderr[-500:]}")
    data = _extract_probe_json(proc.stdout)
    if data is None or "text" not in data:
        raise RuntimeError("probe tidak mengembalikan JSON text")
    return data["text"]


def _extract_probe_json(text: str) -> dict | None:
    """Ambil objek JSON utuh dari stdout probe (tahan noise progress bar)."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def cmd_build(args) -> None:
    import gc
    import resource

    # KAPUR BARIS DARURAT: batasi virtual memory proses sehingga kalau engine
    # OCR (paddle) kehabisan memori, proses melempar MemoryError & mati bersih
    # — TIDAK PERNAH membekukan WSL (lihat tests/paddle_probe_safe.py).
    if args.mem_cap_gb:
        cap = int(args.mem_cap_gb * 1024 ** 3)
        resource.setrlimit(resource.RLIMIT_AS, (cap, cap))

    manifest = _load_manifest()
    classification = classify_manifest(manifest)
    # `--out` = root run dir; teks selalu di `<root>/extracted_texts`.
    run_root = args.out or _run_dir(f"corpus_{args.engine}")
    texts_dir = os.path.join(run_root, "extracted_texts")
    os.makedirs(texts_dir, exist_ok=True)

    stems = sorted(manifest)
    if args.subset != "all":
        stems = [s for s in stems if classification[s]["scan"] == (args.subset == "scan")]
    n_total = len(stems)
    if args.offset:
        stems = stems[args.offset:]
    if args.limit:
        stems = stems[: args.limit]

    total_chars = 0
    n_ok = 0
    n_err = 0
    latency: list[dict] = []
    errors: list[dict] = []

    for stem in tqdm(stems, desc=f"OCR [{args.engine}]"):
        out_file = os.path.join(texts_dir, f"{stem}.txt")
        if args.skip_existing and os.path.exists(out_file):
            continue
        path = os.path.join(REPO, manifest[stem])
        t0 = time.perf_counter()
        try:
            if args.per_cert_process:
                text = _ocr_per_cert(args, stem, manifest[stem])
            else:
                text = ocr_path(args.engine, path, zoom=args.zoom)
            if args.prepend_embedded:
                # Mirip produksi: teks embedded (bila ada) + OCR.
                emb = ocr_engine.embedded_text(manifest[stem])
                if emb.strip():
                    text = f"{emb}\n{text}".strip()
            elapsed = round(time.perf_counter() - t0, 3)
        except Exception as e:  # noqa: BLE001
            n_err += 1
            errors.append({"stem": stem, "error": str(e)})
            continue
        total_chars += len(text)
        latency.append({"stem": stem, "seconds": elapsed, "chars": len(text)})
        if text.strip():
            n_ok += 1
            with open(os.path.join(texts_dir, f"{stem}.txt"), "w") as f:
                f.write(f"# Engine: {args.engine}\n# Seconds: {elapsed}\n\n{text}")
        del text
        gc.collect()  # WSL 7GB: rilis memori model/runtime tiap sertifikat

    missing = [s for s in stems if not os.path.exists(os.path.join(texts_dir, f"{s}.txt"))]
    if missing:
        print(f"WARN: {len(missing)} stem tanpa output: {missing[:5]} ...")

    n_scans = sum(1 for c in classification.values() if c["scan"])
    meta = {
        "engine": args.engine,
        "created": datetime.now().isoformat(),
        "manifest": MANIFEST,
        "subset": args.subset,
        "offset": args.offset,
        "limit": args.limit,
        "zoom": args.zoom,
        "stems_selected": n_total,
        "stems_this_run": len(stems),
        "stems_ok": n_ok,
        "stems_error": n_err,
        "stems_missing_output": len(missing),
        "scan_count": n_scans,
        "total_chars": total_chars,
        "errors": errors,
    }
    if latency:
        lats = sorted(x["seconds"] for x in latency)
        meta["latency"] = {
            "avg_seconds": round(sum(lats) / len(lats), 3),
            "median_seconds": round(lats[len(lats) // 2], 3),
            "p95_seconds": round(lats[int(len(lats) * 0.95)], 3),
            "max_seconds": round(max(lats), 3),
            "n": len(lats),
        }
    meta_name = f"ocr_meta_{args.offset:04d}.json" if (args.offset or args.limit) else "ocr_meta.json"
    try:
        meta["peak_rss_kb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except Exception:
        meta["peak_rss_kb"] = None
    with open(os.path.join(run_root, meta_name), "w") as f:
        json.dump(meta, f, indent=2)
    print(f"\nEngine [{args.engine}] subset={args.subset} zoom={args.zoom}: "
          f"ok={n_ok} err={n_err} of {len(stems)} (run ini) / {n_total} (subset)")
    if latency:
        print("Latency:", meta["latency"])
    print(f"Output: {texts_dir}")


def cmd_eval(args) -> None:
    texts_dir = args.texts
    rows = load_csv(args.csv)
    stem_to_row = {}
    for r in rows:
        fname = (r.get("nama_file") or "").strip()
        stem = os.path.splitext(fname)[0]
        stem_to_row[stem] = r

    manifest = _load_manifest()
    classification = classify_manifest(manifest)

    files = sorted(f for f in os.listdir(texts_dir) if f.endswith(".txt"))
    matched = 0
    results: list[dict] = []
    skipped_missing = []
    for fname in tqdm(files, desc="Eval"):
        stem = os.path.splitext(fname)[0]
        row = stem_to_row.get(stem)
        if row is None:
            skipped_missing.append(stem)
            continue
        with open(os.path.join(texts_dir, fname)) as f:
            lines = f.read().splitlines()
        raw_text = "\n".join(l for l in lines if not l.startswith("#")).strip()
        matched += 1

        from app.services.field_extractor import extract_certificate_fields, ExtractedValue
        from app.services.organizer_v2 import extract_organizer_v2
        from app.services.form_mapper import map_fields_to_form

        try:
            extracted = extract_certificate_fields(raw_text)
        except Exception:
            extracted = {}
        try:
            v2 = extract_organizer_v2(raw_text)
        except Exception:
            v2 = None
        if v2:
            extracted["penyelenggara_kegiatan"] = ExtractedValue(v2, 0.84, "organizer_v2")
        extracted["full_text"] = ExtractedValue(raw_text, 1.0, "ocr_text")
        mapped = map_fields_to_form(extracted, tahun_akademik="2024/2025", bukti_fisik="Sertifikat")

        field_results = evaluate_row(mapped, row)
        field_results["_meta"] = {
            "filename": fname,
            "scan": classification.get(stem, {}).get("scan", True),
        }
        results.append(field_results)

    print(f"\nMatched {matched} / {len(files)} txt -> GT")
    if skipped_missing:
        print(f"  (unmatched stems, bukan bagian GT v8): {len(skipped_missing)}")

    summary = aggregate_results(results)
    scan_results = [r for r in results if r.get("_meta", {}).get("scan")]
    emb_results = [r for r in results if not r.get("_meta", {}).get("scan")]
    scan_summary = aggregate_results(scan_results) if scan_results else None
    emb_summary = aggregate_results(emb_results) if emb_results else None

    out = {
        "texts_dir": texts_dir,
        "csv": args.csv,
        "n_matched": matched,
        "all": summary,
        "scan": scan_summary,
        "embedded": emb_summary,
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"Saved: {args.out}")

    print("\n=== ALL ===")
    print_report(summary)
    if scan_summary:
        print("\n=== SCAN SUBSET ===")
        print_report(scan_summary)
    if emb_summary:
        print("\n=== EMBEDDED SUBSET ===")
        print_report(emb_summary)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="bangun korpus OCR")
    b.add_argument("--engine", required=True,
                   choices=sorted(ocr_engine.ENGINES) + ["rapid_tess"],
                   help="engine OCR (rapid/tess/paddle/rapid_tess)")
    b.add_argument("--out", default=None, help="direktori root output korpus")
    b.add_argument("--subset", default="all", choices=["all", "scan", "embedded"],
                   help="batasi ke subset (scan = teks embedded <=60 char + PNG)")
    b.add_argument("--limit", type=int, default=None,
                   help="maks jumlah sertifikat di run ini (chunking)")
    b.add_argument("--offset", type=int, default=0,
                   help="lewati N sertifikat pertama (chunking)")
    b.add_argument("--zoom", type=float, default=3.0,
                   help="render zoom untuk PDF (default 3.0, konsisten baseline)")
    b.add_argument("--max-side", type=int, default=0,
                   help="downscale sisi terpanjang halaman (px) sebelum OCR; "
                        "0 = tanpa downscale (diteruskan ke probe)")
    b.add_argument("--mem-cap-gb", type=float, default=10.0,
                   help="batas virtual memory proses (RLIMIT_AS). VA tinggi aman "
                        "(RSS tetap terbatas karena per-cert subprocess fresh); "
                        "containment WSL dari process-per-cert, bukan dari cap")
    b.add_argument("--skip-existing", action="store_true",
                   help="lewati stem yang sudah punya file teks (perbaikan chunk)")
    b.add_argument("--per-cert-process", action="store_true",
                   help="OCR tiap cert di subprocess fresh (wajib utk paddle — "
                        "cegah akumulasi RSS yang membekukan WSL)")
    b.add_argument("--threads", type=int, default=4, help="CPU thread (paddle)")
    b.add_argument("--batch", type=int, default=4, help="batch size rec (paddle)")
    b.add_argument("--prepend-embedded", action="store_true",
                   help="awali teks embedded PyMuPDF sebelum OCR (mirip produksi)")
    b.set_defaults(func=cmd_build)

    e = sub.add_parser("eval", help="evaluasi korpus terhadap GT v8")
    e.add_argument("--texts", required=True, help="direktori extracted_texts")
    e.add_argument("--csv", default=DEFAULT_CSV, help="GT CSV (default v8)")
    e.add_argument("--out", required=True, help="path json output eval")
    e.set_defaults(func=cmd_eval)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
