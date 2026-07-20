import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Document, ExtractionJob, ExtractedField, ParsedDocument
from app.services.extraction_pipeline import run_extraction_pipeline
from app.services.form_mapper import field_needs_review

logger = logging.getLogger("certificate-job-processor")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def process_document_job(job_id: str, document_id: str) -> None:
    """Process one extraction job without RabbitMQ.

    The PDF is read from PostgreSQL, parsed with the configured extraction
    pipeline, and the mapped form fields are saved back to PostgreSQL.
    """
    db: Session = SessionLocal()
    try:
        job = db.get(ExtractionJob, job_id)
        document = db.get(Document, document_id)
        if job is None or document is None or document.file is None:
            raise RuntimeError("Job/dokumen/PDF tidak ditemukan di PostgreSQL.")

        if job.status == "completed" or document.status in {"completed", "needs_review"}:
            logger.info("Skip already processed document_id=%s job_id=%s", document_id, job_id)
            return

        logger.info("Processing document_id=%s file=%s", document_id, document.original_file_name)
        job.status = "processing"
        job.started_at = utcnow()
        document.status = "processing"
        db.commit()

        result = run_extraction_pipeline(
            pdf_bytes=document.file.pdf_data,
            original_file_name=document.original_file_name,
            tahun_akademik=document.tahun_akademik,
            bukti_fisik=document.bukti_fisik,
        )

        db.add(
            ParsedDocument(
                id=str(uuid.uuid4()),
                document_id=document_id,
                parser_engine=result.parser_engine,
                raw_text=result.raw_text,
                raw_markdown=result.raw_markdown,
                raw_json=result.raw_json or {},
            )
        )

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
        logger.info("Completed document_id=%s status=%s", document_id, document.status)
    except Exception as exc:
        db.rollback()
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
        db.close()
