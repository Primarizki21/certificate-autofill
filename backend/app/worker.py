import logging
import time
from datetime import datetime, timezone

from app.config import settings
from app.database import SessionLocal, init_db
from app.models import ExtractionJob
from app.services.job_processor import process_document_job
from app.services.retention_cleanup import cleanup_expired_previews_and_documents
from app.services.temporary_upload_store import upload_store
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("certificate-db-worker")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def main() -> None:
    """Optional DB-polling worker.

    This worker does not use RabbitMQ. It repeatedly checks PostgreSQL for
    queued jobs and processes them. For local prototype use, you can either use
    PROCESSING_MODE=background and skip this worker, or use PROCESSING_MODE=db_worker
    and run this worker in a separate terminal.
    """
    init_db()
    logger.info("DB worker started without RabbitMQ. polling=%ss", settings.db_worker_poll_seconds)
    last_cleanup_at = 0.0
    while True:
        now = time.time()
        if now - last_cleanup_at > 300:
            last_cleanup_at = now
            try:
                db_cleanup = SessionLocal()
                try:
                    cleanup_expired_previews_and_documents(db_cleanup)
                finally:
                    db_cleanup.close()
                upload_store.reap_orphans()
            except Exception as e:
                logger.warning("Periodic retention cleanup error: %s", e)
        db = SessionLocal()
        try:
            job = (
                db.query(ExtractionJob)
                .filter(ExtractionJob.status == "queued")
                .order_by(ExtractionJob.created_at.asc())
                .first()
            )
            if job is None:
                time.sleep(settings.db_worker_poll_seconds)
                continue
            job_id = job.id
            document_id = job.document_id
            db.close()
            process_document_job(job_id=job_id, document_id=document_id)
        except KeyboardInterrupt:
            logger.info("DB worker stopped.")
            break
        except Exception as exc:
            logger.exception("DB worker loop error: %s", exc)
            time.sleep(settings.db_worker_poll_seconds)
        finally:
            try:
                db.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
