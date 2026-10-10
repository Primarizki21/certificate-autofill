import logging
import os
import signal
import socket
import threading
import time
from datetime import datetime, timezone
from app.config import settings
from app.database import init_db
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

def worker_thread_loop(thread_id: int) -> None:
    """Individual worker thread loop executing concurrently within one worker process."""
    sub_id = f"{WORKER_ID}-t{thread_id}"
    logger.info("Worker thread started: %s", sub_id)
    while not shutdown_event.is_set():
        try:
            processed = process_document_job(worker_id=sub_id)
            if not processed:
                shutdown_event.wait(timeout=settings.db_worker_poll_seconds)
        except Exception as exc:
            logger.exception("Worker thread %s error: %s", sub_id, exc)
            shutdown_event.wait(timeout=settings.db_worker_poll_seconds)
    logger.info("Worker thread stopped: %s", sub_id)



def main() -> None:
    """Poll and claim queued jobs without RabbitMQ, with graceful shutdown support."""
    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    try:
        from prometheus_client import start_http_server

        worker_metrics_port = int(os.getenv("WORKER_METRICS_PORT", "9102"))
        start_http_server(worker_metrics_port)
        logger.info("Worker Prometheus metrics server listening on port %d", worker_metrics_port)
    except Exception as exc:
        logger.warning("Could not start worker metrics server: %s", exc)

    init_db()
    next_cleanup = 0.0
    concurrency = max(1, settings.worker_concurrency)
    logger.info(
        "DB worker started without RabbitMQ. worker_id=%s polling=%ss concurrency=%d",
        WORKER_ID,
        settings.db_worker_poll_seconds,
        concurrency,
    )

    if concurrency == 1:
        while not shutdown_event.is_set():
            try:
                if time.monotonic() >= next_cleanup:
                    cleanup_expired_jobs_and_uploads()
                    next_cleanup = time.monotonic() + max(1, settings.storage_cleanup_interval_seconds)

                processed = process_document_job(worker_id=WORKER_ID)
                if not processed:
                    shutdown_event.wait(timeout=settings.db_worker_poll_seconds)
            except Exception as exc:
                logger.exception("DB worker loop error: %s", exc)
                shutdown_event.wait(timeout=settings.db_worker_poll_seconds)
    else:
        threads: list[threading.Thread] = []
        for i in range(1, concurrency + 1):
            t = threading.Thread(target=worker_thread_loop, args=(i,), daemon=True)
            t.start()
            threads.append(t)

        while not shutdown_event.is_set():
            try:
                if time.monotonic() >= next_cleanup:
                    cleanup_expired_jobs_and_uploads()
                    next_cleanup = time.monotonic() + max(1, settings.storage_cleanup_interval_seconds)
            except Exception as exc:
                logger.warning("Cleanup error: %s", exc)
            shutdown_event.wait(timeout=1.0)

        for t in threads:
            t.join(timeout=5)
    logger.info("DB worker stopped cleanly. worker_id=%s", WORKER_ID)


if __name__ == "__main__":
    main()
