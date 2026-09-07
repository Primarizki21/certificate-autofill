"""Regression tests for storage cutover, leases, and orphan cleanup."""
from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database import Base
from app.models import Document, ExtractionJob
from app.services.extraction_pipeline import PipelineResult
from app.services.field_extractor import ExtractedValue
from app.services.job_processor import cleanup_expired_jobs_and_uploads, process_document_job
from app.services.temporary_upload_store import TemporaryUploadStore


def _load_migration_module():
    spec = importlib.util.spec_from_file_location(
        "migrate_ephemeral_storage",
        REPO_ROOT / "scripts" / "migrate_ephemeral_storage.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cutover_adds_queue_columns_and_drops_legacy_storage():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE documents (id VARCHAR PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE extraction_jobs (id VARCHAR PRIMARY KEY, document_id VARCHAR NOT NULL)"))
        connection.execute(text("CREATE TABLE document_files (document_id VARCHAR, pdf_data BLOB)"))
        connection.execute(text("CREATE TABLE parsed_documents (document_id VARCHAR, raw_text TEXT)"))

    module = _load_migration_module()
    result = module.apply_ephemeral_storage_cutover(engine)
    inspector = inspect(engine)

    assert result == {"legacy_tables": [], "missing_columns": {}}
    assert "document_files" not in inspector.get_table_names()
    assert "parsed_documents" not in inspector.get_table_names()
    assert {"parser_engine"}.issubset({column["name"] for column in inspector.get_columns("documents")})
    assert {"temp_file_key", "available_at", "lease_expires_at", "worker_id"}.issubset(
        {column["name"] for column in inspector.get_columns("extraction_jobs")}
    )


def test_cleanup_expires_unclaimed_pdf(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    testing_session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    expired_at = datetime.now(timezone.utc) - timedelta(hours=2)

    with tempfile.TemporaryDirectory() as directory:
        store = TemporaryUploadStore(root_dir=directory)
        temp_key = store.stage_bytes(b"%PDF-1.4\nExpired certificate")
        monkeypatch.setattr("app.services.job_processor.SessionLocal", testing_session)
        monkeypatch.setattr("app.services.job_processor.upload_store", store)

        document_id = str(uuid.uuid4())
        job_id = str(uuid.uuid4())
        db = testing_session()
        db.add(
            Document(
                id=document_id,
                source_system="test",
                tahun_akademik="2023/2024",
                bukti_fisik="Sertifikat",
                original_file_name="expired.pdf",
                mime_type="application/pdf",
                file_size=26,
                checksum_sha256="expired",
                status="queued",
            )
        )
        db.add(
            ExtractionJob(
                id=job_id,
                document_id=document_id,
                status="queued",
                temp_file_key=temp_key,
                available_at=expired_at,
                created_at=expired_at,
            )
        )
        db.commit()
        db.close()

        assert cleanup_expired_jobs_and_uploads() == 1

        db = testing_session()
        assert db.get(ExtractionJob, job_id).status == "failed"
        assert db.get(Document, document_id).status == "failed"
        db.close()
        assert not store._resolve_key(temp_key).exists()


def test_reaper_keeps_active_key_even_when_file_is_stale():
    with tempfile.TemporaryDirectory() as directory:
        store = TemporaryUploadStore(root_dir=directory)
        temp_key = store.stage_bytes(b"%PDF-1.4\nActive certificate")
        path = store._resolve_key(temp_key)
        stale_at = time.time() - 7200
        os.utime(path, (stale_at, stale_at))

        assert store.reap_orphans(protected_keys={temp_key}, max_age_seconds=3600) == 0
        assert path.exists()


def test_second_worker_cannot_run_claimed_job(monkeypatch, tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'jobs.sqlite'}",
        connect_args={"check_same_thread": False},
    )
    testing_session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    store = TemporaryUploadStore(root_dir=str(tmp_path / "uploads"))
    monkeypatch.setattr("app.services.job_processor.SessionLocal", testing_session)
    monkeypatch.setattr("app.services.job_processor.upload_store", store)

    started = threading.Event()
    release = threading.Event()
    lock = threading.Lock()
    calls = 0

    def mock_run_pipeline(*args, **kwargs):
        nonlocal calls
        with lock:
            calls += 1
        started.set()
        assert release.wait(timeout=3)
        return PipelineResult(
            parser_engine="test_engine_mock",
            raw_text="Mock text",
            raw_markdown=None,
            raw_json={"status": "mock"},
            mapped_fields={
                "nama_kegiatan_sertifikasi": ExtractedValue(value="Lomba Test", confidence=0.95, source="mock"),
            },
        )

    monkeypatch.setattr("app.services.job_processor.run_extraction_pipeline", mock_run_pipeline)
    temp_key = store.stage_bytes(b"%PDF-1.4\nConcurrent certificate")
    document_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    db = testing_session()
    db.add(
        Document(
            id=document_id,
            source_system="test",
            tahun_akademik="2023/2024",
            bukti_fisik="Sertifikat",
            original_file_name="concurrent.pdf",
            mime_type="application/pdf",
            file_size=29,
            checksum_sha256="concurrent",
            status="queued",
        )
    )
    db.add(ExtractionJob(id=job_id, document_id=document_id, status="queued", temp_file_key=temp_key))
    db.commit()
    db.close()

    first_worker = threading.Thread(
        target=process_document_job,
        kwargs={"job_id": job_id, "document_id": document_id, "worker_id": "worker-one"},
    )
    first_worker.start()
    assert started.wait(timeout=3)

    process_document_job(job_id=job_id, document_id=document_id, worker_id="worker-two")
    release.set()
    first_worker.join(timeout=3)

    assert not first_worker.is_alive()
    assert calls == 1
    db = testing_session()
    assert db.get(ExtractionJob, job_id).status == "completed"
    db.close()


def test_startup_schedules_storage_cleanup(monkeypatch):
    import app.main as main

    calls: list[str] = []
    monkeypatch.setattr(main, "init_db", lambda: calls.append("init"))
    monkeypatch.setattr(main, "cleanup_expired_jobs_and_uploads", lambda: calls.append("cleanup"))

    async def run_startup_and_shutdown():
        await main.on_startup()
        task = main.app.state.storage_cleanup_task
        assert not task.done()
        await main.on_shutdown()

    asyncio.run(run_startup_and_shutdown())
    assert calls == ["init", "cleanup"]
