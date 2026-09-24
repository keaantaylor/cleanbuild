"""inbound provenance on reports; outbound deliveries table (tenant-scoped, RLS)

Revision ID: 0005_inbound_outbound
Revises: 0004_worker_heartbeats
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_inbound_outbound"
down_revision = "0004_worker_heartbeats"
branch_labels = None
depends_on = None

_MATCH = "tenant_id = current_setting('app.tenant_id', true)"


def upgrade() -> None:
    with op.batch_alter_table("reports") as b:
        b.add_column(sa.Column("source_channel", sa.String(length=16), nullable=False, server_default="upload"))
        b.add_column(sa.Column("sender", sa.String(length=200), nullable=True))
        b.add_column(sa.Column("programme", sa.String(length=200), nullable=True))
    op.create_table(
        "deliveries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("report_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("destination", sa.String(length=320), nullable=True),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("created_by", sa.String(length=320), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["report_id"], ["reports.id"], name=op.f("fk_deliveries_report_id_reports"),
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_deliveries_tenant_id_tenants"),
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_deliveries")),
    )
    op.create_index(op.f("ix_deliveries_report_id"), "deliveries", ["report_id"])
    op.create_index(op.f("ix_deliveries_tenant_id"), "deliveries", ["tenant_id"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE deliveries ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE deliveries FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY tenant_isolation ON deliveries USING ({_MATCH}) WITH CHECK ({_MATCH})")


def downgrade() -> None:
    op.drop_index(op.f("ix_deliveries_tenant_id"), table_name="deliveries")
    op.drop_index(op.f("ix_deliveries_report_id"), table_name="deliveries")
    op.drop_table("deliveries")
    with op.batch_alter_table("reports") as b:
        b.drop_column("programme")
        b.drop_column("sender")
        b.drop_column("source_channel")
