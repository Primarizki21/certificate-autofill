from dataclasses import dataclass
import fitz


@dataclass
class FastPathResult:
    text: str
    page_count: int


def extract_text_with_pymupdf(pdf_bytes: bytes) -> FastPathResult:
    if not pdf_bytes.startswith(b"%PDF-"):
        return FastPathResult(text="", page_count=1)
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
):
    # Image input fast-circuit: if already PNG or JPEG, return directly or converted
    if pdf_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return [pdf_bytes]
    if pdf_bytes.startswith(b"\xff\xd8\xff") or (len(pdf_bytes) >= 12 and pdf_bytes.startswith(b"RIFF") and pdf_bytes[8:12] == b"WEBP"):
        import io
        from PIL import Image
        with Image.open(io.BytesIO(pdf_bytes)) as img:
            out = io.BytesIO()
            if img.mode not in ("RGB", "RGBA", "L"):
                img.convert("RGB").save(out, format="PNG")
            else:
                img.save(out, format="PNG")
            return [out.getvalue()]

    # Batasi jumlah halaman render raster untuk mencegah OOM dari PDF multi-halaman.
    limit = max_pages
    if limit is None:
        try:
            from app.config import settings
            limit = settings.max_pdf_pages
        except Exception:
            limit = 3
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception:
        return []

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
