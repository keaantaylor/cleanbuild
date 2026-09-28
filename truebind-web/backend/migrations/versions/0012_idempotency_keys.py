"""Idempotency keys for upload and process requests (tenant-scoped, RLS).

Revision ID: 0012_idempotency_keys
Revises: 0011_money_numeric
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_idempotency_keys"
down_revision = "0011_money_numeric"
branch_labels = None
depends_on = None

_TENANT = "tenant_id = current_setting('app.tenant_id', true)"


def upgrade() -> None:
    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_idempotency_keys_tenant_id_tenants"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_idempotency_keys")),
        sa.UniqueConstraint("tenant_id", "scope", "key", name="uq_idempotency_keys_tenant_scope_key"),
    )
    op.create_index(op.f("ix_idempotency_keys_tenant_id"), "idempotency_keys", ["tenant_id"])
    op.create_index(op.f("ix_idempotency_keys_expires_at"), "idempotency_keys", ["expires_at"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE idempotency_keys ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE idempotency_keys FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY tenant_isolation ON idempotency_keys USING ({_TENANT}) WITH CHECK ({_TENANT})")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS tenant_isolation ON idempotency_keys")
    op.drop_index(op.f("ix_idempotency_keys_expires_at"), table_name="idempotency_keys")
    op.drop_index(op.f("ix_idempotency_keys_tenant_id"), table_name="idempotency_keys")
    op.drop_table("idempotency_keys")
