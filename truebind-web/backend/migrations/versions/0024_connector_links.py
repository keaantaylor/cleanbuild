"""Connector links: a report's workbook opened in Microsoft 365 or Google
Sheets, with the hash of the bytes it started from. Additive; tenant-scoped
with Row Level Security like every other tenant table.

Revision ID: 0024_connector_links
Revises: 0023_memory_email_loop
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0024_connector_links"
down_revision = "0023_memory_email_loop"
branch_labels = None
depends_on = None

_TENANT = "tenant_id = current_setting('app.tenant_id', true)"


def upgrade() -> None:
    op.create_table(
        "connector_links",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("report_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("file_id", sa.String(length=255), nullable=False),
        sa.Column("web_url", sa.String(length=2000), nullable=False),
        sa.Column("base_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.String(length=320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_pulled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_connector_links_tenant_id_tenants"),
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["report_id"], ["reports.id"], name=op.f("fk_connector_links_report_id_reports"),
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_connector_links")),
    )
    op.create_index(op.f("ix_connector_links_tenant_id"), "connector_links", ["tenant_id"])
    op.create_index(op.f("ix_connector_links_report_id"), "connector_links", ["report_id"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE connector_links ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE connector_links FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY tenant_isolation ON connector_links USING ({_TENANT}) WITH CHECK ({_TENANT})")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS tenant_isolation ON connector_links")
    op.drop_table("connector_links")
