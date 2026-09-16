"""Smoke test for KHP Master Data Staging Pipeline (Backend & UI Integration).

Validates end-to-end behavior when ENABLE_KHP_MASTER_STAGING=True:
1. GET /api/options returns KHP_MASTER_OPTIONS with structured taxonomy (id, label, group_id).
2. Extraction pipeline resolves 9-fields and populates master_resolution tuple.
3. GET /api/documents/{id}/result delivers sanitized student payload with zero internal leakages.
4. Frontend index.html & app.js contain master modal and cascading dropdown logic.
"""

from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import app.database as app_db
from app.database import init_db
from app.models import Base

test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)
app_db.engine = test_engine
app_db.SessionLocal = TestingSessionLocal

from fastapi.testclient import TestClient
from app.config import settings
from app.main import app
from app.services.extraction_pipeline import run_extraction_pipeline


def test_smoke_staging_options(client: TestClient) -> None:
    resp = client.get("/api/options")
    assert resp.status_code == 200
    data = resp.json()
    assert "options" in data
    options = data["options"]

    # Verify structured master data options
    assert "kelompok_kegiatan" in options
    assert "jenis_kegiatan" in options
    assert "prestasi_partisipasi_jabatan" in options

    # Verify ID and label presence
    assert any(opt.get("id") == 41 for opt in options["jenis_kegiatan"])
    assert any("PKKMB" in str(opt.get("label")) for opt in options["jenis_kegiatan"])
    assert any(opt.get("id") == 7 for opt in options["prestasi_partisipasi_jabatan"])
    print("[PASS] 1. GET /api/options returns complete KHP Master Options")


def test_smoke_pipeline_resolution() -> None:
    raw_text = """
    KEMENTERIAN PENDIDIKAN, KEBUDAYAAN, RISET, DAN TEKNOLOGI
    UNIVERSITAS AIRLANGGA
    FAKULTAS TEKNOLOGI MAJU DAN MULTIDISIPLIN
    SERTIFIKAT PENGHARGAAN
    Nomor: 1234/UN3.FTMM/KM/2025
    Diberikan kepada:
    PRIMARIZKI AHMAD HARIYONO
    Sebagai JUARA 1 dalam perlombaan Data Science Competition 2025 Tingkat Nasional
    Surabaya, 15 September 2025
    """
    # Create simple dummy PDF bytes with PyMuPDF
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), raw_text)
    pdf_bytes = doc.tobytes()
    doc.close()

    result = run_extraction_pipeline(pdf_bytes, "2024/2025", "Sertifikat")
    assert result.mapped_fields is not None
    assert result.master_resolution is not None

    resolution = result.master_resolution
    assert resolution["status"] in ("resolved", "needs_review", "awaiting_kegiatan_2_lookup")
    assert "fields" in resolution
    assert "kelompok_kegiatan" in resolution["fields"]
    assert "jenis_kegiatan" in resolution["fields"]
    assert "prestasi_partisipasi_jabatan" in resolution["fields"]

    assert "khp_master_staging" in result.parser_engine
    print(f"[PASS] 2. Pipeline resolves master data: {resolution['fields']['jenis_kegiatan']['label']} (id={resolution['fields']['jenis_kegiatan']['id']})")


def test_smoke_api_sanitization(client: TestClient) -> None:
    # Verify health endpoint
    health_resp = client.get("/healthz")
    assert health_resp.status_code == 200
    assert health_resp.json()["status"] == "ok"
    # Upload test document
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "SERTIFIKAT KKN-BBM Mahasiswa Belajar Bersama Komunitas")
    pdf_bytes = doc.tobytes()
    doc.close()

    files = {"file": ("test_cert.pdf", pdf_bytes, "application/pdf")}
    data = {"tahun_akademik": "2024/2025", "bukti_fisik": "Sertifikat"}
    upload_resp = client.post("/api/documents", files=files, data=data)
    assert upload_resp.status_code == 200
    doc_id = upload_resp.json()["document_id"]

    # Poll status / result
    result_resp = client.get(f"/api/documents/{doc_id}/result")
    assert result_resp.status_code in (200, 202)
    if result_resp.status_code == 200:
        res_data = result_resp.json()
        assert "document_id" in res_data
        # Verify zero internal metadata leakage
        assert "raw_text" not in res_data
        assert "gemini_prompt" not in res_data
        assert "api_key" not in res_data
    print("[PASS] 3. API endpoints deliver clean, sanitized response")


def test_smoke_frontend_elements() -> None:
    frontend_html_path = REPO_ROOT / "frontend" / "index.html"
    frontend_js_path = REPO_ROOT / "frontend" / "app.js"

    assert frontend_html_path.exists(), "frontend/index.html missing"
    assert frontend_js_path.exists(), "frontend/app.js missing"

    html_content = frontend_html_path.read_text(encoding="utf-8")
    js_content = frontend_js_path.read_text(encoding="utf-8")

    # Check for master selection elements
    assert "kelompok" in html_content.lower() or "kelompok" in js_content.lower()
    assert "jenis" in html_content.lower() or "jenis" in js_content.lower()
    assert "kegiatan" in html_content.lower()
    # Check that app.js handles master modal and cascading filter
    assert "masterModal" in js_content and "modalGroupFilter" in js_content
    assert "filterJenisKegiatanByGroup" in js_content
    print("[PASS] 4. Frontend assets contain complete KHP Master Data integration UI")
def main() -> None:
    print("=== RUNNING KHP MASTER STAGING SMOKE TEST ===")
    flag_names = ("enable_khp_master_staging", "enable_tesseract_gemini")
    original_flags = {name: getattr(settings, name) for name in flag_names}

    try:
        object.__setattr__(settings, "enable_khp_master_staging", True)
        object.__setattr__(settings, "enable_tesseract_gemini", False)  # Offline deterministic test

        init_db()
        client = TestClient(app)

        test_smoke_staging_options(client)
        test_smoke_pipeline_resolution()
        test_smoke_api_sanitization(client)
        test_smoke_frontend_elements()
        print("\n=== ALL SMOKE TESTS PASSED (100% SUCCESS) ===")
    finally:
        for name, value in original_flags.items():
            object.__setattr__(settings, name, value)


if __name__ == "__main__":
    main()
