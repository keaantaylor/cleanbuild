"""Corrections (cell changes kept apart from the source file) and workbook
versions (original / corrected / approved, each with its SHA-256). Additive;
tenant-scoped with Row Level Security like every other tenant table.

Revision ID: 0021_corrections_versions
Revises: 0020_leads
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0021_corrections_versions"
down_revision = "0020_leads"
branch_labels = None
depends_on = None

_TENANT = "tenant_id = current_setting('app.tenant_id', true)"


def _fks(table: str) -> list:
    return [
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f(f"fk_{table}_tenant_id_tenants"),
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["report_id"], ["reports.id"], name=op.f(f"fk_{table}_report_id_reports"),
                                ondelete="CASCADE"),
    ]


def upgrade() -> None:
    op.create_table(
        "corrections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("report_id", sa.String(length=36), nullable=False),
        sa.Column("issue_id", sa.String(length=36), nullable=True),
        sa.Column("sheet_name", sa.String(length=255), nullable=False),
        sa.Column("cell", sa.String(length=16), nullable=False),
        sa.Column("before_value", sa.Text(), nullable=True),
        sa.Column("after_value", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("rule", sa.String(length=64), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("proposed_by", sa.String(length=320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_by", sa.String(length=320), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        *_fks("corrections"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_corrections")),
    )
    op.create_index(op.f("ix_corrections_tenant_id"), "corrections", ["tenant_id"])
    op.create_index(op.f("ix_corrections_report_id"), "corrections", ["report_id"])
    op.create_index(op.f("ix_corrections_issue_id"), "corrections", ["issue_id"])
    op.create_table(
        "workbook_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("report_id", sa.String(length=36), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("corrections", sa.JSON(), nullable=True),
        sa.Column("based_on", sa.String(length=36), nullable=True),
        sa.Column("created_by", sa.String(length=320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        *_fks("workbook_versions"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workbook_versions")),
        sa.UniqueConstraint("report_id", "number", name=op.f("uq_workbook_versions_report_id_number")),
    )
    op.create_index(op.f("ix_workbook_versions_tenant_id"), "workbook_versions", ["tenant_id"])
    op.create_index(op.f("ix_workbook_versions_report_id"), "workbook_versions", ["report_id"])
    if op.get_bind().dialect.name == "postgresql":
        for table in ("corrections", "workbook_versions"):
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            op.execute(f"CREATE POLICY tenant_isolation ON {table} USING ({_TENANT}) WITH CHECK ({_TENANT})")


def downgrade() -> None:
    for table in ("workbook_versions", "corrections"):
        if op.get_bind().dialect.name == "postgresql":
            op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.drop_table(table)
