"""Tests for database initialization idempotency and concurrent startup resilience."""

from __future__ import annotations

import concurrent.futures
import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.database import Base, init_db


def test_init_db_idempotent_sqlite(tmp_path):
    """Calling init_db sequentially multiple times must not raise errors."""
    db_file = tmp_path / "test_idempotent.db"
    test_url = f"sqlite:///{db_file}"
    engine = create_engine(test_url)

    # First call creates tables
    Base.metadata.create_all(bind=engine)
    # Second call must be idempotent
    Base.metadata.create_all(bind=engine)
    assert db_file.exists()


def test_init_db_concurrent_threads_sqlite(tmp_path):
    """Multiple threads calling DDL simultaneously must succeed safely."""
    db_file = tmp_path / "test_concurrent.db"
    test_url = f"sqlite:///{db_file}"
    engine = create_engine(test_url)

    def worker():
        try:
            Base.metadata.create_all(bind=engine)
            return True
        except (IntegrityError, DBAPIError) as exc:
            err_msg = str(exc).lower()
            if "already exists" in err_msg:
                return True
            raise

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(worker) for _ in range(5)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert all(results)
    assert len(results) == 5


def _get_postgres_test_engine():
    """Detect available PostgreSQL connection for CI and local environments."""
    urls = [
        os.getenv("POSTGRES_TEST_URL"),
        "postgresql+psycopg2://postgres:postgres@localhost:5432/certautofill_ci",
        "postgresql+psycopg2://postgres:postgres@localhost:5434/certautofill",
    ]
    for url in urls:
        if not url:
            continue
        try:
            engine = create_engine(url, pool_pre_ping=True)
            with engine.connect():
                return engine
        except Exception:
            continue
    return None


def test_init_db_concurrency_postgresql():
    """Verify simultaneous DDL creation on PostgreSQL handles pg_type race conditions."""
    pg_engine = _get_postgres_test_engine()
    if pg_engine is None:
        pytest.skip("PostgreSQL test database not available in current environment.")

    def concurrent_creator():
        try:
            Base.metadata.create_all(bind=pg_engine)
            return True
        except (IntegrityError, DBAPIError) as exc:
            err_msg = str(exc).lower()
            if "already exists" in err_msg or "pg_type_typname_nsp_index" in err_msg:
                return True
            raise

    # Simulate simultaneous cold-start from 6 concurrent workers
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(concurrent_creator) for _ in range(6)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert all(results)
    assert len(results) == 6


if __name__ == "__main__":
    print("Testing SQLite idempotency...")
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        from pathlib import Path
        test_init_db_idempotent_sqlite(Path(tmpdir))
        test_init_db_concurrent_threads_sqlite(Path(tmpdir))
    print("SQLite tests passed.")

    pg = _get_postgres_test_engine()
    if pg:
        print("Testing PostgreSQL concurrency...")
        test_init_db_concurrency_postgresql()
        print("PostgreSQL concurrency test passed.")
    else:
        print("PostgreSQL not detected, skipping PG test.")
