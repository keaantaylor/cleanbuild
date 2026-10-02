"""Privacy controls: per-organisation name anonymisation, and a record of when
a deleted or expired report's data was physically purged. Additive.

Revision ID: 0019_privacy_controls
Revises: 0018_claim_policy_fields
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0019_privacy_controls"
down_revision = "0018_claim_policy_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tenants") as batch:
        batch.add_column(sa.Column("anonymise_names", sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table("reports") as batch:
        batch.add_column(sa.Column("purged_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("reports") as batch:
        batch.drop_column("purged_at")
    with op.batch_alter_table("tenants") as batch:
        batch.drop_column("anonymise_names")
