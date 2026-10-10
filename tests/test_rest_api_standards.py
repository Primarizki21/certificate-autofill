import fitz
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.database import Base, get_db
from app.main import app
from app.models import KHPKelompokKegiatan, KHPKegiatan1, KHPTingkat, KHPJabatanPrestasi
from app.services.rate_limiter import upload_rate_limiter


def make_minimal_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 100), "Sertifikat Kelulusan Pelatihan")
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def test_db_client(monkeypatch):
    upload_rate_limiter.reset()
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db_session = TestingSession()

    # Seed data minimum untuk relasi KHP
    kel = KHPKelompokKegiatan(id_kelompok_kegiatan=1, nm_kelompok_kegiatan="Organisasi", is_aktif=True)
    k1 = KHPKegiatan1(id_kegiatan_1=10, id_kelompok_kegiatan=1, nm_kegiatan_1="Webinar", is_aktif=True)
    tingkat = KHPTingkat(id_tingkat=1, nm_tingkat="Nasional")
    jabatan = KHPJabatanPrestasi(id_jabatan_prestasi=1, nm_jabatan_prestasi="Peserta")
    db_session.add_all([kel, k1, tingkat, jabatan])
    db_session.commit()

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    monkeypatch.setattr("app.main.init_db", lambda: None)
    monkeypatch.setattr("app.main.cleanup_expired_jobs_and_uploads", lambda: None)
    monkeypatch.setattr("app.main.process_document_job", lambda *args, **kw: None)
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        yield client, db_session

    app.dependency_overrides.clear()
    db_session.close()


def test_upload_documents_returns_location_and_ratelimit_headers(test_db_client):
    client, _ = test_db_client
    pdf_bytes = make_minimal_pdf()
    resp = client.post(
        "/api/documents",
        data={"tahun_akademik": "2024/2025", "bukti_fisik": "Sertifikat"},
        files={"file": ("sertifikat.pdf", pdf_bytes, "application/pdf")},
    )
    assert resp.status_code == 200
    assert "location" in resp.headers
    assert resp.headers["location"].startswith("/api/documents/")
    assert resp.headers["location"].endswith("/result")
    assert "x-ratelimit-limit" in resp.headers
    assert "x-ratelimit-remaining" in resp.headers


def test_admin_khp_rules_create_returns_location_header(test_db_client):
    client, _ = test_db_client
    auth = ("admin", "admin123")
    payload = {
        "id_kelompok_kegiatan": 1,
        "id_kegiatan_1": 10,
        "id_tingkat": 1,
        "id_jabatan_prestasi": 1,
        "dasar_penilaian": "Sertifikat Keikutsertaan",
        "is_active": True,
    }
    resp = client.post("/api/admin/khp/rules", json=payload, auth=auth)
    assert resp.status_code == 201
    assert "location" in resp.headers
    assert resp.headers["location"].startswith("/api/admin/khp/rules/")


def test_admin_khp_rules_pagination_limit_bounded(test_db_client):
    client, _ = test_db_client
    auth = ("admin", "admin123")

    # Limit valid <= 500
    res_valid = client.get("/api/admin/khp/rules?limit=100&offset=0", auth=auth)
    assert res_valid.status_code == 200

    # Limit tidak valid > 500 memicu 422 Unprocessable Entity
    res_invalid = client.get("/api/admin/khp/rules?limit=600&offset=0", auth=auth)
    assert res_invalid.status_code == 422
