"""Security Guard Service for PDF and Image uploads.

Provides deep defense-in-depth inspection:
1. Magic bytes validation (anti-mime spoofing & polyglots)
2. File extension consistency
3. Image decompression bomb prevention & pixel flood limits
4. Image dimension & aspect ratio boundary enforcement (anti-troll micro/macro)
5. EXIF and metadata sanitization (anti-injection & privacy)
6. PDF page count enforcement (anti-page bomb DoS)
7. PDF encryption/password detection
8. PDF malicious active content inspection (/JS, /JavaScript, /Launch, /EmbeddedFiles)
9. PDF canvas bomb detection (anti-OOM raster render)
"""

from __future__ import annotations

import hashlib
import io
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import fitz
from PIL import Image

from app.config import settings

logger = logging.getLogger("security_guard")

# Set global Pillow decompression bomb limit
Image.MAX_IMAGE_PIXELS = settings.max_image_pixels

# Allowed file extensions & MIME types
SUPPORTED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}

MIME_TYPE_BY_FORMAT: dict[str, str] = {
    "pdf": "application/pdf",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}

# Magic signatures
PDF_MAGIC = b"%PDF-"
JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class SecurityValidationError(ValueError):
    """Raised when an uploaded file violates security or integrity guards."""

    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


@dataclass(frozen=True)
class ValidatedDocument:
    file_type: Literal["pdf", "jpeg", "png", "webp"]
    content_type: str
    cleaned_bytes: bytes
    page_count: int
    dimensions: tuple[int, int] | None
    checksum_sha256: str
    original_size: int
    cleaned_size: int


def detect_file_type_from_magic_bytes(content: bytes) -> Literal["pdf", "jpeg", "png", "webp"]:
    """Detect format strictly using magic bytes header."""
    if len(content) < 8:
        raise SecurityValidationError(
            "Ukuran file terlalu kecil atau rusak.",
            code="CORRUPTED_FILE",
        )

    if content.startswith(PDF_MAGIC):
        return "pdf"
    if content.startswith(JPEG_MAGIC):
        return "jpeg"
    if content.startswith(PNG_MAGIC):
        return "png"
    if len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "webp"

    raise SecurityValidationError(
        "Format file tidak valid atau tidak didukung (magic bytes tidak cocok). Hanya menerima PDF, JPG, JPEG, PNG, dan WEBP.",
        code="UNSUPPORTED_OR_SPOOFED_TYPE",
    )


def validate_extension_match(filename: str, detected_type: str) -> None:
    """Ensure the file extension matches the detected magic bytes format."""
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise SecurityValidationError(
            f"Ekstensi file '{ext}' tidak diizinkan. Hanya menerima .pdf, .jpg, .jpeg, .png, dan .webp.",
            code="INVALID_EXTENSION",
        )

    expected_types: dict[str, set[str]] = {
        ".pdf": {"pdf"},
        ".jpg": {"jpeg"},
        ".jpeg": {"jpeg"},
        ".png": {"png"},
        ".webp": {"webp"},
    }
    if detected_type not in expected_types.get(ext, set()):
        raise SecurityValidationError(
            f"Ekstensi file '{ext}' tidak sesuai dengan isi dokumen asli ({detected_type}). Terdeteksi potensi manipulasi tipe file.",
            code="MIME_SPOOFING",
        )


def sanitize_and_validate_image(
    content: bytes,
    file_type: Literal["jpeg", "png", "webp"],
) -> tuple[bytes, tuple[int, int]]:
    """Validate image integrity, dimensions, aspect ratio, and re-encode to strip EXIF."""
    try:
        with Image.open(io.BytesIO(content)) as img:
            # Check decompression bomb limit
            try:
                img.load()
            except Image.DecompressionBombError as exc:
                raise SecurityValidationError(
                    "Terdeteksi potensi dekompresi berbahaya (pixel flood / decompression bomb).",
                    code="DECOMPRESSION_BOMB",
                ) from exc

            width, height = img.size

            # Check min dimensions (anti-troll micro icons)
            if width < settings.min_image_dimension or height < settings.min_image_dimension:
                raise SecurityValidationError(
                    f"Dimensi gambar ({width}x{height} px) terlalu kecil. Minimal {settings.min_image_dimension}x{settings.min_image_dimension} piksel.",
                    code="IMAGE_TOO_SMALL",
                )

            # Check max dimensions (anti-pixel flood)
            if width > settings.max_image_dimension or height > settings.max_image_dimension:
                raise SecurityValidationError(
                    f"Dimensi gambar ({width}x{height} px) melebihi batas maksimal {settings.max_image_dimension}x{settings.max_image_dimension} piksel.",
                    code="IMAGE_TOO_LARGE",
                )

            # Check aspect ratio (anti-banner troll: ratio must not exceed 5.0)
            ratio = max(width, height) / max(min(width, height), 1)
            if ratio > 5.0:
                raise SecurityValidationError(
                    f"Rasio aspek gambar abnormal ({ratio:.2f}:1). Sertifikat harus memiliki proporsi wajar.",
                    code="ASPECT_RATIO_ABNORMAL",
                )

            # Auto-downscale high-DPI scans (> 3500px on long edge, e.g. 600 DPI)
            max_edge = max(width, height)
            if max_edge > settings.auto_downscale_threshold:
                scale = settings.auto_downscale_target / max_edge
                new_w = max(settings.min_image_dimension, int(width * scale))
                new_h = max(settings.min_image_dimension, int(height * scale))
                logger.info(
                    "Auto-downscaling high-DPI image from %dx%d to %dx%d (target max edge: %d)",
                    width, height, new_w, new_h, settings.auto_downscale_target,
                )
                img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                width, height = img.size

            # Re-encode to completely strip EXIF metadata and active chunks
            out_buf = io.BytesIO()
            if file_type == "jpeg":
                if img.mode != "RGB":
                    clean_img = img.convert("RGB")
                else:
                    clean_img = img.copy()
                clean_img.save(out_buf, format="JPEG", quality=92, optimize=True)
            elif file_type == "png":
                if img.mode not in ("RGB", "RGBA", "L"):
                    clean_img = img.convert("RGBA" if "A" in img.mode else "RGB")
                else:
                    clean_img = img.copy()
                clean_img.save(out_buf, format="PNG", optimize=True)
            elif file_type == "webp":
                if img.mode not in ("RGB", "RGBA"):
                    clean_img = img.convert("RGBA" if "A" in img.mode else "RGB")
                else:
                    clean_img = img.copy()
                clean_img.save(out_buf, format="WEBP", quality=90, method=4)

            cleaned_bytes = out_buf.getvalue()
            return cleaned_bytes, (width, height)
    except SecurityValidationError:
        raise
    except Exception as exc:
        logger.warning("Image decoding failed: %s", exc)
        raise SecurityValidationError(
            "File gambar rusak atau tidak dapat didekode dengan aman.",
            code="CORRUPTED_IMAGE",
        ) from exc


