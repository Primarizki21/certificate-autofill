"""High-DPI Region Crop Module for Certificate Number OCR (NC-001 Pattern).

When whole-page OCR produces low confidence, missing numbers, or corrupted Roman numerals,
this module locates the bounding box around 'NOMOR' / 'NO.' / certificate pattern on the page,
re-renders that specific region at 6.0x zoom (super-high DPI / 300+ DPI), and runs targeted OCR.
"""

import re
from io import BytesIO

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    import pytesseract
except ImportError:
    pytesseract = None

from app.services.field_extractor import extract_certificate_number

_NUMBER_KEYWORD_RE = re.compile(r"\b(?:NOMOR|NO\.?|NUMBER|SERTIFIKAT)\b", re.IGNORECASE)
_STRICT_NUMBER_RE = re.compile(
    r"\b[0-9]{1,5}\s*/\s*[A-Z0-9.\-/]+\s*/\s*[0-9]{4}\b", re.IGNORECASE
)


def crop_and_ocr_number_region(
    pdf_bytes: bytes,
    zoom: float = 6.0,
) -> str | None:
    """Locate number line/region, re-render at high zoom, and extract certificate number."""
    if not pdf_bytes or not fitz:
        return None

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        if len(doc) == 0:
            return None
        page = doc[0]

        # 1. Search text rects for 'NOMOR' or 'No.'
        target_rect = None
        for kw in ["NOMOR", "Nomor", "NO.", "No.", "No", "NUMBER"]:
            rects = page.search_for(kw)
            if rects:
                target_rect = rects[0]
                break

        # 2. If not found via search_for, search text blocks
        if not target_rect:
            blocks = page.get_text("blocks")
            for b in blocks:
                text = b[4]
                if _NUMBER_KEYWORD_RE.search(text) or _STRICT_NUMBER_RE.search(text):
                    target_rect = fitz.Rect(b[0], b[1], b[2], b[3])
                    break

        if not target_rect:
            doc.close()
            return None

        # 3. Expand bounding box to capture adjacent or multiline numbers
        page_rect = page.rect
        w = target_rect.width
        h = target_rect.height
        pad_x = max(20.0, 0.1 * w)
        pad_y = max(10.0, 0.2 * h)

        x0 = max(0.0, target_rect.x0 - pad_x)
        y0 = max(0.0, target_rect.y0 - pad_y)
        x1 = min(page_rect.width, target_rect.x1 + pad_x + 350.0)
        y1 = min(page_rect.height, target_rect.y1 + pad_y + 60.0)

        clip_rect = fitz.Rect(x0, y0, x1, y1)

        # 4. Re-render region at 6.0x zoom
        matrix = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=matrix, clip=clip_rect, alpha=False)
        png_bytes = pix.tobytes("png")
        doc.close()

        # 5. Targeted OCR
        if pytesseract and Image:
            img = Image.open(BytesIO(png_bytes))
            ocr_text = pytesseract.image_to_string(img, config="--psm 6")
            num = extract_certificate_number(ocr_text)
            if num:
                return num

        return None
    except Exception:
        return None
