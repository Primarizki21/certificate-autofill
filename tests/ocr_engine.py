"""OCR engine seam for OCR experiments (handoff v9 §2). EXPERIMENT ONLY.

Tidak dipakai oleh pipeline produksi (`backend/app/services/ocr_fallback.py`
tetap otoritatif). Harness ini menyamakan antarmuka semua engine agar
perbandingan OCR (baseline vs trial PaddleOCR) adil di `tests/benchmark_ocr.py`.

Engine:
- `rapid`   : RapidOCR (onnxruntime) — bagian baseline produksi
- `tess`    : Tesseract — bagian baseline produksi (perlu binary `tesseract`)
- `paddle`  : PaddleOCR 3.x default (PP-OCRv5) — kandidat pengganti RapidOCR
- `rapid_tess` : gabungan RapidOCR + Tesseract (mencerminkan baseline produksi)

Semua engine menerima PNG bytes dan mengembalikan teks baris-per-baris.
Pembuatan PNG dari PDF ada di `render_pdf_pages_to_png_bytes` (pdf_fast_path,
zoom default 3.0 agar konsisten dengan produksi). PNG asli (4 sertifikat)
diteruskan langsung tanpa render.

Run via ephemeral env agar tidak menyentuh lockfile produksi:
  uv run --with paddlepaddle --with paddleocr python -m tests.ocr_engine
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from io import BytesIO
from typing import Callable, Optional

from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.pdf_fast_path import render_pdf_pages_to_png_bytes

ZOOM = 3.0

# Sertifikat dianggap "scan" bila teks embedded PyMuPDF <= MIN_EMBEDDED_CHARS
# (konsisten dgn handoff: 25 berteks embedded / 49 scan). PNG selalu scan.
MIN_EMBEDDED_CHARS = 60

# key engine -> (nama lengkap, apakah wajib dipasang)
ENGINE_INFO: dict[str, tuple[str, bool]] = {
    "rapid": ("rapidocr-onnxruntime", True),
    "tess": ("tesseract binary", True),
    "paddle": ("paddleocr (uv run --with)", True),
    "rapid_tess": ("rapidocr + tesseract", True),
}


def _tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def _load_rapidocr():
    try:
        from rapidocr_onnxruntime import RapidOCR
        return RapidOCR()
    except Exception:
        try:
            from rapidocr import RapidOCR
            return RapidOCR()
        except Exception:
            return None


_rapid_engine = None


def _get_rapid():
    global _rapid_engine
    if _rapid_engine is None:
        _rapid_engine = _load_rapidocr()
    return _rapid_engine


_paddle_engine = None
_easy_engine = None

# Knob global utk probe (tests/paddle_probe_safe.py): set SEBELUM pemakaian.
# GPU opsional — user prioritas CPU; GPU hanya dievaluasi sebagai bukti.
PADDLE_CPU_THREADS = 4
PADDLE_REC_BATCH = 4
EASY_GPU = False


def _paddle_major_version() -> int:
    from paddleocr import __version__
    try:
        return int(str(__version__).split(".")[0])
    except Exception:
        return 3


def _get_paddle():
    global _paddle_engine
    if _paddle_engine is None:
        from paddleocr import PaddleOCR
        if _paddle_major_version() >= 3:
            # v3.x: default pipeline PP-OCRv6. `enable_mkldnn=False` karena
            # oneDNN CPU crash di paddlepaddle 3.3 (ConvertPirAttribute2Runtime
            # Attribute NotImplemented). Thread/batch dibatasi utk WSL 7GB.
            _paddle_engine = PaddleOCR(
                lang="en",
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=True,
                enable_mkldnn=False,
                cpu_threads=PADDLE_CPU_THREADS,
                text_recognition_batch_size=PADDLE_REC_BATCH,
            )
        else:
            # v2.x: API lama. Batasi thread via paddle API bila ada; fallback
            # OMP_NUM_THREADS (diset probe/harness). use_gpu=False (host CPU).
            import paddle as _pd
            if hasattr(_pd, "set_num_threads"):
                _pd.set_num_threads(PADDLE_CPU_THREADS)
            kwargs = dict(use_angle_cls=True, lang="en", show_log=False, use_gpu=False)
            try:
                _paddle_engine = PaddleOCR(**kwargs)
            except TypeError:
                kwargs.pop("use_gpu", None)
                kwargs.pop("use_angle_cls", None)
                _paddle_engine = PaddleOCR(**kwargs)
    return _paddle_engine


def _read_image(image_bytes: bytes) -> Image.Image:
    return Image.open(BytesIO(image_bytes)).convert("RGB")


def ocr_rapid(image_bytes: bytes) -> str:
    engine = _get_rapid()
    if engine is None:
        return ""
    try:
        result, _ = engine(image_bytes)
    except Exception:
        return ""
    if not result:
        return ""
    lines = [str(item[1]) for item in result if len(item) >= 2]
    return "\n".join(lines)


def ocr_tess(image_bytes: bytes) -> str:
    if not _tesseract_available():
        raise RuntimeError("tesseract binary tidak terpasang di host ini")
    import pytesseract
    image = _read_image(image_bytes)
    seen: set[str] = set()
    lines: list[str] = []
    configs = ["", "--psm 6", "--psm 11"]
    for config in configs:
        try:
            text = pytesseract.image_to_string(image, lang="ind+eng", config=config).strip()
        except Exception:
            text = pytesseract.image_to_string(image, lang="eng", config=config).strip()
        for line in text.splitlines():
            clean = line.strip()
            if clean and clean not in seen:
                seen.add(clean)
                lines.append(clean)
    return "\n".join(lines)


def ocr_paddle(image_bytes: bytes) -> str:
    engine = _get_paddle()
    # PaddleOCR `ocr()` hanya menerima numpy.ndarray / path file — tulis PNG
    # sementara lalu beri path (praktis & deterministik untuk seluruh halaman).
    with tempfile.TemporaryDirectory() as td:
        tmp = os.path.join(td, "page.png")
        with open(tmp, "wb") as f:
            f.write(image_bytes)
        result = engine.ocr(tmp)
    lines: list[str] = []
    for page in result or []:
        # v3.x: page = dict {rec_texts: [...], rec_scores: [...], dt_polys: [...]}
        if isinstance(page, dict) and page.get("rec_texts"):
            lines.extend(str(t) for t in page["rec_texts"] if t is not None)
            continue
        # fallback format lama: page = list of [box, (text, score)] / [box, text, score]
        for item in page or []:
            if isinstance(item, (list, tuple)):
                if len(item) >= 2 and isinstance(item[1], (list, tuple)) and item[1]:
                    lines.append(str(item[1][0]))
                elif len(item) >= 3:
                    lines.append(str(item[1]))
    return "\n".join(lines)


def merge_unique_lines(texts: list[str]) -> str:
    seen: set[str] = set()
    lines: list[str] = []
    for text in texts:
        for line in text.splitlines():
            clean = line.strip()
            if clean and clean not in seen:
                seen.add(clean)
                lines.append(clean)
    return "\n".join(lines)


def _get_easy():
    global _easy_engine
    if _easy_engine is None:
        import easyocr
        _easy_engine = easyocr.Reader(["en"], gpu=EASY_GPU, verbose=False)
    return _easy_engine


def ocr_easy(image_bytes: bytes) -> str:
    """EasyOCR (torch) — engine berbeda dari baseline RapidOCR/Tesseract."""
    import numpy as np
    reader = _get_easy()
    img = np.array(_read_image(image_bytes))
    result = reader.readtext(img, detail=0, paragraph=False)
    return "\n".join(str(t) for t in result if str(t).strip())


# engine key -> fungsi OCR per PNG
ENGINES: dict[str, Callable[[bytes], str]] = {
    "rapid": ocr_rapid,
    "tess": ocr_tess,
    "paddle": ocr_paddle,
    "easy": ocr_easy,
}


def ocr_engine(key: str, image_bytes: bytes) -> str:
    """OCR satu halaman PNG. `rapid_tess` = merge rapid + tess (baseline produksi)."""
    if key == "rapid_tess":
        parts = []
        r = ocr_rapid(image_bytes)
        if r.strip():
            parts.append(r)
        if _tesseract_available():
            try:
                t = ocr_tess(image_bytes)
            except Exception:
                t = ""
            if t.strip():
                parts.append(t)
        return merge_unique_lines(parts)
    if key not in ENGINES:
        raise ValueError(f"engine tak dikenal: {key} (pilih {sorted(ENGINES) + ['rapid_tess']})")
    return ENGINES[key](image_bytes)


def pdf_to_page_images(pdf_bytes: bytes) -> list[bytes]:
    return render_pdf_pages_to_png_bytes(pdf_bytes, zoom=ZOOM)


def ocr_pdf(key: str, pdf_bytes: bytes, zoom: float = ZOOM) -> str:
    """OCR seluruh PDF: render halaman SATU PER SATU lalu OCR, free tiap
    halaman. WSL 7GB — jangan pernah menahan semua page image sekaligus
    (OOM). Antar halaman tetap digabung."""
    import fitz
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    texts: list[str] = []
    try:
        matrix = fitz.Matrix(zoom, zoom)
        for page in doc:
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            png = pix.tobytes("png")
            del pix
            t = ocr_engine(key, png)
            del png
            if t.strip():
                texts.append(t)
    finally:
        doc.close()
    return "\n".join(texts).strip()


def ocr_path(key: str, path: str, zoom: float = ZOOM) -> str:
    """OCR file path; PNG diteruskan, selain itu dianggap PDF."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".png":
        with open(path, "rb") as f:
            return ocr_engine(key, f.read())
    with open(path, "rb") as f:
        return ocr_pdf(key, f.read(), zoom=zoom)


