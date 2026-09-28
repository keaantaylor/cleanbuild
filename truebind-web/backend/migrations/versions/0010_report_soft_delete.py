"""Soft delete for reports: originals and derived data are never removed by the app.

Revision ID: 0010_report_soft_delete
Revises: 0009_sso
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_report_soft_delete"
down_revision = "0009_sso"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("reports") as b:
        b.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
        b.add_column(sa.Column("deleted_by", sa.String(length=320), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("reports") as b:
        b.drop_column("deleted_by")
        b.drop_column("deleted_at")
