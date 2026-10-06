"""Counterparty memory and the e-mail loop: approved reusable rules (created
only by a person, from corrections observed repeatedly) and information
requests (one per question sent to a sender, matched back by its [TB-n]
reference when the sender replies). Additive; tenant-scoped with Row Level
Security like every other tenant table.

Revision ID: 0023_memory_email_loop
Revises: 0022_correction_policy
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0023_memory_email_loop"
down_revision = "0022_correction_policy"
branch_labels = None
depends_on = None

_TENANT = "tenant_id = current_setting('app.tenant_id', true)"


def _tenant_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f(f"fk_{table}_tenant_id_tenants"),
                                   ondelete="CASCADE")


def upgrade() -> None:
    op.create_table(
        "approved_rules",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("sender", sa.String(length=200), nullable=True),
        sa.Column("field_code", sa.String(length=32), nullable=True),
        sa.Column("rule", sa.String(length=64), nullable=True),
        sa.Column("match_value", sa.Text(), nullable=True),
        sa.Column("replace_value", sa.Text(), nullable=True),
        sa.Column("observed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="ACTIVE"),
        sa.Column("applied", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.String(length=320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        _tenant_fk("approved_rules"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_approved_rules")),
    )
    op.create_index(op.f("ix_approved_rules_tenant_id"), "approved_rules", ["tenant_id"])
    op.create_table(
        "info_requests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("report_id", sa.String(length=36), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("root_cause", sa.String(length=300), nullable=False),
        sa.Column("issue_ids", sa.JSON(), nullable=False),
        sa.Column("to_address", sa.String(length=320), nullable=True),
        sa.Column("subject", sa.String(length=500), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("message_id", sa.String(length=255), nullable=True),
        sa.Column("delivery", sa.String(length=16), nullable=False),
        sa.Column("delivery_error", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("replies", sa.JSON(), nullable=True),
        sa.Column("reply_report_id", sa.String(length=36), nullable=True),
        sa.Column("resolution", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.String(length=320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        _tenant_fk("info_requests"),
        sa.ForeignKeyConstraint(["report_id"], ["reports.id"], name=op.f("fk_info_requests_report_id_reports"),
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_info_requests")),
        sa.UniqueConstraint("tenant_id", "number", name=op.f("uq_info_requests_tenant_id_number")),
    )
    op.create_index(op.f("ix_info_requests_tenant_id"), "info_requests", ["tenant_id"])
    op.create_index(op.f("ix_info_requests_report_id"), "info_requests", ["report_id"])
    op.create_index(op.f("ix_info_requests_reply_report_id"), "info_requests", ["reply_report_id"])
    if op.get_bind().dialect.name == "postgresql":
        for table in ("approved_rules", "info_requests"):
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            op.execute(f"CREATE POLICY tenant_isolation ON {table} USING ({_TENANT}) WITH CHECK ({_TENANT})")


def downgrade() -> None:
    for table in ("info_requests", "approved_rules"):
        if op.get_bind().dialect.name == "postgresql":
            op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.drop_table(table)
