"""Durable object storage in PostgreSQL (STORAGE_BACKEND=db): uploaded
originals and the parsed-workbook cache survive restarts on ephemeral disks.
Tenant-owned, Row Level Security like every other tenant table.

Revision ID: 0017_stored_blobs
Revises: 0016_billing
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017_stored_blobs"
down_revision = "0016_billing"
branch_labels = None
depends_on = None

_TENANT = "tenant_id = current_setting('app.tenant_id', true)"


def upgrade() -> None:
    op.create_table(
        "stored_blobs",
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_stored_blobs_tenant_id_tenants"),
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_stored_blobs")),
    )
    op.create_index(op.f("ix_stored_blobs_tenant_id"), "stored_blobs", ["tenant_id"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE stored_blobs ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE stored_blobs FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY tenant_isolation ON stored_blobs USING ({_TENANT}) WITH CHECK ({_TENANT})")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS tenant_isolation ON stored_blobs")
    op.drop_index(op.f("ix_stored_blobs_tenant_id"), table_name="stored_blobs")
    op.drop_table("stored_blobs")
