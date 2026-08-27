"""Probe Keras-OCR (CRAFT detection + CRNN recognition, TF-based).

OCR-012 (goal user: "coba banyak engine selain LFM").
End-to-end: detection + recognition dalam satu pipeline.
Model: CRAFT (detection) + CRNN (recognition), ~120MB total.
TensorFlow-based — berjalan di venv ~/.cache/keras_ocr/venv (terpisah dr torch).

Harness (konvensi anti-OOM — sama dgn probe lain):
  - Worker `tests/keras_worker.py` sebagai subprocess per chunk.
  - Resume: txt existing di-skip.

Run:
  uv run python -m tests.benchmark_keras_probe probe \
      --python ~/.cache/keras_ocr/venv/bin/python \
      --out tests/benchmark_runs/ocr_experiment/probe_keras
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "backend"))

from tests.ocr_engine import classify_manifest
from tests.benchmark_ppu_probe import PROBE_STEMS, _find_source, _render_pages_streaming, _rss_kb

MANIFEST = os.path.join(REPO, "tests", "layout_manifest.json")
RUNS_DIR = os.path.join(REPO, "tests", "benchmark_runs", "ocr_experiment")
WORKER = os.path.join(REPO, "tests", "keras_worker.py")

DEFAULT_RSS_CAP_GB = 6.0


def _run_chunk(jobs: list[dict], rss_cap_bytes: int, python: str) -> dict:
    pages_json = os.path.join(os.path.dirname(jobs[0]["out"]), "_chunk_pages.json")
    with open(pages_json, "w") as fh:
        json.dump(jobs, fh)
    proc = subprocess.Popen(
        [python, WORKER, "--pages-json", pages_json],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        start_new_session=True, cwd=REPO,
    )
    stats = {"peak_rss_kb": 0, "killed": None}

    def _guard() -> None:
        while proc.poll() is None:
            kb = _rss_kb(proc.pid)
            stats["peak_rss_kb"] = max(stats["peak_rss_kb"], kb)
            if rss_cap_bytes and kb * 1024 > rss_cap_bytes:
                stats["killed"] = f"RSS>={rss_cap_bytes // 1024**3}GB"
            if stats["killed"]:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
                return
            time.sleep(1.0)

    guard = threading.Thread(target=_guard, daemon=True)
    guard.start()
    try:
        out, err = proc.communicate(timeout=7200)
        stats["rc"] = proc.returncode
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
        out, err = proc.communicate()
        stats["rc"] = proc.returncode
    guard.join(timeout=2)
    stats["tail"] = (err or "").strip().splitlines()[-3:] if err else []
    print(out or "", end="")
    return stats


def cmd_probe(args) -> None:
    with open(MANIFEST) as f:
        classification = classify_manifest(json.load(f))
    scans = sorted(s for s, c in classification.items() if c["scan"])
    stems = scans if args.all_scans else PROBE_STEMS

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_root = args.out or os.path.join(RUNS_DIR, f"probe_keras_{stamp}")
    pages_dir = os.path.join(run_root, "pages")
    texts_dir = os.path.join(run_root, "extracted_keras")
    os.makedirs(pages_dir, exist_ok=True)
    os.makedirs(texts_dir, exist_ok=True)
    meta_path = os.path.join(run_root, "meta.jsonl")
    print(f"run={run_root} stems={len(stems)} chunk={args.chunk} python={args.python}")

    jobs: list[dict] = []
    for stem in stems:
        out_txt = os.path.join(texts_dir, f"{stem}.txt")
        if os.path.exists(out_txt):
            continue
        png_paths = sorted(
            os.path.join(pages_dir, f) for f in os.listdir(pages_dir)
            if f.startswith(f"{stem}_") and f.endswith(".png")
        )
        if not png_paths:
            src = _find_source(stem)
            if src is None:
                print(f"[{stem}] sumber tidak ditemukan — SKIP")
                continue
            if src.lower().endswith(".pdf"):
                png_paths = _render_pages_streaming(src, os.path.join(pages_dir, stem))
            else:
                png_paths = [src]
        for i, p in enumerate(png_paths):
            jobs.append({"stem": stem, "png": p, "out": out_txt})

    total_ok = total_err = 0
    peaks_rss = []
    for c in range(0, len(jobs), args.chunk):
        chunk = jobs[c:c + args.chunk]
        t0 = time.time()
        stats = _run_chunk(chunk, int(args.rss_cap_gb * 1024**3), args.python)
        dt = time.time() - t0
        peaks_rss.append(stats["peak_rss_kb"])
        done_stems = {j["stem"] for j in chunk if os.path.exists(j["out"])}
        total_ok += len(done_stems)
        total_err += len({j["stem"] for j in chunk}) - len(done_stems)
        label = f"{chunk[0]['stem']}..{chunk[-1]['stem']}" if len(chunk) > 1 else chunk[0]["stem"]
        status = stats.get("killed") or f"rc={stats['rc']}"
        print(f"[chunk {label}] {status} {dt:.1f}s "
              f"rss_peak={stats['peak_rss_kb'] // 1024}MB "
              f"done={len(done_stems)}/{len({j['stem'] for j in chunk})}")
        if stats.get("killed") or stats["rc"] != 0:
            print("worker stderr tail:", stats["tail"])
        for stem in done_stems:
            with open(meta_path, "a") as fh:
                fh.write(json.dumps({"stem": stem, "engine": "keras-ocr", "ts": stamp}) + "\n")

    if peaks_rss:
        print(f"\nselesai: ok={total_ok} err={total_err} | peak RSS {max(peaks_rss)//1024}MB -> {run_root}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("probe")
    b.add_argument("--out", default="")
    b.add_argument("--all-scans", action="store_true")
    b.add_argument("--chunk", type=int, default=10)
    b.add_argument("--rss-cap-gb", type=float, default=6.0)
    b.add_argument("--python", default=os.path.expanduser("~/.cache/keras_ocr/venv/bin/python"))
    b.set_defaults(fn=cmd_probe)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
