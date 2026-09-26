import io
from contextlib import contextmanager
import pytest
from fastapi.testclient import TestClient
import fitz  # PyMuPDF

from app.config import settings
from app.main import app
from app.services.api_key_auth import (
    generate_api_key,
    is_valid_key_format,
    validate_api_key,
    get_allowed_api_keys,
)


@contextmanager
def temporary_settings(**kwargs):
    orig = {k: getattr(settings, k) for k in kwargs}
    for k, v in kwargs.items():
        object.__setattr__(settings, k, v)
    try:
        yield
    finally:
        for k, v in orig.items():
            object.__setattr__(settings, k, v)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sample_pdf_bytes():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (50, 100),
        "SERTIFIKAT PENGHARGAAN\n"
        "Nomor: 001/UN3.FTMM/KM/2024\n\n"
        "Diberikan kepada Budi Santoso sebagai Peserta pada\n"
        "Webinar Nasional Kecerdasan Buatan dan Sains Data\n"
        "yang diselenggarakan oleh HIMA Sains Data Universitas Airlangga\n"
        "pada tanggal 20 Agustus 2024.",
        fontsize=12,
    )
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def test_api_key_generation_and_format():
    key_urlsafe = generate_api_key(prefix="sk-", length=32, encoding="base64url")
    assert key_urlsafe.startswith("sk-")
    assert is_valid_key_format(key_urlsafe)
    assert len(key_urlsafe) >= 20

    key_hex = generate_api_key(prefix="sk-hex-", length=32, encoding="hex")
    assert key_hex.startswith("sk-hex-")
    assert is_valid_key_format(key_hex)

    # Prefix without sk should have sk- prepended
    key_custom = generate_api_key(prefix="client_", length=24)
    assert key_custom.startswith("sk-client")
    assert is_valid_key_format(key_custom)

    # Invalid formats
    assert not is_valid_key_format(None)
    assert not is_valid_key_format("")
    assert not is_valid_key_format("short")
    assert not is_valid_key_format("bearer_token_without_sk_prefix_123456789")


def test_api_key_validation():
    key1 = generate_api_key(prefix="sk-test-")
    key2 = generate_api_key(prefix="sk-live-")
    allowed = [key1, key2]

    assert validate_api_key(key1, allowed) is True
    assert validate_api_key(key2, allowed) is True
    assert validate_api_key("sk-random-non-existent-key-123456", allowed) is False
    assert validate_api_key("", allowed) is False
    assert validate_api_key(None, allowed) is False


def test_extract_v1_open_mode_when_no_api_keys(client, sample_pdf_bytes):
    with temporary_settings(api_keys="", require_api_key=False, enable_tesseract_gemini=False):
        files = {"file": ("sertifikat.pdf", sample_pdf_bytes, "application/pdf")}
        data = {
            "tahun_akademik": "2035/2036 - Genap",
            "bukti_fisik": "Sertifikat",
        }
        response = client.post("/api/v1/extract", files=files, data=data)
        assert response.status_code == 200
        payload = response.json()

        assert "status" in payload
        assert "needs_review" in payload
        assert "data" in payload
        data_block = payload["data"]
        assert data_block["bukti_fisik"] == "Sertifikat"
        assert data_block["tahun_akademik"] == "2035/2036 - Genap"
        assert "kelompok_kegiatan" in data_block
        assert "jenis_kegiatan" in data_block
        assert "tingkat" in data_block
        assert "prestasi_partisipasi_jabatan" in data_block
        assert "id_kegiatan_2" in data_block


def test_extract_v1_authentication_enforced(client, sample_pdf_bytes):
    valid_key = "sk-test-secret-key-1234567890abcdef"

    with temporary_settings(api_keys=valid_key, require_api_key=True, enable_tesseract_gemini=False):
        files = {"file": ("sertifikat.pdf", sample_pdf_bytes, "application/pdf")}

        # 1. Missing API Key -> 401 Unauthorized
        res_no_key = client.post("/api/v1/extract", files=files)
        assert res_no_key.status_code == 401
        assert "API Key wajib disertakan" in res_no_key.json()["detail"]

        # 2. Invalid API Key -> 401 Unauthorized
        res_wrong_key = client.post(
            "/api/v1/extract",
            files={"file": ("sertifikat.pdf", sample_pdf_bytes, "application/pdf")},
            headers={"X-API-Key": "sk-wrong-key-00000000000000000"},
        )
        assert res_wrong_key.status_code == 401
        assert "API Key tidak valid" in res_wrong_key.json()["detail"]

        # 3. Valid API Key via X-API-Key -> 200 OK
        res_valid_header = client.post(
            "/api/v1/extract",
            files={"file": ("sertifikat.pdf", sample_pdf_bytes, "application/pdf")},
            headers={"X-API-Key": valid_key},
        )
        assert res_valid_header.status_code == 200
        assert res_valid_header.json()["status"] in {"success", "needs_review"}

        # 4. Valid API Key via Authorization: Bearer -> 200 OK
        res_bearer = client.post(
            "/api/v1/extract",
            files={"file": ("sertifikat.pdf", sample_pdf_bytes, "application/pdf")},
            headers={"Authorization": f"Bearer {valid_key}"},
        )
        assert res_bearer.status_code == 200


def test_extract_v1_validation_errors(client):
    valid_key = "sk-valid-key-abcdef1234567890"
    with temporary_settings(api_keys=valid_key, enable_tesseract_gemini=False):
        # Empty filename / missing file
        res_empty = client.post(
            "/api/v1/extract",
            files={"file": ("", b"", "application/pdf")},
            headers={"X-API-Key": valid_key},
        )
        assert res_empty.status_code in {400, 422}

        # Disallowed file type (.exe)
        res_invalid_type = client.post(
            "/api/v1/extract",
            files={"file": ("malicious.exe", b"MZ\x90\x00\x03\x00\x00\x00", "application/x-msdownload")},
            headers={"X-API-Key": valid_key},
        )
        assert res_invalid_type.status_code == 400


def test_extract_v1_response_payload_structure(client, sample_pdf_bytes):
    valid_key = "sk-test-payload-key-123456789012"
    with temporary_settings(api_keys=valid_key, enable_tesseract_gemini=False):
        files = {"file": ("sertifikat.pdf", sample_pdf_bytes, "application/pdf")}
        res = client.post(
            "/api/v1/extract",
            files=files,
            headers={"X-API-Key": valid_key},
        )
        assert res.status_code == 200
        data = res.json()

        # Top-level fields
        assert "status" in data
        assert "needs_review" in data
        assert "data" in data
        assert "confidence" in data
        assert "sources" in data
        assert "review_reasons" in data
        assert "parser_engine" in data

        cert_data = data["data"]
        # Essential certificate fields
        assert "nama_kegiatan_sertifikasi" in cert_data
        assert "nomor_bukti_fisik_nomor_sertifikasi" in cert_data
        assert "penyelenggara_kegiatan" in cert_data
        assert "waktu_mulai_pelaksanaan" in cert_data
        assert "waktu_selesai_pelaksanaan" in cert_data
        assert "jenis_penyelenggara" in cert_data

        # Master resolution fields
        for field in ("kelompok_kegiatan", "jenis_kegiatan", "tingkat", "prestasi_partisipasi_jabatan"):
            assert field in cert_data
            if cert_data[field] is not None:
                assert "id" in cert_data[field]
                assert "label" in cert_data[field]

        assert "id_kegiatan_2" in cert_data
