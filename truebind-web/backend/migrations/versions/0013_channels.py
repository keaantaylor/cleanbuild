"""P2 channels: inbound e-mail token, webhooks, SFTP destinations, ECB FX rates.

Revision ID: 0013_channels
Revises: 0012_idempotency_keys
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013_channels"
down_revision = "0012_idempotency_keys"
branch_labels = None
depends_on = None

_TENANT = "tenant_id = current_setting('app.tenant_id', true)"
_WORKER = "current_setting('app.worker', true) = 'on'"
_TENANT_TABLES = ("webhook_endpoints", "webhook_deliveries", "sftp_destinations")


def _fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["tenant_id"], ["tenants.id"], name=op.f(f"fk_{table}_tenant_id_tenants"), ondelete="CASCADE"
    )


def upgrade() -> None:
    with op.batch_alter_table("tenants") as batch:
        batch.add_column(sa.Column("inbound_token", sa.String(length=32), nullable=True))
        batch.create_unique_constraint("uq_tenants_inbound_token", ["inbound_token"])
    op.create_table(
        "webhook_endpoints",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("url", sa.String(length=2000), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=True),
        sa.Column("events", sa.JSON(), nullable=False),
        sa.Column("secret_enc", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        _fk("webhook_endpoints"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_webhook_endpoints")),
    )
    op.create_index(op.f("ix_webhook_endpoints_tenant_id"), "webhook_endpoints", ["tenant_id"])
    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("endpoint_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("message_id", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status_code", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        _fk("webhook_deliveries"),
        sa.ForeignKeyConstraint(
            ["endpoint_id"],
            ["webhook_endpoints.id"],
            name=op.f("fk_webhook_deliveries_endpoint_id_webhook_endpoints"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_webhook_deliveries")),
    )
    for col in ("tenant_id", "endpoint_id", "message_id", "status", "next_attempt_at"):
        op.create_index(op.f(f"ix_webhook_deliveries_{col}"), "webhook_deliveries", [col])
    op.create_table(
        "sftp_destinations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("host", sa.String(length=253), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=200), nullable=False),
        sa.Column("password_enc", sa.Text(), nullable=True),
        sa.Column("private_key_enc", sa.Text(), nullable=True),
        sa.Column("host_key_fingerprint", sa.String(length=200), nullable=False),
        sa.Column("remote_dir", sa.String(length=500), nullable=False),
        sa.Column("auto_deliver", sa.Boolean(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        _fk("sftp_destinations"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sftp_destinations")),
    )
    op.create_index(op.f("ix_sftp_destinations_tenant_id"), "sftp_destinations", ["tenant_id"], unique=True)
    op.create_table(
        "fx_rates",
        sa.Column("rate_date", sa.Date(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("rate", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.PrimaryKeyConstraint("rate_date", "currency", name=op.f("pk_fx_rates")),
    )
    if op.get_bind().dialect.name == "postgresql":
        for table in _TENANT_TABLES:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            # The worker dispatches due webhook deliveries across organisations (like job claims).
            using = f"({_TENANT}) OR ({_WORKER})" if table == "webhook_deliveries" else _TENANT
            op.execute(f"CREATE POLICY tenant_isolation ON {table} USING ({using}) WITH CHECK ({using})")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table in _TENANT_TABLES:
            op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
    op.drop_table("fx_rates")
    op.drop_index(op.f("ix_sftp_destinations_tenant_id"), table_name="sftp_destinations")
    op.drop_table("sftp_destinations")
    for col in ("tenant_id", "endpoint_id", "message_id", "status", "next_attempt_at"):
        op.drop_index(op.f(f"ix_webhook_deliveries_{col}"), table_name="webhook_deliveries")
    op.drop_table("webhook_deliveries")
    op.drop_index(op.f("ix_webhook_endpoints_tenant_id"), table_name="webhook_endpoints")
    op.drop_table("webhook_endpoints")
    with op.batch_alter_table("tenants") as batch:
        batch.drop_constraint("uq_tenants_inbound_token", type_="unique")
        batch.drop_column("inbound_token")
