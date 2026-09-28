"""P3 check modules: findings, module runs, binders; reports.binder_id.

Revision ID: 0014_modules_binders
Revises: 0013_channels
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014_modules_binders"
down_revision = "0013_channels"
branch_labels = None
depends_on = None

_TENANT = "tenant_id = current_setting('app.tenant_id', true)"
_TABLES = ("binders", "module_runs", "findings")


def _fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["tenant_id"], ["tenants.id"], name=op.f(f"fk_{table}_tenant_id_tenants"), ondelete="CASCADE"
    )


def _report_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["report_id"], ["reports.id"], name=op.f(f"fk_{table}_report_id_reports"), ondelete="CASCADE"
    )


def upgrade() -> None:
    op.create_table(
        "binders",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("umr", sa.String(length=64), nullable=True),
        sa.Column("coverholder", sa.String(length=200), nullable=True),
        sa.Column("inception_date", sa.Date(), nullable=False),
        sa.Column("expiry_date", sa.Date(), nullable=False),
        sa.Column("currencies", sa.JSON(), nullable=False),
        sa.Column("limit_currency", sa.String(length=3), nullable=False),
        sa.Column("claims_authority", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("aggregate_limit", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        _fk("binders"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_binders")),
    )
    op.create_index(op.f("ix_binders_tenant_id"), "binders", ["tenant_id"])
    with op.batch_alter_table("reports") as batch:
        batch.add_column(sa.Column("binder_id", sa.String(length=36), nullable=True))
        batch.create_foreign_key(
            op.f("fk_reports_binder_id_binders"), "binders", ["binder_id"], ["id"], ondelete="SET NULL"
        )
        batch.create_index(op.f("ix_reports_binder_id"), ["binder_id"])
    op.create_table(
        "module_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("report_id", sa.String(length=36), nullable=False),
        sa.Column("module", sa.String(length=32), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("rules", sa.JSON(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column("finding_count", sa.Integer(), nullable=False),
        sa.Column("ran_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ran_by", sa.String(length=255), nullable=False),
        _fk("module_runs"),
        _report_fk("module_runs"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_module_runs")),
        sa.UniqueConstraint("report_id", "module", name="uq_module_runs_report_module"),
    )
    for col in ("tenant_id", "report_id"):
        op.create_index(op.f(f"ix_module_runs_{col}"), "module_runs", [col])
    op.create_table(
        "findings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("report_id", sa.String(length=36), nullable=False),
        sa.Column("module", sa.String(length=32), nullable=False),
        sa.Column("rule_code", sa.String(length=48), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("explanation", sa.String(length=2000), nullable=False),
        sa.Column("sheet_name", sa.String(length=255), nullable=True),
        sa.Column("row_number", sa.Integer(), nullable=True),
        sa.Column("field_code", sa.String(length=32), nullable=True),
        sa.Column("source_column", sa.String(length=255), nullable=True),
        sa.Column("claim_row_id", sa.String(length=36), nullable=True),
        sa.Column("claim_reference", sa.String(length=255), nullable=True),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("disposition", sa.String(length=16), nullable=False),
        sa.Column("disposition_note", sa.String(length=1000), nullable=True),
        sa.Column("disposed_by", sa.String(length=255), nullable=True),
        sa.Column("disposed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        _fk("findings"),
        _report_fk("findings"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_findings")),
    )
    for col in ("tenant_id", "report_id", "module", "fingerprint"):
        op.create_index(op.f(f"ix_findings_{col}"), "findings", [col])
    if op.get_bind().dialect.name == "postgresql":
        for table in _TABLES:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            op.execute(f"CREATE POLICY tenant_isolation ON {table} USING ({_TENANT}) WITH CHECK ({_TENANT})")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table in _TABLES:
            op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
    for col in ("tenant_id", "report_id", "module", "fingerprint"):
        op.drop_index(op.f(f"ix_findings_{col}"), table_name="findings")
    op.drop_table("findings")
    for col in ("tenant_id", "report_id"):
        op.drop_index(op.f(f"ix_module_runs_{col}"), table_name="module_runs")
    op.drop_table("module_runs")
    with op.batch_alter_table("reports") as batch:
        batch.drop_index(op.f("ix_reports_binder_id"))
        batch.drop_constraint(op.f("fk_reports_binder_id_binders"), type_="foreignkey")
        batch.drop_column("binder_id")
    op.drop_index(op.f("ix_binders_tenant_id"), table_name="binders")
    op.drop_table("binders")
