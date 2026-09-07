"""Migrate existing databases to ephemeral zero-PDF storage."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings
from app.database import Base
from app import models

LEGACY_TABLES = ("parsed_documents", "document_files")
REQUIRED_COLUMNS = {
    "documents": {"parser_engine": "VARCHAR(150)"},
    "extraction_jobs": {
        "temp_file_key": "VARCHAR(64)",
        "available_at": "TIMESTAMP WITH TIME ZONE",
        "lease_expires_at": "TIMESTAMP WITH TIME ZONE",
        "worker_id": "VARCHAR(64)",
    },
}


def inspect_cutover(engine: Engine) -> dict[str, object]:
    """Report migration work without exposing the database URL."""
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    missing_columns: dict[str, list[str]] = {}
    for table, columns in REQUIRED_COLUMNS.items():
        existing = {column["name"] for column in inspector.get_columns(table)} if table in tables else set()
        missing = [column for column in columns if column not in existing]
        if missing:
            missing_columns[table] = missing
    return {
        "legacy_tables": [table for table in LEGACY_TABLES if table in tables],
        "missing_columns": missing_columns,
    }


def apply_ephemeral_storage_cutover(
    engine: Engine,
    *,
    maintenance_window_confirmed: bool = False,
) -> dict[str, object]:
    """Add queue fields, then permanently remove legacy PDF and OCR tables."""
    if not maintenance_window_confirmed:
        raise ValueError("A maintenance window is required before destructive migration.")
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        state = inspect_cutover(engine)
        for table, columns in REQUIRED_COLUMNS.items():
            for column in state["missing_columns"].get(table, []):
                definition = REQUIRED_COLUMNS[table][column]
                connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))
        for table in state["legacy_tables"]:
            connection.execute(text(f"DROP TABLE {table}"))
    return inspect_cutover(engine)


def main() -> None:
    parser = argparse.ArgumentParser(description="Cut over PostgreSQL to ephemeral zero-PDF storage.")
    parser.add_argument("--database-url", default=settings.database_url)
    parser.add_argument("--apply", action="store_true", help="Apply schema changes instead of dry-run.")
    parser.add_argument(
        "--confirm-delete-legacy-storage",
        action="store_true",
        help="Confirm permanent deletion of document_files and parsed_documents.",
    )
    parser.add_argument(
        "--confirm-maintenance-window",
        action="store_true",
        help="Confirm all API instances and workers are stopped before applying the migration.",
    )
    args = parser.parse_args()
    engine = create_engine(args.database_url, pool_pre_ping=True)
    before = inspect_cutover(engine)

    if not args.apply:
        print(json.dumps({"mode": "dry-run", **before}, indent=2, sort_keys=True))
        return
    if not args.confirm_maintenance_window:
        parser.error("Stop every API instance and worker, then add --confirm-maintenance-window.")
    if before["legacy_tables"] and not args.confirm_delete_legacy_storage:
        parser.error("Legacy PDF/OCR tables detected; add --confirm-delete-legacy-storage after verified backup.")

    after = apply_ephemeral_storage_cutover(engine, maintenance_window_confirmed=True)
    print(json.dumps({"mode": "applied", "before": before, "after": after}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
