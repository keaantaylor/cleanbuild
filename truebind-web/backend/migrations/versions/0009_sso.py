"""OIDC single sign-on: one connection per organisation, globally unique domains.

Revision ID: 0009_sso
Revises: 0008_mfa
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009_sso"
down_revision = "0008_mfa"
branch_labels = None
depends_on = None

_TENANT = "tenant_id = current_setting('app.tenant_id', true)"
_POLICIES = {
    "sso_connections": "id = current_setting('app.sso_connection_id', true)",
    "sso_domains": "domain = current_setting('app.sso_domain', true)",
}


def upgrade() -> None:
    op.create_table(
        "sso_connections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("issuer", sa.String(length=500), nullable=False),
        sa.Column("client_id", sa.String(length=300), nullable=False),
        sa.Column("client_secret_enc", sa.String(length=1000), nullable=True),
        sa.Column("token_auth_method", sa.String(length=32), nullable=False),
        sa.Column("jit_provisioning", sa.Boolean(), nullable=False),
        sa.Column("default_role", sa.String(length=16), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_sso_connections_tenant_id_tenants"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sso_connections")),
    )
    op.create_index(op.f("ix_sso_connections_tenant_id"), "sso_connections", ["tenant_id"], unique=True)
    op.create_table(
        "sso_domains",
        sa.Column("domain", sa.String(length=253), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("connection_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_sso_domains_tenant_id_tenants"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["sso_connections.id"],
            name=op.f("fk_sso_domains_connection_id_sso_connections"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("domain", name=op.f("pk_sso_domains")),
    )
    op.create_index(op.f("ix_sso_domains_tenant_id"), "sso_domains", ["tenant_id"])
    op.create_index(op.f("ix_sso_domains_connection_id"), "sso_domains", ["connection_id"])
    if op.get_bind().dialect.name == "postgresql":
        for table, lookup in _POLICIES.items():
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            using = f"({_TENANT}) OR ({lookup})"
            op.execute(f"CREATE POLICY tenant_isolation ON {table} USING ({using}) WITH CHECK ({_TENANT})")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table in _POLICIES:
            op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
    op.drop_index(op.f("ix_sso_domains_connection_id"), table_name="sso_domains")
    op.drop_index(op.f("ix_sso_domains_tenant_id"), table_name="sso_domains")
    op.drop_table("sso_domains")
    op.drop_index(op.f("ix_sso_connections_tenant_id"), table_name="sso_connections")
    op.drop_table("sso_connections")
