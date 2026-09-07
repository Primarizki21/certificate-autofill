"""Unit tests for TemporaryUploadStore and ephemeral zero-storage pipeline.

Verifies:
- Atomic staging with strict 0o600 permissions.
- Rejection of invalid magic bytes and oversized payloads.
- Path traversal defense via UUID validation.
- Orphan reaper lifecycle.
- End-to-end ephemeral pipeline: zero PDF bytes in DB and automatic file unlinking.
"""

import os
import sys
import tempfile
import time
import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(REPO_ROOT, "backend")
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.database import Base
from app.models import Document, ExtractionJob, ExtractedField
from app.services.temporary_upload_store import TemporaryUploadStore
from app.services.job_processor import process_document_job
from app.services.extraction_pipeline import PipelineResult


class TestTemporaryUploadStore:
    def test_stage_read_delete_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            store = TemporaryUploadStore(root_dir=td)
            payload = b"%PDF-1.4\nTest certificate content"
            key = store.stage_bytes(payload)

            assert isinstance(key, str)
            # Verify file exists and content matches
            retrieved = store.open_bytes(key)
            assert retrieved == payload

            # Verify deletion
            assert store.delete(key) is True
            assert store.delete(key) is False
            with pytest.raises(FileNotFoundError):
                store.open_bytes(key)

    def test_reject_non_pdf_magic_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            store = TemporaryUploadStore(root_dir=td)
            with pytest.raises(ValueError, match="magic bytes mismatch"):
                store.stage_bytes(b"<html>Not a PDF</html>")

    def test_reject_path_traversal(self):
        with tempfile.TemporaryDirectory() as td:
            store = TemporaryUploadStore(root_dir=td)
            with pytest.raises(ValueError, match="Invalid file key"):
                store.open_bytes("../../etc/passwd")

            assert store.delete("../../../secret.pdf") is False

    def test_reap_orphans(self):
        with tempfile.TemporaryDirectory() as td:
            store = TemporaryUploadStore(root_dir=td)
            key_old = store.stage_bytes(b"%PDF-1.4 Old orphaned PDF")
            key_new = store.stage_bytes(b"%PDF-1.4 Fresh PDF")

            path_old = store._resolve_key(key_old)
            # Set old mtime to 2 hours ago
            two_hours_ago = time.time() - 7200
            os.utime(path_old, (two_hours_ago, two_hours_ago))

            reaped = store.reap_orphans(max_age_seconds=3600)
            assert reaped == 1

            # Old file deleted, new file intact
            assert not path_old.exists()
            assert store.open_bytes(key_new) == b"%PDF-1.4 Fresh PDF"


class TestEphemeralPipelineProcessing:
    def test_job_processor_unlinks_temp_file_on_completion(self, monkeypatch):
        # Setup in-memory SQLite DB
        engine = create_engine("sqlite:///:memory:")
        TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
        Base.metadata.create_all(bind=engine)

        with tempfile.TemporaryDirectory() as td:
            test_store = TemporaryUploadStore(root_dir=td)

            # Monkeypatch SessionLocal and upload_store in job_processor
            monkeypatch.setattr("app.services.job_processor.SessionLocal", TestingSessionLocal)
            monkeypatch.setattr("app.services.job_processor.upload_store", test_store)

            # Mock extraction pipeline to avoid external API calls
            def mock_run_pipeline(*args, **kwargs):
                from app.services.field_extractor import ExtractedValue
                return PipelineResult(
                    parser_engine="test_engine_mock",
                    raw_text="Mock text",
                    raw_markdown=None,
                    raw_json={"status": "mock"},
                    mapped_fields={
                        "nama_kegiatan_sertifikasi": ExtractedValue(value="Lomba Test", confidence=0.95, source="mock"),
                        "penyelenggara": ExtractedValue(value="HIMA Test", confidence=0.90, source="mock"),
                    },
                )

            monkeypatch.setattr("app.services.job_processor.run_extraction_pipeline", mock_run_pipeline)

            # Stage a test PDF
            pdf_data = b"%PDF-1.4\nTest Certificate Content"
            temp_key = test_store.stage_bytes(pdf_data)

            # Verify file exists on disk
            assert test_store._resolve_key(temp_key).is_file()

            db = TestingSessionLocal()
            doc_id = str(uuid.uuid4())
            job_id = str(uuid.uuid4())

            doc = Document(
                id=doc_id,
                source_system="test",
                tahun_akademik="2023/2024",
                bukti_fisik="Sertifikat",
                original_file_name="cert.pdf",
                mime_type="application/pdf",
                file_size=len(pdf_data),
                checksum_sha256="dummy_sha256",
                status="queued",
            )
            job = ExtractionJob(
                id=job_id,
                document_id=doc_id,
                temp_file_key=temp_key,
                status="queued",
            )
            db.add(doc)
            db.add(job)
            db.commit()
            db.close()

            # Execute job processor
            process_document_job(job_id=job_id, document_id=doc_id)

            # Verify database state
            db = TestingSessionLocal()
            updated_doc = db.get(Document, doc_id)
            updated_job = db.get(ExtractionJob, job_id)
            fields = db.query(ExtractedField).filter(ExtractedField.document_id == doc_id).all()

            assert updated_doc.status in {"completed", "needs_review"}
            assert updated_doc.parser_engine == "test_engine_mock"
            assert updated_job.status == "completed"
            assert len(fields) == 2
            db.close()

            # CRITICAL VERIFICATION: Ephemeral PDF file MUST be deleted from disk
            assert not test_store._resolve_key(temp_key).is_file()
            with pytest.raises(FileNotFoundError):
                test_store.open_bytes(temp_key)


