import logging
import os
import random
import signal
import socket
import threading
import time
from datetime import datetime, timezone
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from app.config import settings
from app.database import SessionLocal
from app.models import WorkerHeartbeat
from app.services.job_processor import cleanup_expired_jobs_and_uploads, process_document_job

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("certificate-db-worker")
WORKER_ID = f"{socket.gethostname()[:32]}-{os.getpid()}"
WORKER_STARTED_AT = datetime.now(timezone.utc)

shutdown_event = threading.Event()

_in_flight = 0
_in_flight_lock = threading.Lock()


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


def _update_in_flight(delta: int) -> None:
    global _in_flight
    with _in_flight_lock:
        _in_flight = max(0, _in_flight + delta)


def _heartbeat_values() -> dict[str, object]:
    with _in_flight_lock:
        in_flight = _in_flight
    return {
        "worker_id": WORKER_ID,
        "hostname": socket.gethostname()[:100],
        "concurrency": max(1, settings.worker_concurrency),
        "in_flight": in_flight,
        "state": "busy" if in_flight else "idle",
        "started_at": WORKER_STARTED_AT,
        "last_seen_at": utcnow(),
    }


def _write_heartbeat() -> None:
    """Upsert satu baris liveness; kegagalan DB hanya dicatat, worker tetap jalan."""
    db = SessionLocal()
    try:
        values = _heartbeat_values()
        if db.get_bind().dialect.name == "postgresql":
            statement = (
                postgresql_insert(WorkerHeartbeat)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=[WorkerHeartbeat.worker_id],
                    set_={
                        key: values[key]
                        for key in (
                            "hostname",
                            "concurrency",
                            "in_flight",
                            "state",
                            "last_seen_at",
                        )
                    },
                )
            )
        else:
            db.query(WorkerHeartbeat).filter(
                WorkerHeartbeat.worker_id == WORKER_ID
            ).delete()
            statement = WorkerHeartbeat.__table__.insert().values(**values)
        db.execute(statement)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("Heartbeat gagal ditulis: %s", exc)
    finally:
        db.close()


def _delete_heartbeat() -> None:
    db = SessionLocal()
    try:
        db.query(WorkerHeartbeat).filter(WorkerHeartbeat.worker_id == WORKER_ID).delete()
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.debug("Heartbeat tidak bisa dihapus saat shutdown: %s", exc)
    finally:
        db.close()


def heartbeat_loop() -> None:
    interval = max(1, settings.worker_heartbeat_seconds)
    while not shutdown_event.is_set():
        _write_heartbeat()
        shutdown_event.wait(timeout=interval)


def _next_idle_wait(current: float) -> float:
    """Backoff eksponensial dengan jitter agar worker tidak polling serentak."""
    base = max(1.0, float(settings.db_worker_poll_seconds))
    cap = max(base, float(settings.worker_idle_backoff_max_seconds))
    doubled = min(cap, current * 2)
    return min(cap, doubled * random.uniform(0.8, 1.2))


def worker_thread_loop(thread_id: int) -> None:
    """Individual worker thread loop executing concurrently within one worker process."""
    sub_id = f"{WORKER_ID}-t{thread_id}"
    logger.info("Worker thread started: %s", sub_id)
    wait = float(settings.db_worker_poll_seconds)
    while not shutdown_event.is_set():
        try:
            _update_in_flight(1)
            try:
                processed = process_document_job(worker_id=sub_id)
            finally:
                _update_in_flight(-1)
            if processed:
                wait = float(settings.db_worker_poll_seconds)
            else:
                shutdown_event.wait(timeout=wait)
                wait = _next_idle_wait(wait)
        except Exception as exc:
            logger.exception("Worker thread %s error: %s", sub_id, exc)
            shutdown_event.wait(timeout=wait)
            wait = _next_idle_wait(wait)
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

    heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True)
    heartbeat_thread.start()

    next_cleanup = 0.0
    concurrency = max(1, settings.worker_concurrency)
    logger.info(
        "DB worker started without RabbitMQ. worker_id=%s polling=%ss concurrency=%d heartbeat=%ss",
        WORKER_ID,
        settings.db_worker_poll_seconds,
        concurrency,
        settings.worker_heartbeat_seconds,
    )

    if concurrency == 1:
        wait = float(settings.db_worker_poll_seconds)
        while not shutdown_event.is_set():
            try:
                if time.monotonic() >= next_cleanup:
                    cleanup_expired_jobs_and_uploads()
                    next_cleanup = time.monotonic() + max(1, settings.storage_cleanup_interval_seconds)

                _update_in_flight(1)
                try:
                    processed = process_document_job(worker_id=WORKER_ID)
                finally:
                    _update_in_flight(-1)
                if processed:
                    wait = float(settings.db_worker_poll_seconds)
                else:
                    shutdown_event.wait(timeout=wait)
                    wait = _next_idle_wait(wait)
            except Exception as exc:
                logger.exception("DB worker loop error: %s", exc)
                shutdown_event.wait(timeout=wait)
                wait = _next_idle_wait(wait)
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

    _delete_heartbeat()
    heartbeat_thread.join(timeout=2)
    logger.info("DB worker stopped cleanly. worker_id=%s", WORKER_ID)


if __name__ == "__main__":
    main()
