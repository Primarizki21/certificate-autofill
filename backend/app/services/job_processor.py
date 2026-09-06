import logging
import uuid
from datetime import datetime, timezone

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


def process_document_job(job_id: str, document_id: str) -> None:
    """Process one extraction job with ephemeral PDF storage.

    Invariants:
    - PDF bytes are read exclusively from TemporaryUploadStore.
    - Zero PDF bytes or raw OCR text are stored in PostgreSQL.
    - The ephemeral PDF file is unlinked in the finally block upon terminal status.
    """
    db: Session = SessionLocal()
    temp_key: str | None = None
    terminal_status: bool = False
    try:
        job = db.get(ExtractionJob, job_id)
        document = db.get(Document, document_id)
        if job is None or document is None:
            raise RuntimeError(f"Job ({job_id}) atau Dokumen ({document_id}) tidak ditemukan di PostgreSQL.")

        temp_key = job.temp_file_key
        if not temp_key:
            raise RuntimeError(f"Job ({job_id}) tidak memiliki temp_file_key.")

        if job.status == "completed" or document.status in {"completed", "needs_review"}:
            logger.info("Skip already processed document_id=%s job_id=%s", document_id, job_id)
            terminal_status = True
            return

        logger.info("Processing document_id=%s file=%s temp_key=%s", document_id, document.original_file_name, temp_key)
        job.status = "processing"
        job.started_at = utcnow()
        document.status = "processing"
        db.commit()

        pdf_bytes = upload_store.open_bytes(temp_key)

        result = run_extraction_pipeline(
            pdf_bytes=pdf_bytes,
            tahun_akademik=document.tahun_akademik,
            bukti_fisik=document.bukti_fisik,
        )

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
        document.status = "needs_review" if any_review else "completed"
        db.commit()
        terminal_status = True
        logger.info("Completed document_id=%s status=%s parser_engine=%s", document_id, document.status, document.parser_engine)
    except Exception as exc:
        db.rollback()
        terminal_status = True
        try:
            job = db.get(ExtractionJob, job_id)
            document = db.get(Document, document_id)
            if job:
                job.status = "failed"
                job.error_message = str(exc)
                job.finished_at = utcnow()
            if document:
                document.status = "failed"
            db.commit()
        finally:
            logger.exception("Failed processing document_id=%s job_id=%s: %s", document_id, job_id, exc)
        raise
    finally:
        if temp_key and terminal_status:
            deleted = upload_store.delete(temp_key)
            if deleted:
                logger.info("Ephemeral PDF successfully unlinked: temp_key=%s", temp_key)
        db.close()
