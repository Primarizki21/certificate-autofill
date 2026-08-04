"""Probe PaddleOCR terkontrol — TIDAK BISA membekukan WSL (desain utama).

WSL 7.7GB membeku bila proses memakan semua RAM. Probe ini menjalankan OCR 1
sertifikat di SUBPROCESS dengan:
  - RLIMIT_AS (cap virtual memory) -> kelebihan jadi MemoryError di proses,
    exit code 42 (bukan matikan VM)
  - faulthandler.enable()          -> segfault menampilkan traceback
  - watchdog induk: sampling /proc/<pid>/status VmRSS tiap 0.2s; kill proses
    bila RSS melewati --mem-cap-gb (induk yang kill, VM aman)

Output JSON ke stdout (diproduksi induk; child mengirim JSON fase sendiri).

Usage (pakai venv yang punya paddleocr):
  PYTHONPATH=backend:tests .venv-ocr/bin/python -m tests.paddle_probe_safe \
      --path Sertifikat_Ground_Truth/Lomba/Girifest_Faiz.pdf \
      --zoom 3.0 --max-side 0 --threads 4 --mem-cap-gb 2.5
"""

from __future__ import annotations

import argparse
import json
import os
import resource
import subprocess
import sys
import time
from io import BytesIO

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

CHILD_ENV = "PADDLE_PROBE_CHILD"


def _render_pages(pdf_bytes: bytes, zoom: float):
    import fitz
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    matrix = fitz.Matrix(zoom, zoom)
    try:
        for page in doc:
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            yield pix.tobytes("png")
            del pix
    finally:
        doc.close()


