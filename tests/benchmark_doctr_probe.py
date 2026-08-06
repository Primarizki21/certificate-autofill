"""Probe DocTR (handoff v13 OCR-005). EXPERIMENT ONLY — tidak menyentuh produksi.

Controlled probe pada 10 sertifikat SCAN tetap (spread kategori), memakai
harness yang sudah ada:
  - `tests/paddle_probe_safe.py` (subprocess + RLIMIT_AS + watchdog RSS)
    dengan `--engine doctr` → aman di WSL 8GB.
  - `tests/ocr_engine.ocr_doctr` (db_mobilenet_v3_large + crnn_mobilenet_v3_small).
  - Evaluasi vs `Ground_Truth_Sertifikat_v9.csv` + `tests.matchers` (matcher v2)
    memakai `benchmark_ocr.cmd_eval` — sama seperti run OCR sebelumnya.

Stem dipilih tetap & deterministik: kasus yang TAJAM untuk 3 gate field
(nomor / tanggal / organizer), termasuk cert yang jadi miss set di Exp5
(2439919 UB, FIT_Faiz, NIC_Faiz, 2954707, 2954933, 2954571).

Run:
  uv run --with python-doctr python -m tests.benchmark_doctr_probe \
      --out tests/benchmark_runs/ocr_experiment/probe_doctr
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "backend"))

from tests.ocr_engine import classify_manifest
from tests.evaluation_framework import (
    aggregate_results,
    evaluate_row,
    load_csv,
    print_report,
)

MANIFEST = os.path.join(REPO, "tests", "layout_manifest.json")
GT_CSV = os.path.join(REPO, "Ground_Truth_Sertifikat_v9.csv")
RUNS_DIR = os.path.join(REPO, "tests", "benchmark_runs", "ocr_experiment")

# 10 scan cert, tetap: spread kategori + kasus gate field tajam.
PROBE_STEMS = [
    "2439919_221065_skp",
    "2954707_219642_skp",
    "2954933_219642_skp",
    "2954571_219642_skp",
    "2955331_219642_skp",
    "FIT_Faiz",
    "NIC_Faiz",
    "ACW_Faiz",
    "1952296_219642_skp",
    "SERTIF76",
]

# DocTR (torch) reservasi VA besar → RLIMIT_AS harus ≥ RAM host; containment
# sebenarnya dari watchdog RSS parent (kill > cap) + process-per-cert fresh.
MEM_CAP_GB = 8.0


def _run_dir(label: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(RUNS_DIR, f"{label}_{stamp}")


def probe_one(stem: str, path: str, zoom: float) -> dict:
    """OCR 1 cert via paddle_probe_safe --engine doctr (subprocess fresh +
    RLIMIT_AS + watchdog RSS). Mengembalikan dict report probe."""
    python = sys.executable
    probe = os.path.join(REPO, "tests", "paddle_probe_safe.py")
    cmd = [
        python, probe,
        "--path", os.path.join(REPO, path),
        "--engine", "doctr",
        "--zoom", str(zoom),
        "--threads", "1",
        "--mem-cap-gb", str(MEM_CAP_GB),
        "--full-text",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if proc.returncode != 0:
        raise RuntimeError(
            f"probe exit {proc.returncode}: stderr={proc.stderr[-300:]!r} stdout={proc.stdout[-300:]!r}"
        )
    data = json.loads(proc.stdout)
    return data


def cmd_probe(args) -> None:
    import json as _json

    with open(MANIFEST) as f:
        manifest = _json.load(f)
    classification = classify_manifest(manifest)
    missing = [s for s in PROBE_STEMS if s not in classification]
    if missing:
        raise SystemExit(f"stem tak ada di manifest: {missing}")
    scans = [s for s in PROBE_STEMS if classification[s]["scan"]]
    if len(scans) != len(PROBE_STEMS):
        raise SystemExit(f"PROBE_STEMS harus semua scan; bukan: {set(PROBE_STEMS) - set(scans)}")

    run_root = args.out or _run_dir("probe_doctr")
    texts_dir = os.path.join(run_root, "extracted_texts")
    os.makedirs(texts_dir, exist_ok=True)

    reports = {}
    errors = []
    for stem in PROBE_STEMS:
        out_file = os.path.join(texts_dir, f"{stem}.txt")
        if os.path.exists(out_file):
            continue
        t0 = time.perf_counter()
        try:
            r = probe_one(stem, manifest[stem], args.zoom)
        except Exception as e:  # noqa: BLE001
            errors.append({"stem": stem, "error": str(e)})
            continue
        text = r.get("text", "")
        r["stem"] = stem
        r["wall_s"] = round(time.perf_counter() - t0, 2)
        reports[stem] = r
        with open(out_file, "w") as f:
            f.write(f"# Engine: doctr\n# Seconds: {r['wall_s']}\n\n{text}")
        if r.get("status") != "ok":
            errors.append({"stem": stem, "status": r.get("status"), "error": r.get("error")})
        print(f"{stem}: status={r.get('status')} chars={len(text)} "
              f"init={r.get('model_init_s')}s wall={r['wall_s']}s "
              f"maxrss={r.get('maxrss_kb', 0) // 1024}MB watchdog={r.get('watchdog_kill')}")

    meta = {
        "engine": "doctr",
        "arch": {"det": "db_mobilenet_v3_large", "reco": "crnn_mobilenet_v3_small"},
        "created": datetime.now().isoformat(),
        "stems": PROBE_STEMS,
        "zoom": args.zoom,
        "mem_cap_gb": MEM_CAP_GB,
        "errors": errors,
        "reports": reports,
    }
    with open(os.path.join(run_root, "ocr_meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    print(f"\nDone. ok={len(reports) - len(errors)} err={len(errors)} / {len(PROBE_STEMS)}")
    print(f"Output: {texts_dir}")


def cmd_eval(args) -> None:
    """Evaluasi korpus probe vs GT v9 + matcher v2 (sub-set scan saja)."""
    from tests import benchmark_ocr
    benchmark_ocr.cmd_eval(args)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("probe", help="OCR 10 scan cert dengan DocTR")
    b.add_argument("--out", default=None, help="root run dir output")
    b.add_argument("--zoom", type=float, default=3.0)
    b.set_defaults(func=cmd_probe)

    e = sub.add_parser("eval", help="evaluasi korpus vs GT v9 (matcher v2)")
    e.add_argument("--texts", required=True, help="direktori extracted_texts")
    e.add_argument("--csv", default=GT_CSV, help="GT CSV (default v9)")
    e.add_argument("--out", required=True, help="path json output eval")
    e.set_defaults(func=cmd_eval)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
