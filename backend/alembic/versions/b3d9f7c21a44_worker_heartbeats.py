"""worker heartbeats

Revision ID: b3d9f7c21a44
Revises: a7c3e5f91b02
Create Date: 2026-11-05

Tabel liveness per proses worker. Menjawab "berapa worker yang benar-benar
hidup" pada deployment multi-node tanpa bergantung pada healthcheck container.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b3d9f7c21a44"
down_revision: Union[str, Sequence[str], None] = "a7c3e5f91b02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "worker_heartbeats",
        sa.Column("worker_id", sa.String(length=80), nullable=False),
        sa.Column("hostname", sa.String(length=100), nullable=False),
        sa.Column("concurrency", sa.Integer(), nullable=False),
        sa.Column("in_flight", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("state", sa.String(length=20), nullable=False, server_default="idle"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("worker_id"),
    )
    op.create_index(
        "ix_worker_heartbeats_last_seen_at",
        "worker_heartbeats",
        ["last_seen_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_worker_heartbeats_last_seen_at", table_name="worker_heartbeats")
    op.drop_table("worker_heartbeats")
