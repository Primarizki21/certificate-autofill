import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Document, ExtractionJob

logger = logging.getLogger("certificate-retention-cleanup")


def cleanup_expired_previews_and_documents(db: Session, max_age_hours: int | None = None) -> int:
    """Purge documents and previews older than retention hours from finished_at.

    Invariants:
    - Avoids permanent accumulation of BYTEA and database rows in PostgreSQL.
    - Uses ExtractionJob.finished_at as the authoritative contract cutoff.
    - Deleting Document cascades to ExtractionJob and ExtractedField, reclaiming
      both table and PostgreSQL TOAST storage completely.
    """
    retention_hours = max_age_hours if max_age_hours is not None else settings.result_retention_hours
    cutoff = datetime.now(timezone.utc) - timedelta(hours=retention_hours)

    expired_docs = (
        db.query(Document)
        .join(ExtractionJob, ExtractionJob.document_id == Document.id)
        .filter(
            ExtractionJob.status.in_(["completed", "needs_review", "failed"]),
            ExtractionJob.finished_at.isnot(None),
            ExtractionJob.finished_at < cutoff,
        )
        .distinct()
        .all()
    )
    count = len(expired_docs)
    for doc in expired_docs:
        db.delete(doc)

    if count > 0:
        db.commit()
        logger.info("Purged %d expired documents (> %d hours from finished_at)", count, retention_hours)

    return count
