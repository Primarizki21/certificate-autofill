"""Adversarial and Security Red-Testing Suite for Certificate Uploads.

Tests defensive guards against attacks and troll submissions:
1. Benign valid files (PDF, JPEG, PNG)
2. File extension & MIME type spoofing (polyglot / camouflage)
3. Decompression bomb & pixel flood DoS
4. Micro-dimension & extreme aspect ratio troll images
5. EXIF active script & metadata injection sanitization
6. PDF multi-page bomb DoS (> 3 pages)
7. PDF password encryption locking
8. PDF malicious active content (/JS, /JavaScript, /Launch, /EmbeddedFiles)
9. PDF canvas bomb DoS
10. FastAPI HTTP upload integration & error response handling
"""

import io
import pytest
import fitz
from PIL import Image
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.services.security_guard import (
    SecurityValidationError,
    detect_file_type_from_magic_bytes,
    inspect_and_guard_upload,
    sanitize_and_validate_image,
    validate_extension_match,
    validate_pdf_security,
)
from app.services.temporary_upload_store import TemporaryUploadStore


# ============================================================================
# Helpers to generate synthetic benign & adversarial payloads
# ============================================================================

def make_clean_pdf(pages: int = 1, width: float = 595.0, height: float = 842.0) -> bytes:
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=width, height=height)
        page.insert_text((50, 100), f"Sertifikat Halaman {i + 1}")
    data = doc.tobytes()
    doc.close()
    return data


def make_clean_jpeg(width: int = 800, height: int = 600) -> bytes:
    img = Image.new("RGB", (width, height), color=(240, 240, 240))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def make_clean_png(width: int = 800, height: int = 600) -> bytes:
    img = Image.new("RGB", (width, height), color=(240, 240, 240))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def make_clean_webp(width: int = 800, height: int = 600) -> bytes:
    img = Image.new("RGB", (width, height), color=(240, 240, 240))
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=90)
    return buf.getvalue()

# ============================================================================
# Unit & Adversarial Tests
# ============================================================================

