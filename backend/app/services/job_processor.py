import logging
import os
import socket
import threading
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from app.config import settings
from app.database import SessionLocal
from app.models import Document, ExtractionJob, ExtractedField
from app.services.extraction_pipeline import run_extraction_pipeline
from app.services.form_mapper import field_needs_review
from app.services.temporary_upload_store import upload_store

logger = logging.getLogger("certificate-job-processor")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_worker_id() -> str:
    return f"{socket.gethostname()[:32]}-{os.getpid()}-{uuid.uuid4().hex[:16]}"


def _claim_job(db: Session, job_id: str, document_id: str, worker_id: str) -> ExtractionJob | None:
    now = utcnow()
    job = db.execute(
        select(ExtractionJob)
        .where(
            ExtractionJob.id == job_id,
            ExtractionJob.document_id == document_id,
            ExtractionJob.status == "queued",
            (ExtractionJob.available_at.is_(None)) | (ExtractionJob.available_at <= now),
        )
        .with_for_update(skip_locked=True)
    ).scalar_one_or_none()
    if job is None:
        return None

    job.status = "processing"
    job.started_at = now
    job.available_at = None
    job.worker_id = worker_id
    job.lease_expires_at = now + timedelta(seconds=settings.job_lease_seconds)
    document = db.get(Document, document_id)
    if document is not None:
        document.status = "processing"
    db.commit()
    return job


def _lock_owned_job(db: Session, job_id: str, worker_id: str) -> ExtractionJob | None:
    return db.execute(
        select(ExtractionJob)
        .where(
            ExtractionJob.id == job_id,
            ExtractionJob.status == "processing",
            ExtractionJob.worker_id == worker_id,
            ExtractionJob.lease_expires_at > utcnow(),
        )
        .with_for_update()
    ).scalar_one_or_none()


def _mark_owned_job_failed(db: Session, job_id: str, worker_id: str, error_message: str) -> bool:
    job = _lock_owned_job(db, job_id, worker_id)
    if job is None:
        db.rollback()
        return False

    document = db.get(Document, job.document_id)
    job.status = "failed"
    job.error_message = error_message
    job.finished_at = utcnow()
    job.worker_id = None
    job.lease_expires_at = None
    if document is not None:
        document.status = "failed"
    db.commit()
    return True


def _renew_lease(job_id: str, worker_id: str) -> bool:
    """Extend an active worker lease without reviving a reclaimed job."""
    db: Session = SessionLocal()
    try:
        now = utcnow()
        result = db.execute(
            update(ExtractionJob)
            .where(
                ExtractionJob.id == job_id,
                ExtractionJob.status == "processing",
                ExtractionJob.worker_id == worker_id,
                ExtractionJob.lease_expires_at > now,
            )
            .values(lease_expires_at=now + timedelta(seconds=settings.job_lease_seconds))
        )
        db.commit()
        return result.rowcount == 1
    except Exception:
        db.rollback()
        logger.exception("Could not renew job lease job_id=%s worker_id=%s", job_id, worker_id)
        return False
    finally:
        db.close()


def _run_lease_heartbeat(job_id: str, worker_id: str, stop_event: threading.Event) -> None:
    interval_seconds = max(0.1, settings.job_lease_seconds / 3)
    while not stop_event.wait(interval_seconds):
        if not _renew_lease(job_id, worker_id):
            if not stop_event.is_set():
                logger.warning("Lease heartbeat stopped job_id=%s worker_id=%s", job_id, worker_id)
            return


