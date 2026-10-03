import logging
import os
import signal
import socket
import threading
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

shutdown_event = threading.Event()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def handle_shutdown(signum: int, frame: object) -> None:
    """Handle termination signals (SIGTERM, SIGINT) and trigger graceful exit."""
    sig_name = signal.Signals(signum).name
    logger.info(
        "Received termination signal %s (%s). Initiating graceful worker shutdown...",
        sig_name,
        signum,
    )
    shutdown_event.set()


def main() -> None:
    """Poll and claim queued jobs without RabbitMQ, with graceful shutdown support."""
    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    try:
        from prometheus_client import start_http_server

        worker_metrics_port = int(os.getenv("WORKER_METRICS_PORT", "8001"))
        start_http_server(worker_metrics_port)
        logger.info("Worker Prometheus metrics server listening on port %d", worker_metrics_port)
    except Exception as exc:
        logger.warning("Could not start worker metrics server: %s", exc)

    init_db()
    next_cleanup = 0.0
    logger.info(
        "DB worker started without RabbitMQ. worker_id=%s polling=%ss",
        WORKER_ID,
        settings.db_worker_poll_seconds,
    )

    while not shutdown_event.is_set():
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
                db.close()
                shutdown_event.wait(timeout=settings.db_worker_poll_seconds)
                continue

            job_id = job.id
            document_id = job.document_id
            db.close()

            logger.info("Worker %s claimed job %s for document %s", WORKER_ID, job_id, document_id)
            process_document_job(job_id=job_id, document_id=document_id, worker_id=WORKER_ID)
        except Exception as exc:
            logger.exception("DB worker loop error: %s", exc)
            shutdown_event.wait(timeout=settings.db_worker_poll_seconds)
        finally:
            db.close()

    logger.info("DB worker stopped cleanly. worker_id=%s", WORKER_ID)


if __name__ == "__main__":
    main()
