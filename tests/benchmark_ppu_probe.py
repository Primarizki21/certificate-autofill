"""Probe ppu-paddle-ocr (PP-OCRv6/v5 via ONNX standalone binary). EXPERIMENT ONLY.

OCR-009 (cabang revive OCR, arah user: "coba banyak engine selain LFM").
Engine BEDA dari kegagalan paddle sebelumnya:
  - OCR-002 = paddleocr 2.9 + paddlepaddle 2.6 (Paddle inference) -> nomor FAIL.
  - OCR-001 = paddleocr 3.7 Python (PaddleX) -> OOM CPU.
  - ini     = ONNX Runtime (binary Bun mandiri), model PP-OCRv6 tiny/small /
    v5 en-server (~6-139MB), cache ~/.cache/ppu-paddle-ocr.

Harness (hardened pasca-insiden OOM WSL — lihat ledger OCR-009):
  - Render halaman PDF -> PNG PAGE-PER-PAGE (render -> tulis -> del; JANGAN
    menahan semua page image sekaligus — konvensi anti-OOM `ocr_pdf`).
  - Per model preset: subprocess CLI `recognize <png> --json -q` (stdout
    bersih, progress di stderr), teks digabung antar halaman.
  - **Watchdog RSS**: polling /proc/<pid>/status, SIGKILL process-group jika
    RSS > cap (default 2.5GB, flag --rss-cap-gb) + timeout per halaman.
    RLIMIT_AS TIDAK dipakai: runtime JS/WASM (Bun + ONNX + OpenCV.js)
    reservasi virtual memori besar sehingga AS-limit false-kill; batas nyata = RSS.
  - Engine default `canvas-native` (tanpa heap WASM OpenCV.js; akurasi paritas
    menurut README upstream). Peak RSS dicatat di meta.jsonl untuk audit.
  - Resume: txt yang sudah ada di-skip (aman dibunuh/diulang).

Evaluasi terpisah via benchmark_hybrid_ocr.cmd_eval (--doc dir kosong => base-only):
  uv run python -m tests.benchmark_hybrid_ocr eval \
      --base <out>/extracted_<model> --doc <out>/empty_doc --doc-label ppu-<model> \
      --stems 10 --out <out>/eval_<model>_10.json

Run:
  uv run python -m tests.benchmark_ppu_probe probe --out tests/benchmark_runs/ocr_experiment/probe_ppu
  uv run python -m tests.benchmark_ppu_probe probe --all-scans   # full 49 setelah gate lolos
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

MANIFEST = os.path.join(REPO, "tests", "layout_manifest.json")
RUNS_DIR = os.path.join(REPO, "tests", "benchmark_runs", "ocr_experiment")
BIN = os.path.expanduser("~/.cache/ppu-paddle-ocr/bin/ppu-paddle-ocr-linux-x64")
ZOOM = 3.0  # sama dengan baseline (tests.ocr_engine.ZOOM)

# 10 scan cert tetap — sama dengan probe DocTR/LFM (spread kategori, gate tajam).
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

DEFAULT_MODELS = "v6-tiny,v6-small,v5-en-server"
DEFAULT_RSS_CAP_GB = 2.5


def _find_source(stem: str) -> str | None:
    """Cari sumber cert: PDF atau gambar (mis. SERTIF76 = PNG)."""
    wanted = {".pdf", ".png", ".jpg", ".jpeg"}
    for root, _dirs, files in os.walk(os.path.join(REPO, "Sertifikat_Ground_Truth")):
        for f in files:
            base, ext = os.path.splitext(f)
            if base == stem and ext.lower() in wanted:
                return os.path.join(root, f)
    return None


def _render_pages_streaming(pdf_path: str, out_prefix: str) -> list[str]:
    """Render PDF -> PNG satu per satu (render -> tulis -> del).
    Konvensi anti-OOM `ocr_pdf`: JANGAN menahan semua page image sekaligus."""
    import fitz
    paths: list[str] = []
    doc = fitz.open(pdf_path)
    try:
        for i, page in enumerate(doc):
            pix = page.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), alpha=False)
            p = f"{out_prefix}_{i}.png"
            pix.save(p)
            del pix
            paths.append(p)
    finally:
        doc.close()
    return paths


def _rss_kb(pid: int) -> int:
    try:
        with open(f"/proc/{pid}/status") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except (FileNotFoundError, ProcessLookupError):
        pass
    return 0


def _recognize_page(
    png_path: str, model: str, engine: str, rss_cap_bytes: int, timeout: float = 300.0
) -> tuple[str, float, int, int, bool]:
    """CLI recognize satu PNG dgn watchdog RSS.
    Return (text, seconds, rc, peak_rss_kb, rss_killed)."""
    t0 = time.time()
    proc = subprocess.Popen(
        [BIN, "recognize", png_path, "--json", "-q", "--model", model,
         "--engine", engine],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        start_new_session=True,
    )
    peak = {"kb": 0, "killed": False}

    def _guard() -> None:
        while proc.poll() is None:
            kb = _rss_kb(proc.pid)
            if kb > peak["kb"]:
                peak["kb"] = kb
            if kb * 1024 > rss_cap_bytes:
                peak["killed"] = True
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
                return
            time.sleep(0.2)

    guard = threading.Thread(target=_guard, daemon=True)
    guard.start()
    try:
        out, _err = proc.communicate(timeout=timeout)
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
        out, _err = proc.communicate()
        rc = proc.returncode
    dt = time.time() - t0
    if rc != 0 or peak["killed"]:
        return "", dt, (rc if rc else -9), peak["kb"], peak["killed"]
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return "", dt, rc, peak["kb"], peak["killed"]
    return (data.get("text") or "").strip(), dt, rc, peak["kb"], peak["killed"]


def cmd_probe(args) -> None:
    if not os.path.exists(BIN):
        sys.exit(f"binary tidak ada: {BIN} — unduh dulu (lihat docstring)")
    with open(MANIFEST) as f:
        manifest = json.load(f)
    classification = classify_manifest(manifest)
    scans = sorted(s for s, c in classification.items() if c["scan"])
    stems = scans if args.all_scans else PROBE_STEMS
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    rss_cap_bytes = int(args.rss_cap_gb * 1024**3)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_root = args.out or os.path.join(RUNS_DIR, f"probe_ppu_{stamp}")
    pages_dir = os.path.join(run_root, "pages")
    os.makedirs(pages_dir, exist_ok=True)
    meta_path = os.path.join(run_root, "meta.jsonl")
    print(f"run={run_root} stems={len(stems)} models={models} "
          f"engine={args.engine} rss_cap={args.rss_cap_gb}GB")

    total_ok = total_err = 0
    peaks: list[int] = []
    for stem in stems:
        # Render sekali per stem (page-per-page), pakai ulang untuk semua model.
        png_paths = sorted(
            os.path.join(pages_dir, f) for f in os.listdir(pages_dir)
            if f.startswith(f"{stem}_") and f.endswith(".png")
        )
        if not png_paths:
            src = _find_source(stem)
            if src is None:
                print(f"[{stem}] sumber (PDF/gambar) tidak ditemukan — SKIP")
                continue
            if src.lower().endswith(".pdf"):
                png_paths = _render_pages_streaming(
                    pdf=src, out_prefix=os.path.join(pages_dir, stem)
                )
            else:
                png_paths = [src]  # gambar langsung = satu halaman

        for model in models:
            texts_dir = os.path.join(run_root, f"extracted_{model}")
            os.makedirs(texts_dir, exist_ok=True)
            out_txt = os.path.join(texts_dir, f"{stem}.txt")
            if os.path.exists(out_txt):
                continue  # resume
            parts, secs, err = [], 0.0, None
            peak_kb = 0
            for p in png_paths:
                text, dt, rc, kb, killed = _recognize_page(
                    p, model, args.engine, rss_cap_bytes
                )
                secs += dt
                peak_kb = max(peak_kb, kb)
                if killed:
                    err = f"RSS>={args.rss_cap_gb}GB KILLED"
                    break
                if rc != 0:
                    err = f"rc={rc}"
                    break
                parts.append(text)
            peaks.append(peak_kb)
            if err:
                total_err += 1
                print(f"[{stem}/{model}] ERROR {err} ({secs:.1f}s, peak {peak_kb // 1024}MB)")
                continue
            body = "\n".join(x for x in parts if x).strip()
            with open(out_txt, "w") as fh:
                fh.write(f"# Engine: ppu-{model}\n# Seconds: {secs:.2f}\n\n{body}\n")
            total_ok += 1
            with open(meta_path, "a") as fh:
                fh.write(json.dumps({
                    "stem": stem, "model": model, "seconds": round(secs, 2),
                    "peak_rss_mb": round(peak_kb / 1024, 1), "engine": args.engine,
                    "ts": stamp,
                }) + "\n")
            print(f"[{stem}/{model}] ok {secs:.1f}s peak={peak_kb // 1024}MB ({len(body)} chars)")

    if peaks:
        print(f"\npeak RSS maks: {max(peaks) // 1024}MB | ok={total_ok} err={total_err} -> {run_root}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("probe", help="OCR korpus scan via ppu CLI")
    b.add_argument("--models", default=DEFAULT_MODELS, help="preset dipisah koma")
    b.add_argument("--out", default="", help="root output run")
    b.add_argument("--all-scans", action="store_true", help="49 scan (default: 10 probe)")
    b.add_argument("--engine", default="canvas-native",
                   choices=["canvas-native", "opencv"],
                   help="backend pengolahan gambar CLI (default: canvas-native, lebih ringan)")
    b.add_argument("--rss-cap-gb", type=float, default=DEFAULT_RSS_CAP_GB,
                   help="watchdog: SIGKILL subprocess saat RSS melebihi cap (GB)")
    b.set_defaults(fn=cmd_probe)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
