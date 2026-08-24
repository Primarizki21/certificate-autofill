"""Probe LFM2.5-VL-3B (VLM OCR via llama.cpp llama-server). EXPERIMENT ONLY.

Model VLM LiquidAI/LFM2.5-VL-3B — "Better OCR" (full page OCR). Variant
terendah RAM/quant: GGUF Q4_0 (1520 MB) + mmproj Q8_0 (556 MB).

Alur (mirror `tests/benchmark_doctr_probe.py`, OCR-006):
  - `llama-server -m <Q4_0.gguf> --mmproj <mmproj-Q8_0.gguf> -c 4096 --port 8080`
  - Harness render halaman PNG (zoom 3.0) -> POST /v1/chat/completions dengan
    prompt transkripsi polos -> simpan teks -> eval `benchmark_ocr.cmd_eval`
    (GT v9 + matcher v2).

Run:
  uv run python -m tests.benchmark_lfm25_probe probe --out tests/benchmark_runs/lfm25_ocr_<ts>
  uv run python -m tests.benchmark_lfm25_probe eval --texts <dir> --out <dir>/eval.json
"""

import argparse
import base64
import json
import os
import sys
import time
import urllib.request
from datetime import datetime

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "backend"))

from tests.ocr_engine import classify_manifest

MANIFEST = os.path.join(REPO, "tests", "layout_manifest.json")
GT_CSV = os.path.join(REPO, "Ground_Truth_Sertifikat_v9.csv")
RUNS_DIR = os.path.join(REPO, "tests", "benchmark_runs", "ocr_experiment")

# 10 scan cert, tetap (sama dgn probe DocTR OCR-006).
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

TRANS_PROMPT = (
    "Transkripsikan semua teks pada gambar ini secara lengkap, baris per baris, "
    "persis seperti yang tertulis. Jangan menambahkan komentar."
)

DEFAULT_SERVER = "http://127.0.0.1:8080"


def _run_dir(label: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(RUNS_DIR, f"{label}_{stamp}")


def _ocr_page(server: str, image_bytes: bytes, n_predict: int, temp: float) -> str:
    """Transkripsi 1 halaman PNG via llama-server (OpenAI-compatible API)."""
    b64 = base64.b64encode(image_bytes).decode()
    payload = {
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                {"type": "text", "text": TRANS_PROMPT},
            ],
        }],
        "temperature": temp,
        "max_tokens": n_predict,
    }
    req = urllib.request.Request(
        f"{server}/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    resp = json.load(urllib.request.urlopen(req, timeout=900))
    return (resp.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()


def probe_one(stem: str, path: str, server: str, zoom: float, n_predict: int, temp: float) -> dict:
    """OCR 1 cert via llama-server. PDF dirender per halaman (zoom konsisten)."""
    if path.lower().endswith(".png"):
        with open(path, "rb") as f:
            pages = [f.read()]
    else:
        from app.services.pdf_fast_path import render_pdf_pages_to_png_bytes
        with open(path, "rb") as f:
            pages = render_pdf_pages_to_png_bytes(f.read(), zoom=zoom)
    parts: list[str] = []
    for page in pages:
        t = _ocr_page(server, page, n_predict, temp)
        if t:
            parts.append(t)
    return {"text": "\n".join(parts), "pages": len(pages), "chars": sum(len(p) for p in parts)}


def _rss_kb(pid: int) -> int | None:
    if pid <= 0:
        return None
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except OSError:
        return None
    return None


def cmd_probe(args) -> None:
    with open(MANIFEST) as f:
        manifest = json.load(f)
    classification = classify_manifest(manifest)
    if getattr(args, "all_scans", False):
        stems = sorted(s for s, c in classification.items() if c["scan"])
    else:
        stems = PROBE_STEMS
        missing = [s for s in stems if s not in classification]
        if missing:
            raise SystemExit(f"stem tak ada di manifest: {missing}")
        scans = [s for s in stems if classification[s]["scan"]]
        if len(scans) != len(stems):
            raise SystemExit(f"PROBE_STEMS harus semua scan; bukan: {set(stems) - set(scans)}")

    run_root = args.out or _run_dir("lfm25_ocr")
    texts_dir = os.path.join(run_root, "extracted_texts")
    os.makedirs(texts_dir, exist_ok=True)

    reports = {}
    errors = []
    for stem in stems:
        out_file = os.path.join(texts_dir, f"{stem}.txt")
        if os.path.exists(out_file):
            print(f"{stem}: skip (exists)")
            continue
        t0 = time.perf_counter()
        try:
            r = probe_one(stem, manifest[stem], args.server, args.zoom, args.n_predict, args.temp)
        except Exception as e:  # noqa: BLE001
            errors.append({"stem": stem, "error": str(e)})
            print(f"{stem}: ERROR {e}")
            continue
        text = r["text"]
        r["stem"] = stem
        r["wall_s"] = round(time.perf_counter() - t0, 2)
        reports[stem] = r
        with open(out_file, "w") as f:
            f.write(f"# Engine: lfm25-q4_0\n# Seconds: {r['wall_s']}\n\n{text}")
        print(f"{stem}: chars={len(text)} pages={r['pages']} wall={r['wall_s']}s")

    meta = {
        "engine": "lfm25_vl_3b",
        "variant": "GGUF Q4_0 + mmproj Q8_0 (llama.cpp llama-server)",
        "server": args.server,
        "prompt": TRANS_PROMPT,
        "created": datetime.now().isoformat(),
        "stems": stems,
        "zoom": args.zoom,
        "n_predict": args.n_predict,
        "temp": args.temp,
        "server_rss_kb": _rss_kb(args.server_pid),
        "errors": errors,
        "reports": reports,
    }
    with open(os.path.join(run_root, "ocr_meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    print(f"\nDone. ok={len(reports)} err={len(errors)} / {len(stems)}")
    print(f"Output: {texts_dir}")


def cmd_eval(args) -> None:
    from tests import benchmark_ocr
    benchmark_ocr.cmd_eval(args)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("probe", help="OCR 10 scan cert dengan LFM2.5-VL-3B")
    b.add_argument("--out", default=None, help="root run dir output")
    b.add_argument("--server", default=DEFAULT_SERVER, help="base URL llama-server")
    b.add_argument("--zoom", type=float, default=3.0)
    b.add_argument("--n-predict", type=int, default=2000)
    b.add_argument("--temp", type=float, default=0.1)
    b.add_argument("--server-pid", type=int, default=0, help="PID llama-server utk RSS meta")
    b.add_argument("--all-scans", action="store_true",
                   help="transkripsi SEMUA stem scan di manifest (49), bukan hanya PROBE_STEMS")
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
