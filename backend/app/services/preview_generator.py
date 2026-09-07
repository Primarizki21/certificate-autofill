import logging
import fitz

logger = logging.getLogger("certificate-preview-generator")


def generate_compressed_preview(pdf_bytes: bytes, dpi: int = 110, max_size_bytes: int = 150_000) -> bytes | None:
    """Generate a lightweight compressed JPEG preview of the first page.

    Invariants:
    - Never raises: failure returns None so the main extraction pipeline is never interrupted.
    - Resolves first page at dpi=110 (~900x1300 px), keeping file size strictly bounded (~30-60 KB).
    - If rendered bytes exceed max_size_bytes, downsamples at dpi=72.
    """
    if not pdf_bytes:
        return None
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            if len(doc) == 0:
                return None
            page = doc[0]
            # Iterative downsampling down to 50 DPI to enforce strict max_size_bytes cap
            for target_dpi in [dpi, 72, 50]:
                pix = page.get_pixmap(dpi=target_dpi)
                jpeg_bytes = pix.tobytes("jpeg")
                if len(jpeg_bytes) <= max_size_bytes:
                    return jpeg_bytes

            logger.warning(
                "Certificate preview exceeded strict cap %d bytes even at 50 DPI (%d bytes); omitted to preserve database bounds.",
                max_size_bytes,
                len(jpeg_bytes),
            )
            return None
        finally:
            doc.close()
    except Exception as exc:
        logger.warning("Failed to generate certificate preview image: %s", exc)
        return None
