from io import BytesIO
from PIL import Image
import pytesseract

from app.services.pdf_fast_path import render_pdf_pages_to_png_bytes


def extract_text_with_ocr(pdf_bytes: bytes) -> str:
    # Pakai zoom lebih tinggi agar teks kecil seperti tanggal pelaksanaan
    # di bagian bawah sertifikat lebih sering terbaca OCR.
    page_images = render_pdf_pages_to_png_bytes(pdf_bytes, zoom=3.0)
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

    return "\n".join(all_text).strip()


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
