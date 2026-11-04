"""queued jobs partial index

Revision ID: a7c3e5f91b02
Revises: b1ffa32f19bf
Create Date: 2026-11-05

Partial index untuk klaim job: hanya baris status='queued' yang masuk index,
sehingga ukuran index mengikuti panjang antrean, bukan total riwayat job.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a7c3e5f91b02"
down_revision: Union[str, Sequence[str], None] = "b1ffa32f19bf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.create_index(
        "ix_extraction_jobs_queued_created",
        "extraction_jobs",
        ["created_at"],
        postgresql_where=sa.text("status = 'queued'"),
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.drop_index("ix_extraction_jobs_queued_created", table_name="extraction_jobs")
