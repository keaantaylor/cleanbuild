"""P5 sanctions screening: sanctions lists and their entries.

Revision ID: 0015_sanctions
Revises: 0014_modules_binders
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015_sanctions"
down_revision = "0014_modules_binders"
branch_labels = None
depends_on = None

_TENANT = "tenant_id = current_setting('app.tenant_id', true)"
_TABLES = ("sanctions_lists", "sanctions_entries")


def _fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["tenant_id"], ["tenants.id"], name=op.f(f"fk_{table}_tenant_id_tenants"), ondelete="CASCADE"
    )


def upgrade() -> None:
    op.create_table(
        "sanctions_lists",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("entry_count", sa.Integer(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("uploaded_by", sa.String(length=255), nullable=False),
        _fk("sanctions_lists"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sanctions_lists")),
    )
    op.create_index(op.f("ix_sanctions_lists_tenant_id"), "sanctions_lists", ["tenant_id"])
    op.create_table(
        "sanctions_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("list_id", sa.String(length=36), nullable=False),
        sa.Column("reference", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        _fk("sanctions_entries"),
        sa.ForeignKeyConstraint(
            ["list_id"],
            ["sanctions_lists.id"],
            name=op.f("fk_sanctions_entries_list_id_sanctions_lists"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sanctions_entries")),
    )
    for col in ("tenant_id", "list_id"):
        op.create_index(op.f(f"ix_sanctions_entries_{col}"), "sanctions_entries", [col])
    if op.get_bind().dialect.name == "postgresql":
        for table in _TABLES:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            op.execute(f"CREATE POLICY tenant_isolation ON {table} USING ({_TENANT}) WITH CHECK ({_TENANT})")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table in _TABLES:
            op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
    for col in ("tenant_id", "list_id"):
        op.drop_index(op.f(f"ix_sanctions_entries_{col}"), table_name="sanctions_entries")
    op.drop_table("sanctions_entries")
    op.drop_index(op.f("ix_sanctions_lists_tenant_id"), table_name="sanctions_lists")
    op.drop_table("sanctions_lists")
