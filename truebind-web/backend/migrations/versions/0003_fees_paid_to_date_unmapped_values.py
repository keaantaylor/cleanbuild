"""claim_rows: fees/expenses paid to date, and retained values of unmapped source columns

Revision ID: 0003_fees_unmapped
Revises: 0002_pg_security
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_fees_unmapped"
down_revision = "0002_pg_security"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("claim_rows") as b:
        b.add_column(sa.Column("fees_paid_to_date", sa.Float(), nullable=True))
        b.add_column(sa.Column("unmapped_values", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("claim_rows") as b:
        b.drop_column("unmapped_values")
        b.drop_column("fees_paid_to_date")