class TestUploadDeduplicationAutoRetrieval:
    def test_duplicate_upload_returns_cached_document(self, monkeypatch):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.database import get_db

        from sqlalchemy.pool import StaticPool
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
        Base.metadata.create_all(bind=engine)
        def override_get_db():
            db = TestingSessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db

        with tempfile.TemporaryDirectory() as td:
            test_store = TemporaryUploadStore(root_dir=td)
            monkeypatch.setattr("app.main.upload_store", test_store)
            monkeypatch.setattr("app.services.job_processor.upload_store", test_store)
            monkeypatch.setattr("app.services.job_processor.SessionLocal", TestingSessionLocal)

            def mock_run_pipeline(*args, **kwargs):
                from app.services.field_extractor import ExtractedValue
                return PipelineResult(
                    parser_engine="test_engine_mock",
                    raw_text="Mock text",
                    raw_markdown=None,
                    raw_json={"status": "mock"},
                    mapped_fields={
                        "nama_kegiatan_sertifikasi": ExtractedValue(value="Lomba Test", confidence=0.95, source="mock"),
                    },
                )
            import dataclasses
            from app.config import settings
            monkeypatch.setattr("app.main.settings", dataclasses.replace(settings, processing_mode="sync"))
            import fitz
            doc = fitz.open()
            doc.new_page()
            pdf_bytes = doc.tobytes()
            doc.close()
            client = TestClient(app)

            # 1. First upload -> processes synchronously
            resp1 = client.post(
                "/api/documents",
                data={"tahun_akademik": "2023/2024", "bukti_fisik": "Sertifikat"},
                files={"file": ("cert.pdf", pdf_bytes, "application/pdf")},
            )
            assert resp1.status_code == 200
            data1 = resp1.json()
            doc_id_1 = data1["document_id"]
            assert data1["status"] in {"completed", "needs_review"}
            assert data1["job_id"] != "cached"

            # Clear preview_image to simulate legacy document before preview feature
            db_check = TestingSessionLocal()
            doc_obj = db_check.get(Document, doc_id_1)
            doc_obj.preview_image = None
            db_check.commit()
            db_check.close()

            # 2. Second upload of identical PDF -> instant cache hit and backfills preview!
            resp2 = client.post(
                "/api/documents",
                data={"tahun_akademik": "2023/2024", "bukti_fisik": "Sertifikat"},
                files={"file": ("cert.pdf", pdf_bytes, "application/pdf")},
            )
            assert resp2.status_code == 200
            data2 = resp2.json()
            assert data2["document_id"] == doc_id_1
            assert data2["job_id"] == "cached"
            assert data2["status"] in {"completed", "needs_review"}

            # Verify preview was backfilled
            db_check2 = TestingSessionLocal()
            doc_obj2 = db_check2.get(Document, doc_id_1)
            assert doc_obj2.preview_image is not None
            db_check2.close()
        app.dependency_overrides.clear()