def validate_pdf_security(content: bytes) -> tuple[int, tuple[int, int] | None]:
    """Inspect PDF for encryption, active scripts, embedded binaries, page count, and canvas bomb."""
    try:
        doc = fitz.open(stream=content, filetype="pdf")
    except Exception as exc:
        raise SecurityValidationError(
            "File PDF rusak atau tidak dapat dibaca.",
            code="CORRUPTED_PDF",
        ) from exc

    try:
        # 1. Check password encryption
        if doc.is_encrypted or doc.needs_pass:
            raise SecurityValidationError(
                "PDF terproteksi kata sandi dan tidak dapat diproses.",
                code="PDF_PASSWORD_PROTECTED",
            )

        # 2. Check page count limit (max 3 pages)
        page_count = doc.page_count
        if page_count < 1:
            raise SecurityValidationError(
                "PDF tidak memiliki halaman valid.",
                code="EMPTY_PDF",
            )
        if page_count > settings.max_pdf_pages:
            raise SecurityValidationError(
                f"Jumlah halaman PDF ({page_count}) melebihi batas maksimal {settings.max_pdf_pages} halaman.",
                code="PDF_TOO_MANY_PAGES",
            )

        # 3. Check embedded files / binary attachments
        if doc.embfile_count() > 0:
            raise SecurityValidationError(
                "PDF ditolak karena memuat lampiran file tersemat (embedded files).",
                code="PDF_EMBEDDED_FILES",
            )

        # 4. Check active scripts & dangerous objects in xrefs
        dangerous_keywords = ("/JavaScript", "/JS", "/Launch", "/EmbeddedFiles", "/RichMedia")
        for xref in range(1, doc.xref_length()):
            try:
                obj_str = doc.xref_object(xref)
                for kw in dangerous_keywords:
                    if kw in obj_str:
                        raise SecurityValidationError(
                            f"PDF ditolak karena memuat objek aktif/eksekusi berisiko ({kw}).",
                            code="PDF_ACTIVE_CONTENT",
                        )
            except SecurityValidationError:
                raise
            except Exception:
                # Malformed xref entry
                pass

        # 5. Check canvas dimension limits on all pages
        dimensions: tuple[int, int] | None = None
        for idx in range(page_count):
            rect = doc[idx].rect
            w, h = rect.width, rect.height
            if dimensions is None:
                dimensions = (int(w), int(h))

            if w > settings.max_pdf_canvas_dimension or h > settings.max_pdf_canvas_dimension:
                raise SecurityValidationError(
                    f"Halaman {idx + 1} PDF memiliki dimensi kanvas abnormal ({int(w)}x{int(h)} pt). Maksimal {settings.max_pdf_canvas_dimension} pt.",
                    code="PDF_CANVAS_BOMB",
                )

        return page_count, dimensions
    finally:
        doc.close()


def inspect_and_guard_upload(
    content: bytes,
    filename: str,
) -> ValidatedDocument:
    """Central entrypoint for validating, securing, and sanitizing any uploaded document."""
    # 0. Size check
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise SecurityValidationError(
            f"Ukuran file ({len(content) / (1024 * 1024):.1f} MB) melebihi batas {settings.max_upload_size_mb} MB.",
            code="FILE_TOO_LARGE",
        )

    # 1. Detect magic bytes format
    file_type = detect_file_type_from_magic_bytes(content)

    # 2. Check filename extension consistency
    validate_extension_match(filename, file_type)

    # 3. Format-specific deep checks & sanitization
    if file_type == "pdf":
        page_count, dimensions = validate_pdf_security(content)
        cleaned_bytes = content  # PDF bytes are validated clean
    else:  # jpeg or png
        cleaned_bytes, dimensions = sanitize_and_validate_image(content, file_type)
        page_count = 1

    checksum = hashlib.sha256(cleaned_bytes).hexdigest()
    content_type = MIME_TYPE_BY_FORMAT[file_type]

    return ValidatedDocument(
        file_type=file_type,
        content_type=content_type,
        cleaned_bytes=cleaned_bytes,
        page_count=page_count,
        dimensions=dimensions,
        checksum_sha256=checksum,
        original_size=len(content),
        cleaned_size=len(cleaned_bytes),
    )
