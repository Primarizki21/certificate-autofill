from dataclasses import dataclass
import fitz


@dataclass
class FastPathResult:
    text: str
    page_count: int


def extract_text_with_pymupdf(pdf_bytes: bytes) -> FastPathResult:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    texts: list[str] = []
    try:
        for page in doc:
            texts.append(page.get_text("text") or "")
        return FastPathResult(text="\n".join(texts).strip(), page_count=doc.page_count)
    finally:
        doc.close()


def render_pdf_pages_to_png_bytes(pdf_bytes: bytes, zoom: float = 2.0) -> list[bytes]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    rendered: list[bytes] = []
    try:
        matrix = fitz.Matrix(zoom, zoom)
        for page in doc:
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            rendered.append(pix.tobytes("png"))
        return rendered
    finally:
        doc.close()
