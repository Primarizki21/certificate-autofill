import logging
import os
import socket
import time
from datetime import datetime, timezone
from sqlalchemy import or_
from app.config import settings
from app.database import SessionLocal, init_db
from app.models import ExtractionJob
from app.services.job_processor import cleanup_expired_jobs_and_uploads, process_document_job

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("certificate-db-worker")
WORKER_ID = f"{socket.gethostname()[:32]}-{os.getpid()}"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def main() -> None:
    """Poll and claim queued jobs without RabbitMQ."""
    init_db()
    next_cleanup = 0.0
    logger.info("DB worker started without RabbitMQ. polling=%ss", settings.db_worker_poll_seconds)
    while True:
        db = SessionLocal()
        try:
            if time.monotonic() >= next_cleanup:
                cleanup_expired_jobs_and_uploads()
                next_cleanup = time.monotonic() + max(1, settings.storage_cleanup_interval_seconds)

            job = (
                db.query(ExtractionJob)
                .filter(
                    ExtractionJob.status == "queued",
                    or_(ExtractionJob.available_at.is_(None), ExtractionJob.available_at <= utcnow()),
                )
                .order_by(ExtractionJob.created_at.asc())
                .first()
            )
            if job is None:
                time.sleep(settings.db_worker_poll_seconds)
                continue
            job_id = job.id
            document_id = job.document_id
            db.close()
            process_document_job(job_id=job_id, document_id=document_id, worker_id=WORKER_ID)
        except KeyboardInterrupt:
            logger.info("DB worker stopped.")
            break
        except Exception as exc:
            logger.exception("DB worker loop error: %s", exc)
            time.sleep(settings.db_worker_poll_seconds)
        finally:
            db.close()