def embedded_char_count(path: str) -> int:
    """Jumlah karakter teks embedded PyMuPDF (0 untuk PNG = scan)."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".png":
        return 0
    import fitz
    doc = fitz.open(path)
    try:
        return len("".join(p.get_text("text") or "" for p in doc).strip())
    finally:
        doc.close()


def embedded_text(path: str) -> str:
    """Teks embedded PyMuPDF ("" untuk PNG / tanpa teks)."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".png":
        return ""
    import fitz
    doc = fitz.open(path)
    try:
        return "\n".join(p.get_text("text") or "" for p in doc).strip()
    finally:
        doc.close()


def classify_manifest(manifest: dict[str, str]) -> dict[str, dict]:
    """Klasifikasikan tiap stem: embedded vs scan (lihat MIN_EMBEDDED_CHARS)."""
    out = {}
    for stem, path in manifest.items():
        n = embedded_char_count(path)
        out[stem] = {"path": path, "chars": n, "scan": n <= MIN_EMBEDDED_CHARS}
    return out


def demo() -> None:
    """Self-check: merge + dispatch bekerja, dan seam OCR jalan pada aset nyata.

    Seam diuji dengan RapidOCR pada PNG asli dari manifest (tanpa model
    download tambahan). Trial lengkap dijalankan oleh tests/benchmark_ocr.py.
    """
    assert merge_unique_lines(["A", "B", "A", "B"]) == "A\nB"
    try:
        ocr_engine("nope", b"")
        raise AssertionError("engine tak dikenal harus error")
    except ValueError:
        pass
    if not _tesseract_available():
        try:
            ocr_engine("tess", b"")
            raise AssertionError("tesseract harus error bila binary absen")
        except RuntimeError:
            pass
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    manifest = os.path.join(root, "tests", "layout_manifest.json")
    if not os.path.exists(manifest):
        print("ok: ocr_engine (manifest absent, seam skippable)")
        return
    import json
    with open(manifest) as f:
        m = json.load(f)
    png = next((p for p in m.values() if p.lower().endswith(".png")), None)
    if not png:
        print("ok: ocr_engine (no png asset)")
        return
    text = ocr_path("rapid", os.path.join(root, png))
    assert text.strip(), "rapid harus menghasilkan teks pada PNG asli"
    print(f"ok: ocr_engine | tesseract_available={_tesseract_available()} | rapid_chars={len(text)}")


if __name__ == "__main__":
    demo()
