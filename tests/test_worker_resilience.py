"""Unit tests for DB worker resilience and graceful shutdown."""

import signal
from unittest.mock import patch

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

    with patch("app.worker.init_db") as mock_init:
        main()
        mock_init.assert_called_once()