class TestSecurityGuards:

    def test_benign_pdf_accepted(self):
        content = make_clean_pdf(pages=1)
        res = inspect_and_guard_upload(content, "sertifikat_resmi.pdf")
        assert res.file_type == "pdf"
        assert res.content_type == "application/pdf"
        assert res.page_count == 1
        assert len(res.cleaned_bytes) == len(content)

    def test_benign_jpeg_accepted_and_sanitized(self):
        content = make_clean_jpeg(width=1000, height=750)
        res = inspect_and_guard_upload(content, "sertifikat.jpg")
        assert res.file_type == "jpeg"
        assert res.content_type == "image/jpeg"
        assert res.dimensions == (1000, 750)
        assert res.page_count == 1

    def test_benign_png_accepted_and_sanitized(self):
        content = make_clean_png(width=1200, height=800)
        res = inspect_and_guard_upload(content, "sertifikat.png")
        assert res.file_type == "png"
        assert res.content_type == "image/png"
        assert res.dimensions == (1200, 800)
        assert res.page_count == 1

    def test_benign_webp_accepted_and_sanitized(self):
        content = make_clean_webp(width=1000, height=750)
        res = inspect_and_guard_upload(content, "sertifikat.webp")
        assert res.file_type == "webp"
        assert res.content_type == "image/webp"
        assert res.dimensions == (1000, 750)
        assert res.page_count == 1

    def test_file_size_boundary_enforcement(self):
        # Default limit is 25 MB. 26 MB must be rejected.
        oversized = b"%PDF-" + b"0" * (26 * 1024 * 1024)
        with pytest.raises(SecurityValidationError) as exc:
            inspect_and_guard_upload(oversized, "huge.pdf")
        assert exc.value.code == "FILE_TOO_LARGE"
    # --- MIME & Extension Spoofing ---

    def test_reject_executable_or_shell_script(self):
        script_content = b"#!/bin/bash\nrm -rf / --no-preserve-root\n"
        with pytest.raises(SecurityValidationError) as exc:
            inspect_and_guard_upload(script_content, "script.pdf")
        assert exc.value.code == "UNSUPPORTED_OR_SPOOFED_TYPE"

    def test_reject_html_phishing_spoofed_as_pdf(self):
        html_content = b"<!DOCTYPE html><html><body>Phishing login</body></html>"
        with pytest.raises(SecurityValidationError) as exc:
            inspect_and_guard_upload(html_content, "document.pdf")
        assert exc.value.code == "UNSUPPORTED_OR_SPOOFED_TYPE"

    def test_reject_jpeg_renamed_to_pdf(self):
        jpeg_bytes = make_clean_jpeg()
        with pytest.raises(SecurityValidationError) as exc:
            inspect_and_guard_upload(jpeg_bytes, "fake_doc.pdf")
        assert exc.value.code == "MIME_SPOOFING"

    def test_reject_png_renamed_to_jpg(self):
        png_bytes = make_clean_png()
        with pytest.raises(SecurityValidationError) as exc:
            inspect_and_guard_upload(png_bytes, "fake_photo.jpg")
        assert exc.value.code == "MIME_SPOOFING"

    def test_reject_pdf_renamed_to_png(self):
        pdf_bytes = make_clean_pdf()
        with pytest.raises(SecurityValidationError) as exc:
            inspect_and_guard_upload(pdf_bytes, "fake_image.png")
        assert exc.value.code == "MIME_SPOOFING"

    def test_reject_disallowed_extensions(self):
        content = make_clean_jpeg()
        for bad_ext in ("sertifikat.svg", "sertifikat.bmp", "sertifikat.exe", "sertifikat.sh"):
            with pytest.raises(SecurityValidationError) as exc:
                inspect_and_guard_upload(content, bad_ext)
            assert exc.value.code == "INVALID_EXTENSION"

    def test_reject_non_webp_riff_audio(self):
        # Fake RIFF with WAVE format
        wav_bytes = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00"
        with pytest.raises(SecurityValidationError) as exc:
            inspect_and_guard_upload(wav_bytes, "audio.webp")
        assert exc.value.code == "UNSUPPORTED_OR_SPOOFED_TYPE"
    # --- Image Dimension & Decompression Bomb Guards ---

    def test_reject_micro_dimension_troll_image(self):
        tiny_png = make_clean_png(width=1, height=1)
        with pytest.raises(SecurityValidationError) as exc:
            inspect_and_guard_upload(tiny_png, "micro.png")
        assert exc.value.code == "IMAGE_TOO_SMALL"

    def test_reject_sub_threshold_dimension(self):
        small_jpeg = make_clean_jpeg(width=200, height=200)
        with pytest.raises(SecurityValidationError) as exc:
            inspect_and_guard_upload(small_jpeg, "too_small.jpg")
        assert exc.value.code == "IMAGE_TOO_SMALL"

    def test_reject_macro_dimension_pixel_flood(self):
        big_jpeg = make_clean_jpeg(width=8500, height=8500)
        with pytest.raises(SecurityValidationError) as exc:
            inspect_and_guard_upload(big_jpeg, "too_big.jpg")
        assert exc.value.code == "IMAGE_TOO_LARGE"

    def test_auto_downscale_high_dpi_image(self):
        # Scan 600 DPI (4800 x 3600 px) -> should auto-downscale to target max edge (2500 px)
        high_dpi_jpeg = make_clean_jpeg(width=4800, height=3600)
        res = inspect_and_guard_upload(high_dpi_jpeg, "scan_600dpi.jpg")
        assert res.dimensions is not None
        assert max(res.dimensions) == 2500
        assert res.dimensions[0] == 2500
        assert res.dimensions[1] == int(3600 * (2500 / 4800))

    def test_reject_extreme_aspect_ratio_banner_troll(self):
        # 3000 x 300 px = ratio 10:1 (exceeds limit 5:1)
        banner_png = make_clean_png(width=3000, height=300)
        with pytest.raises(SecurityValidationError) as exc:
            inspect_and_guard_upload(banner_png, "banner.png")
        assert exc.value.code == "ASPECT_RATIO_ABNORMAL"

    # --- EXIF & Active Metadata Injection Sanitization ---

    def test_sanitize_malicious_exif_tags(self):
        img = Image.new("RGB", (600, 600), color=(255, 255, 255))
        exif = img.getexif()
        # 0x010E is ImageDescription, 0x9286 is UserComment
        exif[0x010E] = "<script>alert('xss')</script>"
        exif[0x9286] = "; DROP TABLE documents; --"
        buf = io.BytesIO()
        img.save(buf, format="JPEG", exif=exif)
        dirty_bytes = buf.getvalue()

        assert b"<script>" in dirty_bytes

        res = inspect_and_guard_upload(dirty_bytes, "sertifikat_with_exif.jpg")
        # Cleaned bytes must not contain injected scripts
        assert b"<script>" not in res.cleaned_bytes
        assert b"DROP TABLE" not in res.cleaned_bytes

        # Re-verify through Pillow
        cleaned_img = Image.open(io.BytesIO(res.cleaned_bytes))
        cleaned_exif = cleaned_img.getexif()
        assert len(cleaned_exif.keys()) == 0

    # --- PDF Security Guards ---

    def test_reject_pdf_page_bomb(self):
        bomb_pdf = make_clean_pdf(pages=5)  # Max allowed is 3
        with pytest.raises(SecurityValidationError) as exc:
            inspect_and_guard_upload(bomb_pdf, "page_bomb.pdf")
        assert exc.value.code == "PDF_TOO_MANY_PAGES"

    def test_reject_password_protected_pdf(self):
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 100), "Sertifikat rahasia")
        locked_pdf = doc.tobytes(
            encryption=fitz.PDF_ENCRYPT_AES_256,
            owner_pw="ownerpass",
            user_pw="userpass",
        )
        doc.close()

        with pytest.raises(SecurityValidationError) as exc:
            inspect_and_guard_upload(locked_pdf, "locked.pdf")
        assert exc.value.code == "PDF_PASSWORD_PROTECTED"

    def test_reject_pdf_with_embedded_binary(self):
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 100), "Sertifikat berlampiran")
        doc.embfile_add("malicious.exe", b"binary payload")
        pdf_bytes = doc.tobytes()
        doc.close()

        with pytest.raises(SecurityValidationError) as exc:
            inspect_and_guard_upload(pdf_bytes, "attachment.pdf")
        assert exc.value.code == "PDF_EMBEDDED_FILES"

    def test_reject_pdf_with_javascript_action(self):
        doc = fitz.open()
        doc.new_page()
        catalog = doc.pdf_catalog()
        doc.xref_set_key(catalog, "OpenAction", "<</S /JavaScript /JS (app.alert('evil'))>>")
        pdf_bytes = doc.tobytes()
        doc.close()

        with pytest.raises(SecurityValidationError) as exc:
            inspect_and_guard_upload(pdf_bytes, "js_script.pdf")
        assert exc.value.code == "PDF_ACTIVE_CONTENT"

    def test_accept_google_docs_benign_js_name_tree(self):
        # Simulates Google Docs/Google Drive PDF export having empty /Names <</JavaScript 3 0 R>>
        doc = fitz.open()
        doc.new_page()
        catalog = doc.pdf_catalog()
        doc.xref_set_key(catalog, "Names", "<</JavaScript 3 0 R>>")
        pdf_bytes = doc.tobytes()
        doc.close()

        res = inspect_and_guard_upload(pdf_bytes, "google_docs_sertifikat.pdf")
        assert res.file_type == "pdf"
        assert res.page_count == 1

    def test_reject_pdf_with_launch_action(self):
        # Malicious PDF trying to execute an OS command or binary
        doc = fitz.open()
        doc.new_page()
        catalog = doc.pdf_catalog()
        doc.xref_set_key(catalog, "OpenAction", "<</S /Launch /F (cmd.exe)>>")
        pdf_bytes = doc.tobytes()
        doc.close()

        with pytest.raises(SecurityValidationError) as exc:
            inspect_and_guard_upload(pdf_bytes, "malicious_launch.pdf")
        assert exc.value.code == "PDF_ACTIVE_CONTENT"

    def test_reject_pdf_canvas_bomb(self):
        # Abnormal canvas: 8000 x 8000 pt (limit is 5000 pt)
        canvas_bomb = make_clean_pdf(pages=1, width=8000.0, height=8000.0)
        with pytest.raises(SecurityValidationError) as exc:
            inspect_and_guard_upload(canvas_bomb, "canvas_bomb.pdf")
        assert exc.value.code == "PDF_CANVAS_BOMB"


