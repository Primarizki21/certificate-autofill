from dataclasses import dataclass
import io
from typing import Any
import fitz
from PIL import Image


@dataclass
class FastPathResult:
    text: str
    page_count: int


@dataclass
class PageImageBuffer:
    """Zero-copy / in-memory buffer representation of a rendered page or uploaded image."""
    samples: bytes
    width: int
    height: int
    mode: str = "RGB"  # "RGB" or "L"
    _png_cache: bytes | None = None

    def to_png_bytes(self) -> bytes:
        """Lazy encode to PNG bytes when backward compatibility or bytes output is needed."""
        if self._png_cache is not None:
            return self._png_cache
        pil_img = self.to_pil()
        out = io.BytesIO()
        pil_img.save(out, format="PNG")
        self._png_cache = out.getvalue()
        return self._png_cache

    def to_pil(self, mode: str | None = None) -> Image.Image:
        """Convert directly to PIL Image in memory without intermediate PNG encode/decode."""
        img = Image.frombytes(self.mode, (self.width, self.height), self.samples)
        if mode and mode != self.mode:
            return img.convert(mode)
        return img

    def to_bgr_ndarray(self) -> Any:
        """Zero-copy view converted to BGR NumPy array for OpenCV / RapidOCR."""
        import numpy as np
        channels = 3 if self.mode == "RGB" else 1
        arr = np.frombuffer(self.samples, dtype=np.uint8).reshape(self.height, self.width, channels)
        if self.mode == "RGB":
            return arr[:, :, ::-1]
        return arr


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


def render_pdf_pages_to_image_buffers(
    pdf_bytes: bytes,
    zoom: float = 3.0,
    max_pages: int | None = None,
) -> list[PageImageBuffer]:
    # Image input fast-circuit: if already PNG or JPEG or WEBP, convert directly to PageImageBuffer
    if (
        pdf_bytes.startswith(b"\x89PNG\r\n\x1a\n")
        or pdf_bytes.startswith(b"\xff\xd8\xff")
        or (len(pdf_bytes) >= 12 and pdf_bytes.startswith(b"RIFF") and pdf_bytes[8:12] == b"WEBP")
    ):
        with Image.open(io.BytesIO(pdf_bytes)) as img:
            rgb_img = img.convert("RGB")
            return [
                PageImageBuffer(
                    samples=rgb_img.tobytes(),
                    width=rgb_img.width,
                    height=rgb_img.height,
                    mode="RGB",
                    _png_cache=pdf_bytes if pdf_bytes.startswith(b"\x89PNG\r\n\x1a\n") else None,
                )
            ]

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

    rendered: list[PageImageBuffer] = []
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
            rendered.append(
                PageImageBuffer(
                    samples=bytes(pix.samples),
                    width=pix.width,
                    height=pix.height,
                    mode="RGB",
                )
            )
            del pix
        return rendered
    finally:
        doc.close()


def render_pdf_pages_to_png_bytes(
    pdf_bytes: bytes,
    zoom: float = 3.0,
    max_pages: int | None = None,
) -> list[bytes]:
    buffers = render_pdf_pages_to_image_buffers(pdf_bytes, zoom=zoom, max_pages=max_pages)
    return [b.to_png_bytes() for b in buffers]
