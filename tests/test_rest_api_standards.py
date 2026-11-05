import fitz
import pytest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.config import settings
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

    monkeypatch.setattr("app.main.settings", replace(settings, admin_password="admin123"))
    monkeypatch.setattr("app.main._run_auto_migrations", lambda: None)
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


def test_production_startup_rejects_weak_admin_password(monkeypatch):
    import asyncio
    import app.main as main

    monkeypatch.setattr(
        main,
        "settings",
        replace(settings, app_env="production", admin_password="admin123"),
    )
    with pytest.raises(RuntimeError):
        asyncio.run(main.on_startup())


def test_empty_admin_password_rejects_basic_auth(test_db_client, monkeypatch):
    client, _ = test_db_client
    monkeypatch.setattr(
        "app.main.settings",
        replace(settings, app_env="development", admin_password=""),
    )
    resp = client.get("/api/admin/khp/rules", auth=("admin", ""))
    assert resp.status_code == 401


def test_security_headers_present(test_db_client):
    client, _ = test_db_client
    resp = client.get("/livez")
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["referrer-policy"] == "no-referrer"


def test_invalid_document_uuid_returns_404(test_db_client):
    client, _ = test_db_client
    resp = client.get("/api/documents/not-a-uuid/result")
    assert resp.status_code == 404


def test_forwarded_for_ignored_unless_trusted(monkeypatch):
    from starlette.requests import Request
    from app.services import rate_limiter

    request = Request(
        {
            "type": "http",
            "headers": [(b"x-forwarded-for", b"1.2.3.4")],
            "client": ("9.9.9.9", 1234),
        }
    )
    monkeypatch.setattr(rate_limiter, "settings", replace(settings, trust_proxy_headers=False))
    assert rate_limiter.get_client_ip(request) == "9.9.9.9"

    monkeypatch.setattr(rate_limiter, "settings", replace(settings, trust_proxy_headers=True))
    assert rate_limiter.get_client_ip(request) == "1.2.3.4"


def test_queue_backpressure_rejects_stale_backlog(monkeypatch):
    import app.main as main

    monkeypatch.setattr(
        main, "settings", replace(settings, queue_backpressure_seconds=60)
    )

    stale_db = MagicMock()
    stale_db.query.return_value.filter.return_value.scalar.return_value = (
        datetime.now(timezone.utc) - timedelta(minutes=10)
    )
    with pytest.raises(main.HTTPException) as exc:
        main._reject_when_queue_saturated(stale_db)
    assert exc.value.status_code == 503
    assert exc.value.headers["Retry-After"] == "60"

    fresh_db = MagicMock()
    fresh_db.query.return_value.filter.return_value.scalar.return_value = (
        datetime.now(timezone.utc) - timedelta(seconds=5)
    )
    main._reject_when_queue_saturated(fresh_db)

    empty_db = MagicMock()
    empty_db.query.return_value.filter.return_value.scalar.return_value = None
    assert main._queue_backlog_seconds(empty_db) == 0.0


def test_rate_limit_identity_uses_valid_api_key(monkeypatch):
    from starlette.requests import Request
    from app.services import api_key_auth, rate_limiter

    allowed = ["sk-portal-kampus-1234567890"]
    monkeypatch.setattr(api_key_auth, "get_allowed_api_keys", lambda: allowed)
    monkeypatch.setattr(
        rate_limiter, "settings", replace(settings, trust_proxy_headers=False)
    )

    def make_request(key: str) -> Request:
        return Request(
            {
                "type": "http",
                "headers": [(b"x-api-key", key.encode())],
                "client": ("9.9.9.9", 1234),
            }
        )

    valid_identity = rate_limiter.get_client_identity(make_request(allowed[0]))
    assert valid_identity.startswith("key:")
    assert rate_limiter.get_client_identity(make_request("sk-random-000000000")) == "ip:9.9.9.9"