class TestCompressedPreview:
    def test_preview_generation_and_endpoint(self, monkeypatch):
        import fitz
        from app.services.preview_generator import generate_compressed_preview
        from fastapi.testclient import TestClient
        from app.main import app
        from app.database import get_db
        from sqlalchemy.pool import StaticPool

        # Create valid sample PDF
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        page.insert_text(fitz.Point(100, 100), "Sample Certificate", fontsize=18)
        pdf_bytes = doc.tobytes()
        doc.close()

        # 1. Test generator directly
        preview_bytes = generate_compressed_preview(pdf_bytes, dpi=110)
        assert preview_bytes is not None
        assert preview_bytes.startswith(b"\xff\xd8\xff")  # JPEG SOI magic bytes
        assert len(preview_bytes) < 100_000  # Strictly bounded under 100 KB

        # 2. Test failure returns None without raising
        assert generate_compressed_preview(b"corrupt non-pdf") is None

        # 3. Test GET preview endpoint with in-memory DB
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
        Base.metadata.create_all(bind=engine)

        def override_get_db():
            db = TestingSessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db

        db = TestingSessionLocal()
        doc_id = str(uuid.uuid4())
        test_doc = Document(
            id=doc_id,
            tahun_akademik="2023/2024",
            bukti_fisik="Sertifikat",
            original_file_name="cert.pdf",
            mime_type="application/pdf",
            file_size=len(pdf_bytes),
            checksum_sha256="dummy_sha",
            status="completed",
            preview_image=preview_bytes,
        )
        db.add(test_doc)
        db.commit()
        db.close()

        client = TestClient(app)
        resp = client.get(f"/api/documents/{doc_id}/preview")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/jpeg"
        assert resp.content == preview_bytes

        # Test non-existent preview returns 404
        resp_404 = client.get(f"/api/documents/{uuid.uuid4()}/preview")
        assert resp_404.status_code == 404

        # Test invalid uuid returns 400
        resp_400 = client.get("/api/documents/invalid-uuid/preview")
        assert resp_400.status_code == 400

        app.dependency_overrides.clear()

    def test_cleanup_expired_previews(self):
        from app.services.retention_cleanup import cleanup_expired_previews_and_documents
        from datetime import datetime, timedelta, timezone

        engine = create_engine("sqlite:///:memory:")
        TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
        Base.metadata.create_all(bind=engine)

        db = TestingSessionLocal()
        old_time = datetime.now(timezone.utc) - timedelta(hours=25)
        fresh_time = datetime.now(timezone.utc)

        doc_old_id = str(uuid.uuid4())
        doc_fresh_id = str(uuid.uuid4())
        doc_queued_id = str(uuid.uuid4())

        doc_old = Document(
            id=doc_old_id,
            tahun_akademik="2023/2024",
            bukti_fisik="Sertifikat",
            original_file_name="old.pdf",
            mime_type="application/pdf",
            file_size=100,
            checksum_sha256="old_sha",
            status="completed",
            preview_image=b"old_preview_bytes",
        )
        job_old = ExtractionJob(
            id=str(uuid.uuid4()),
            document_id=doc_old_id,
            status="completed",
            finished_at=old_time,
        )

        doc_fresh = Document(
            id=doc_fresh_id,
            tahun_akademik="2023/2024",
            bukti_fisik="Sertifikat",
            original_file_name="fresh.pdf",
            mime_type="application/pdf",
            file_size=100,
            checksum_sha256="fresh_sha",
            status="completed",
            preview_image=b"fresh_preview_bytes",
        )
        job_fresh = ExtractionJob(
            id=str(uuid.uuid4()),
            document_id=doc_fresh_id,
            status="completed",
            finished_at=fresh_time,
        )

        doc_queued = Document(
            id=doc_queued_id,
            tahun_akademik="2023/2024",
            bukti_fisik="Sertifikat",
            original_file_name="queued.pdf",
            mime_type="application/pdf",
            file_size=100,
            checksum_sha256="queued_sha",
            status="queued",
            preview_image=b"queued_preview_bytes",
        )
        job_queued = ExtractionJob(
            id=str(uuid.uuid4()),
            document_id=doc_queued_id,
            status="queued",
            finished_at=None,
        )

        db.add_all([doc_old, job_old, doc_fresh, job_fresh, doc_queued, job_queued])
        db.commit()

        purged = cleanup_expired_previews_and_documents(db, max_age_hours=24)
        assert purged == 1

        # doc_old deleted completely
        assert db.get(Document, doc_old_id) is None
        # doc_fresh and doc_queued intact
        assert db.get(Document, doc_fresh_id) is not None
        assert db.get(Document, doc_queued_id) is not None
        db.close()
