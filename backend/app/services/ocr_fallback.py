import re
from io import BytesIO
from PIL import Image
import fitz
import pytesseract

from app.config import settings
from app.services.field_extractor import extract_certificate_number
from app.services.pdf_fast_path import render_pdf_pages_to_png_bytes

ZOOM = 3.0  # render halaman (konsisten dgn eksperimen)
CRENDER_ZOOM = 6.0  # NC-001: re-render region nomor di zoom tinggi (piksel nyata)
_KEYWORD_RE = re.compile(r"\bNOMOR\b|\bNO\.\b|\bNUMBER\b", re.I)
_NUMBER_LINE_RE = re.compile(r"[0-9]{1,6}\s*/\s*[A-Z0-9]", re.I)


def extract_text_with_ocr(pdf_bytes: bytes) -> str:
    # Pakai zoom lebih tinggi agar teks kecil seperti tanggal pelaksanaan
    # di bagian bawah sertifikat lebih sering terbaca OCR.
    page_images = render_pdf_pages_to_png_bytes(pdf_bytes, zoom=ZOOM)
    all_text: list[str] = []

    rapidocr_engine = _load_rapidocr()
    for image_bytes in page_images:
        # Jangan berhenti di RapidOCR saja. Pada beberapa sertifikat, RapidOCR
        # membaca nama/nomor tetapi melewatkan tanggal. Gabungkan RapidOCR +
        # Tesseract agar field tanggal punya peluang terbaca lebih tinggi.
        page_texts: list[str] = []
        if rapidocr_engine is not None:
            rapid_text = _ocr_with_rapidocr(rapidocr_engine, image_bytes)
            if rapid_text.strip():
                page_texts.append(rapid_text)
        tess_text = _ocr_with_tesseract(image_bytes)
        if tess_text.strip():
            page_texts.append(tess_text)
        all_text.append(merge_unique_lines(page_texts))

    full = "\n".join(all_text).strip()

    # NC-001 (disagreement): re-OCR region nomor (re-render PDF zoom tinggi);
    # prepend `NOMOR : <crop>` HANYA bila nomor crop beda dari baseline.
    # Default OFF — diukur 0/18 gain utk cert nomor-hilang, dan varian penuh
    # ~+2-10s/cert. Aktifkan via ENABLE_OCR_NUMBER_2PASS=true utk gain +3pt
    # nomor (validasi eksperimen NC-001) dengan cost tsb.
    if (
        settings.enable_ocr_number_2pass
        and rapidocr_engine is not None
        and page_images
    ):
        base_num = extract_certificate_number(full)
        recovered = _recover_number_region(pdf_bytes, page_images[0], rapidocr_engine)
        crop_num = extract_certificate_number(re.sub(r"\s+", "", recovered))
        if crop_num and crop_num != base_num:
            full = f"NOMOR : {crop_num}\n{full}".strip()

    return full


def _find_number_item(items: list) -> list | None:
    """Anchor semantik (tanpa koordinat hardcode): baris ber-keyword
    NOMOR/NO./NUMBER dulu, fallback baris ber-pola nomor `NN/…`."""
    for item in items:
        if _KEYWORD_RE.search(str(item[1] or "")):
            return item
    for item in items:
        if _NUMBER_LINE_RE.search(str(item[1] or "")):
            return item
    return None


def _recover_number_region(pdf_bytes: bytes, page_image: bytes, rapid_engine) -> str:
    """Crop region baris nomor (dari bbox RapidOCR) -> re-render PDF zoom
    CRENDER_ZOOM (piksel nyata utk scan res tinggi) -> re-OCR rapid_tess."""
    try:
        result, _ = rapid_engine(page_image)
    except Exception:
        return ""
    if not result:
        return ""
    item = _find_number_item(result)
    if item is None:
        return ""
    box = item[0]
    xs = [p[0] for p in box]
    ys = [p[1] for p in box]
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    w = x1 - x0
    h = y1 - y0
    pad = max(5, int(0.05 * w))
    x0 = max(0, x0 - pad)
    y0 = max(0, y0 - pad)
    x1 = x1 + pad + int(0.20 * w)  # angka bisa di kanan label
    y1 = y1 + pad + int(1.2 * h)  # angka bisa di baris berikut
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception:
        return ""
    try:
        page = doc[0]
        pw, ph = page.rect.width, page.rect.height
        rect = fitz.Rect(
            max(0.0, x0 / ZOOM), max(0.0, y0 / ZOOM),
            min(pw, x1 / ZOOM), min(ph, y1 / ZOOM),
        )
        pix = page.get_pixmap(matrix=fitz.Matrix(CRENDER_ZOOM, CRENDER_ZOOM), clip=rect, alpha=False)
        region = pix.tobytes("png")
        del pix
    except Exception:
        return ""
    finally:
        doc.close()
    parts: list[str] = []
    r = _ocr_with_rapidocr(rapid_engine, region)
    if r.strip():
        parts.append(r)
    t = _ocr_with_tesseract(region)
    if t.strip():
        parts.append(t)
    return "\n".join(parts)


def _self_check() -> None:
    items = [
        ([[0, 0], [200, 0], [200, 20], [0, 20]], "NOMOR : 106/STF.E/HOLOGY7.0/X1T/2024", 0.9),
        ([[0, 30], [200, 30], [200, 50], [0, 50]], "SERTIFIKAT PELATIHAN", 0.9),
    ]
    assert _find_number_item(items)[1].startswith("NOMOR"), "anchor keyword harus menang"
    n = extract_certificate_number(re.sub(r"\s+", "", "106 / STF.E / X1T / 2024"))
    assert n == "106/STF.E/X1T/2024", n
    # disagreement: crop beda dari baseline -> menang; crop sama -> baseline utuh
    from app.services.field_extractor import extract_certificate_number as _E
    base = "SERTIFIKAT A\nNOMOR: 106/STF.E/X1/2024"
    crop = "106 / STF.E / HOLOGY 7.0 / X1T / 2024"
    crop_num = _E(re.sub(r"\s+", "", crop))
    full = "NOMOR : " + crop_num + "\n" + base
    assert _E(full) == "106/STF.E/HOLOGY7.0/X1T/2024", "crop beda harus menang"
    assert _E(base + "\n" + crop) == "106/STF.E/X1/2024", "nomor baseline tetap"
    print("ok: ocr_fallback number 2-pass self-check")


if __name__ == "__main__":
    _self_check()


def merge_unique_lines(texts: list[str]) -> str:
    lines: list[str] = []
    seen: set[str] = set()
    for text in texts:
        for line in text.splitlines():
            clean = line.strip()
            if clean and clean not in seen:
                seen.add(clean)
                lines.append(clean)
    return "\n".join(lines)


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


def _ocr_with_rapidocr(engine, image_bytes: bytes) -> str:
    try:
        result, _ = engine(image_bytes)
        if not result:
            return ""
        lines = []
        for item in result:
            if len(item) >= 2:
                lines.append(str(item[1]))
        return "\n".join(lines)
    except Exception:
        return ""


def _ocr_with_tesseract(image_bytes: bytes) -> str:
    try:
        image = Image.open(BytesIO(image_bytes))
        # Beberapa sertifikat hasil scan membuat tanggal hilang pada mode OCR default.
        # Gabungkan beberapa PSM agar teks kecil seperti tanggal pelaksanaan lebih sering tertangkap.
        configs = ["", "--psm 6", "--psm 11"]
        lines: list[str] = []
        seen: set[str] = set()
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
    except Exception:
        return ""
