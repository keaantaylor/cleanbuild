"""P9 billing: subscription state on tenants; processed Stripe event ids.

Revision ID: 0016_billing
Revises: 0015_sanctions
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016_billing"
down_revision = "0015_sanctions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tenants") as batch:
        batch.add_column(sa.Column("billing_plan", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("billing_status", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("stripe_customer_id", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("stripe_subscription_id", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("billing_period_end", sa.DateTime(timezone=True), nullable=True))
        batch.create_unique_constraint("uq_tenants_stripe_customer_id", ["stripe_customer_id"])
    # Stripe event ids already applied (webhooks are delivered at least once). Not tenant data.
    op.create_table(
        "billing_events",
        sa.Column("id", sa.String(length=255), nullable=False),
        sa.Column("type", sa.String(length=100), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_billing_events")),
    )


def downgrade() -> None:
    op.drop_table("billing_events")
    with op.batch_alter_table("tenants") as batch:
        batch.drop_constraint("uq_tenants_stripe_customer_id", type_="unique")
        for col in (
            "billing_period_end",
            "stripe_subscription_id",
            "stripe_customer_id",
            "billing_status",
            "billing_plan",
        ):
            batch.drop_column(col)
