"""Execution policy and the full record on every correction: the policy that
governed it, the evidence it answered, how it was approved, and the result of
the re-check. Additive and nullable.

Revision ID: 0022_correction_policy
Revises: 0021_corrections_versions
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0022_correction_policy"
down_revision = "0021_corrections_versions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("corrections") as batch:
        batch.add_column(sa.Column("policy", sa.String(length=24), nullable=True))
        batch.add_column(sa.Column("policy_reason", sa.Text(), nullable=True))
        batch.add_column(sa.Column("field_code", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("evidence", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("approval", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("result", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("corrections") as batch:
        for col in ("result", "approval", "evidence", "field_code", "policy_reason", "policy"):
            batch.drop_column(col)
