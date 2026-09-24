"""worker_heartbeats: liveness registry for job workers

Revision ID: 0004_worker_heartbeats
Revises: 0003_fees_unmapped
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_worker_heartbeats"
down_revision = "0003_fees_unmapped"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "worker_heartbeats",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("hostname", sa.String(length=255), nullable=False),
        sa.Column("pid", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_job_id", sa.String(length=36), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_worker_heartbeats")),
    )
    op.create_index(op.f("ix_worker_heartbeats_last_seen_at"), "worker_heartbeats", ["last_seen_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_worker_heartbeats_last_seen_at"), table_name="worker_heartbeats")
    op.drop_table("worker_heartbeats")