def process_document_job(job_id: str, document_id: str, worker_id: str | None = None) -> None:
    """Process a queued job once while holding its database lease."""
    db: Session = SessionLocal()
    owner = worker_id or _new_worker_id()
    temp_key: str | None = None
    terminal_status = False
    heartbeat_stop: threading.Event | None = None
    heartbeat: threading.Thread | None = None
    try:
        job = _claim_job(db, job_id, document_id, owner)
        if job is None:
            return

        temp_key = job.temp_file_key
        if not temp_key:
            raise RuntimeError(f"Job ({job_id}) tidak memiliki temp_file_key.")

        document = db.get(Document, document_id)
        if document is None:
            raise RuntimeError(f"Dokumen ({document_id}) tidak ditemukan di PostgreSQL.")

        tahun_akademik = document.tahun_akademik
        bukti_fisik = document.bukti_fisik
        db.close()
        heartbeat_stop = threading.Event()
        heartbeat = threading.Thread(
            target=_run_lease_heartbeat,
            args=(job_id, owner, heartbeat_stop),
            daemon=True,
        )
        heartbeat.start()

        logger.info("Processing document_id=%s file=%s temp_key=%s", document_id, document.original_file_name, temp_key)
        pdf_bytes = upload_store.open_bytes(temp_key)
        result = run_extraction_pipeline(
            pdf_bytes=pdf_bytes,
            tahun_akademik=tahun_akademik,
            bukti_fisik=bukti_fisik,
        )

        job = _lock_owned_job(db, job_id, owner)
        if job is None:
            logger.warning("Lease expired before completion document_id=%s job_id=%s", document_id, job_id)
            return

        document = db.get(Document, document_id)
        if document is None:
            raise RuntimeError(f"Dokumen ({document_id}) tidak ditemukan di PostgreSQL.")

        document.parser_engine = result.parser_engine
        db.query(ExtractedField).filter(ExtractedField.document_id == document_id).delete()
        any_review = False
        for field_name, extracted in result.mapped_fields.items():
            value = extracted.value
            needs_review = field_needs_review(field_name, value, extracted.confidence)
            any_review = any_review or needs_review
            db.add(
                ExtractedField(
                    id=str(uuid.uuid4()),
                    document_id=document_id,
                    form_field_name=field_name,
                    extracted_value=value,
                    mapped_value=value,
                    confidence=extracted.confidence,
                    source=extracted.source,
                    needs_review=needs_review,
                )
            )

        job.status = "completed"
        job.finished_at = utcnow()
        job.worker_id = None
        job.lease_expires_at = None
        document.status = "needs_review" if any_review else "completed"
        db.commit()
        terminal_status = True
        logger.info("Completed document_id=%s status=%s parser_engine=%s", document_id, document.status, document.parser_engine)
    except Exception as exc:
        db.rollback()
        terminal_status = _mark_owned_job_failed(db, job_id, owner, str(exc))
        if terminal_status:
            logger.exception("Failed processing document_id=%s job_id=%s: %s", document_id, job_id, exc)
            raise
        logger.warning("Ignored failed stale lease document_id=%s job_id=%s", document_id, job_id)
    finally:
        if heartbeat_stop is not None:
            heartbeat_stop.set()
        if heartbeat is not None:
            heartbeat.join(timeout=1)
        if temp_key and terminal_status:
            deleted = upload_store.delete(temp_key)
            if deleted:
                logger.info("Ephemeral PDF successfully unlinked: temp_key=%s", temp_key)
        db.close()


def cleanup_expired_jobs_and_uploads() -> int:
    """Recover expired leases and remove PDFs no active job owns."""
    db: Session = SessionLocal()
    terminal_keys: list[str] = []
    try:
        now = utcnow()
        retention_cutoff = now - timedelta(hours=settings.temp_file_ttl_hours)
        retryable_jobs = db.execute(
            select(ExtractionJob)
            .where(
                ExtractionJob.status == "processing",
                ExtractionJob.lease_expires_at < now,
                ExtractionJob.created_at >= retention_cutoff,
                ExtractionJob.retry_count < settings.max_job_retries,
            )
            .with_for_update(skip_locked=True)
        ).scalars()
        for job in retryable_jobs:
            document = db.get(Document, job.document_id)
            job.status = "queued"
            job.retry_count += 1
            job.available_at = now
            job.worker_id = None
            job.lease_expires_at = None
            if document is not None:
                document.status = "queued"

        expired_jobs = db.execute(
            select(ExtractionJob)
            .where(
                (
                    (ExtractionJob.status == "queued")
                    & (ExtractionJob.created_at < retention_cutoff)
                )
                | (
                    (ExtractionJob.status == "processing")
                    & (
                        (ExtractionJob.created_at < retention_cutoff)
                        | (
                            (ExtractionJob.lease_expires_at < now)
                            & (ExtractionJob.retry_count >= settings.max_job_retries)
                        )
                    )
                )
            )
            .with_for_update(skip_locked=True)
        ).scalars()
        for job in expired_jobs:
            document = db.get(Document, job.document_id)
            job.status = "failed"
            job.error_message = "Masa retensi file sementara berakhir."
            job.finished_at = now
            job.worker_id = None
            job.lease_expires_at = None
            if job.temp_file_key:
                terminal_keys.append(job.temp_file_key)
            if document is not None:
                document.status = "failed"

        db.commit()
        protected_keys = set(
            db.execute(
                select(ExtractionJob.temp_file_key).where(
                    ExtractionJob.status.in_(("queued", "processing")),
                    ExtractionJob.temp_file_key.is_not(None),
                )
            ).scalars()
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    deleted_count = sum(upload_store.delete(key) for key in terminal_keys)
    return deleted_count + upload_store.reap_orphans(protected_keys=protected_keys)