# ============================================================================
# API HTTP Endpoint Integration Tests
# ============================================================================

class TestUploadEndpointSecurity:

    @pytest.fixture
    def client(self, monkeypatch):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool
        from app.database import Base, get_db

        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
        db_session = TestingSession()

        def override_get_db():
            try:
                yield db_session
            finally:
                pass

        monkeypatch.setattr("app.main.init_db", lambda: None)
        monkeypatch.setattr("app.main.cleanup_expired_jobs_and_uploads", lambda: None)
        monkeypatch.setattr("app.main.process_document_job", lambda *args, **kw: None)
        app.dependency_overrides[get_db] = override_get_db
        with TestClient(app) as test_client:
            yield test_client
        app.dependency_overrides.clear()
        db_session.close()

    def test_api_upload_valid_jpeg(self, client):
        jpeg_bytes = make_clean_jpeg(width=800, height=600)
        resp = client.post(
            "/api/documents",
            data={"tahun_akademik": "2024/2025", "bukti_fisik": "Sertifikat"},
            files={"file": ("sertifikat.jpg", jpeg_bytes, "image/jpeg")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "document_id" in data
        assert "job_id" in data

    def test_api_upload_valid_png(self, client):
        png_bytes = make_clean_png(width=800, height=600)
        resp = client.post(
            "/api/documents",
            data={"tahun_akademik": "2024/2025", "bukti_fisik": "Sertifikat"},
            files={"file": ("sertifikat.png", png_bytes, "image/png")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "document_id" in data

    def test_api_upload_rejects_spoofed_file(self, client):
        html_bytes = b"<html><body>Phishing</body></html>"
        resp = client.post(
            "/api/documents",
            data={"tahun_akademik": "2024/2025", "bukti_fisik": "Sertifikat"},
            files={"file": ("sertifikat.pdf", html_bytes, "application/pdf")},
        )
        assert resp.status_code == 400
        assert "magic bytes tidak cocok" in resp.json()["detail"]

    def test_api_upload_rejects_micro_troll_image(self, client):
        tiny_png = make_clean_png(width=1, height=1)
        resp = client.post(
            "/api/documents",
            data={"tahun_akademik": "2024/2025", "bukti_fisik": "Sertifikat"},
            files={"file": ("tiny.png", tiny_png, "image/png")},
        )
        assert resp.status_code == 400
        assert "terlalu kecil" in resp.json()["detail"]

    def test_api_upload_rejects_password_pdf(self, client):
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 100), "Confidential")
        locked_pdf = doc.tobytes(
            encryption=fitz.PDF_ENCRYPT_AES_256,
            owner_pw="pw1",
            user_pw="pw2",
        )
        doc.close()

        resp = client.post(
            "/api/documents",
            data={"tahun_akademik": "2024/2025", "bukti_fisik": "Sertifikat"},
            files={"file": ("locked.pdf", locked_pdf, "application/pdf")},
        )
        assert resp.status_code == 400
        assert "kata sandi" in resp.json()["detail"]

    def test_api_upload_enforces_rate_limit(self, client):
        from app.services.rate_limiter import upload_rate_limiter
        upload_rate_limiter.reset()
        original_limit = upload_rate_limiter.max_requests
        upload_rate_limiter.max_requests = 2
        try:
            jpeg_bytes = make_clean_jpeg(width=800, height=600)
            # Request 1: OK
            r1 = client.post(
                "/api/documents",
                data={"tahun_akademik": "2024/2025", "bukti_fisik": "Sertifikat"},
                files={"file": ("cert1.jpg", jpeg_bytes, "image/jpeg")},
            )
            assert r1.status_code == 200

            # Request 2: OK
            r2 = client.post(
                "/api/documents",
                data={"tahun_akademik": "2024/2025", "bukti_fisik": "Sertifikat"},
                files={"file": ("cert2.jpg", jpeg_bytes, "image/jpeg")},
            )
            assert r2.status_code == 200

            # Request 3: 429 Too Many Requests
            r3 = client.post(
                "/api/documents",
                data={"tahun_akademik": "2024/2025", "bukti_fisik": "Sertifikat"},
                files={"file": ("cert3.jpg", jpeg_bytes, "image/jpeg")},
            )
            assert r3.status_code == 429
            assert "Terlalu banyak permintaan upload" in r3.json()["detail"]
            assert "Retry-After" in r3.headers
        finally:
            upload_rate_limiter.max_requests = original_limit
            upload_rate_limiter.reset()
