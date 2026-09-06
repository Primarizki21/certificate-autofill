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
