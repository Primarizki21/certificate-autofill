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


def render_pdf_pages_to_png_bytes(
    pdf_bytes: bytes,
    zoom: float = 3.0,
    max_pages: int | None = None,
) -> list[bytes]:
    # Batasi jumlah halaman render raster untuk mencegah OOM dari PDF multi-halaman.
    limit = max_pages
    if limit is None:
        try:
            from app.config import settings
            limit = settings.max_pdf_pages
        except Exception:
            limit = 3

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    rendered: list[bytes] = []
    try:
        for idx, page in enumerate(doc):
            if limit is not None and limit > 0 and idx >= limit:
                break
            rect = page.rect
            long_edge = max(rect.width, rect.height)
            max_allowed = 2500  # Standar 300 DPI long-edge; mencegah OOM pada PDF native raksasa
            scale = min(max_allowed / long_edge, zoom) if long_edge > 0 else zoom
            matrix = fitz.Matrix(scale, scale)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            rendered.append(pix.tobytes("png"))
            del pix
        return rendered
    finally:
        doc.close()
