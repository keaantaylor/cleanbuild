"""Policy-context fields on claim rows (inception, expiry, limit, binder/UMR),
so per-row checks can run: loss outside the policy period, incurred over the
policy limit and unknown binder. Additive and nullable.

Revision ID: 0018_claim_policy_fields
Revises: 0017_stored_blobs
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018_claim_policy_fields"
down_revision = "0017_stored_blobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("claim_rows") as batch:
        batch.add_column(sa.Column("policy_inception", sa.Date(), nullable=True))
        batch.add_column(sa.Column("policy_expiry", sa.Date(), nullable=True))
        batch.add_column(sa.Column("policy_limit", sa.Numeric(18, 2), nullable=True))
        batch.add_column(sa.Column("binder_reference", sa.String(length=255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("claim_rows") as batch:
        for col in ("binder_reference", "policy_limit", "policy_expiry", "policy_inception"):
            batch.drop_column(col)
