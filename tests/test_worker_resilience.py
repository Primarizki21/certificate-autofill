"""Unit tests for DB worker resilience and graceful shutdown."""

import signal

from app.worker import handle_shutdown, main, shutdown_event


def test_handle_shutdown_triggers_event():
    """Verify handle_shutdown sets shutdown_event and logs signal name."""
    shutdown_event.clear()
    assert not shutdown_event.is_set()

    handle_shutdown(signal.SIGTERM, None)
    assert shutdown_event.is_set()


def test_handle_shutdown_sigint():
    """Verify handle_shutdown sets shutdown_event on SIGINT."""
    shutdown_event.clear()
    handle_shutdown(signal.SIGINT, None)
    assert shutdown_event.is_set()


def test_worker_main_loop_exits_when_shutdown_signaled():
    """Verify main loop terminates immediately when shutdown_event is already set."""
    shutdown_event.set()
    main()


def test_idle_backoff_is_bounded_and_jittered():
    from app import worker

    first = worker._next_idle_wait(1.0)
    assert 0 < first <= 5.0
    assert worker._next_idle_wait(100.0) <= 5.0


def test_heartbeat_upsert_and_delete(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app import worker
    from app.database import Base
    from app.models import WorkerHeartbeat

    engine = create_engine(f"sqlite:///{tmp_path / 'heartbeat.db'}")
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)
    monkeypatch.setattr(worker, "SessionLocal", TestSession)

    worker.shutdown_event.clear()
    worker._write_heartbeat()
    worker._write_heartbeat()

    db = TestSession()
    rows = db.query(WorkerHeartbeat).all()
    assert len(rows) == 1
    assert rows[0].worker_id == worker.WORKER_ID
    assert rows[0].state == "idle"
    db.close()

    worker._delete_heartbeat()
    db = TestSession()
    assert db.query(WorkerHeartbeat).count() == 0
    db.close()