def _downscale(png_bytes: bytes, max_side: int) -> bytes:
    if max_side <= 0:
        return png_bytes
    from PIL import Image
    img = Image.open(BytesIO(png_bytes)).convert("RGB")
    w, h = img.size
    m = max(w, h)
    if m <= max_side:
        return png_bytes
    scale = max_side / m
    img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    buf = BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _child(args) -> int:
    """Jalankan OCR 1 cert di proses ini, lalu tulis JSON fase ke stdout."""
    cap_bytes = int(args.mem_cap_gb * 1024 ** 3)
    resource.setrlimit(resource.RLIMIT_AS, (cap_bytes, cap_bytes))
    import faulthandler
    faulthandler.enable()

    # Batasi thread OpenMP/MKLDNN paddle 2.x via env (API set_num_threads tidak
    # selalu ada). Ini juga mengurangi thread stack oversubscription.
    os.environ["OMP_NUM_THREADS"] = str(args.threads)
    os.environ["MKL_NUM_THREADS"] = str(args.threads)

    sys.path.insert(0, REPO)
    sys.path.insert(0, os.path.join(REPO, "tests"))
    sys.path.insert(0, os.path.join(REPO, "backend"))
    import tests.ocr_engine as oe

    oe.PADDLE_CPU_THREADS = args.threads
    oe.PADDLE_REC_BATCH = args.batch

    report: dict = {
        "engine": args.engine,
        "paddleocr_version": None,
        "paddle_version": None,
        "zoom": args.zoom,
        "max_side": args.max_side,
        "threads": args.threads,
        "batch": args.batch,
        "mem_cap_gb": args.mem_cap_gb,
        "status": "ok",
        "model_init_s": None,
        "per_page_s": [],
        "page_chars": [],
        "total_s": None,
        "maxrss_kb": None,
        "error": None,
    }
    try:
        try:
            import paddleocr
            report["paddleocr_version"] = paddleocr.__version__
        except Exception:
            pass
        try:
            import paddle
            report["paddle_version"] = paddle.__version__
        except Exception:
            pass

        with open(args.path, "rb") as f:
            pdf_bytes = f.read()
        pdf = args.path.lower().endswith(".pdf")
        full = ""
        if not pdf:
            # PNG langsung
            t0 = time.perf_counter()
            text = oe.ocr_engine(args.engine, pdf_bytes)
            report["total_s"] = round(time.perf_counter() - t0, 3)
            report["page_chars"] = [len(text)]
            report["per_page_s"] = [report["total_s"]]
            full = text
        else:
            # model init (lazy) diukur eksplisit (hanya untuk paddle; engine
            # lain init saat ocr_engine pertama dipanggil)
            if args.engine == "paddle":
                t0 = time.perf_counter()
                oe._get_paddle()
                report["model_init_s"] = round(time.perf_counter() - t0, 2)
            texts = []
            for png in _render_pages(pdf_bytes, args.zoom):
                if args.max_side > 0:
                    png = _downscale(png, args.max_side)
                t = time.perf_counter()
                text = oe.ocr_engine(args.engine, png)
                report["per_page_s"].append(round(time.perf_counter() - t, 3))
                report["page_chars"].append(len(text))
                texts.append(text)
                del text, png
            report["total_s"] = round(sum(report["per_page_s"]), 3)
            full = "\n".join(texts)
        report["text_preview"] = full[:400]
        if args.full_text:
            report["text"] = full
        report["maxrss_kb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except MemoryError:
        report["status"] = "memory_error"
        report["error"] = "MemoryError (RLIMIT_AS) — cap virtual memory terlampaui"
    except Exception as e:  # noqa: BLE001
        report["status"] = "error"
        report["error"] = f"{type(e).__name__}: {e}"
    finally:
        print(json.dumps(report))  # compact single-line — parent parse per-baris
    return 0 if report["status"] == "ok" else 42


def _extract_json(text: str) -> dict | None:
    """Ambil objek JSON utuh dari teks yang mungkin mengandung noise
    (progress bar \r / multi-line). Ambil `{` pertama s/d `}` terakhir."""
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _parent(args) -> int:
    python = sys.executable
    child_args = [
        python, os.path.abspath(__file__),
        "--path", args.path, "--engine", args.engine,
        "--zoom", str(args.zoom), "--max-side", str(args.max_side),
        "--threads", str(args.threads), "--batch", str(args.batch),
        "--mem-cap-gb", str(args.mem_cap_gb),
    ]
    if args.full_text:
        child_args.append("--full-text")
    env = dict(os.environ)
    env[CHILD_ENV] = "1"
    cap_kb = int(args.mem_cap_gb * 1024 ** 2)
    proc = subprocess.Popen(child_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    out_chunks = []
    peak_kb = 0
    killed_by_watchdog = False
    try:
        while True:
            line = proc.stdout.readline()
            if line:
                out_chunks.append(line)
            if line == b"" and proc.poll() is not None:
                break
            try:
                with open(f"/proc/{proc.pid}/status") as f:
                    for l in f:
                        if l.startswith("VmRSS:"):
                            rss_kb = int(l.split()[1])
                            if rss_kb > peak_kb:
                                peak_kb = rss_kb
                            if rss_kb > cap_kb:
                                killed_by_watchdog = True
                                proc.kill()
                                out_chunks.append(b'{"status":"watchdog_kill","error":"RSS melewati cap"}\n')
                            break
            except (FileNotFoundError, ProcessLookupError):
                pass
            if killed_by_watchdog:
                proc.wait()
                break
    finally:
        stderr = proc.stderr.read().decode(errors="replace")
    child_out = b"".join(out_chunks).decode(errors="replace").strip()
    result: dict = _extract_json(child_out) or {}
    if not result:
        result = {"status": "no_json", "error": child_out[:500] or "child tidak output JSON"}
    result["parent_peak_rss_kb"] = peak_kb
    result["watchdog_kill"] = killed_by_watchdog
    result["exit_code"] = proc.returncode
    if killed_by_watchdog:
        result["status"] = "watchdog_kill"
    result["stderr_tail"] = stderr[-1200:]
    print(json.dumps(result))  # compact — diparse per-baris oleh pemanggil
    return 1 if result["status"] not in ("ok",) else 0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--path", required=True, help="file PDF/PNG utk di-probe")
    p.add_argument("--engine", default="paddle", choices=["paddle", "rapid", "rapid_tess", "tess", "easy"])
    p.add_argument("--zoom", type=float, default=3.0)
    p.add_argument("--max-side", type=int, default=0, help="0 = tanpa downscale; >0 = cap sisi terpanjang px")
    p.add_argument("--threads", type=int, default=4)
    p.add_argument("--batch", type=int, default=4)
    p.add_argument("--mem-cap-gb", type=float, default=2.5)
    p.add_argument("--full-text", action="store_true", help="sertakan teks OCR penuh di JSON (untuk benchmark_ocr per-cert)")
    args = p.parse_args()
    if args.engine != "paddle" and args.threads == 4:
        args.threads = 1
    if os.environ.get(CHILD_ENV):
        sys.exit(_child(args))
    sys.exit(_parent(args))


if __name__ == "__main__":
    main()
