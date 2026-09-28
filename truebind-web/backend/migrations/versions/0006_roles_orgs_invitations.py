"""roles (REVIEWER -> ANALYST, + SENDER), organisation type + 2FA flag, invitations

Invitations are readable on PostgreSQL either inside their own tenant or by
presenting the token hash for the current transaction
(``app.invite_token_hash``) -- the accept endpoint runs before any tenant
is known, and must not be able to see any other invitation.

Revision ID: 0006_roles_orgs_invitations
Revises: 0005_inbound_outbound
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_roles_orgs_invitations"
down_revision = "0005_inbound_outbound"
branch_labels = None
depends_on = None

_TENANT = "tenant_id = current_setting('app.tenant_id', true)"
_BY_INVITE_HASH = "token_hash = current_setting('app.invite_token_hash', true)"


def upgrade() -> None:
    with op.batch_alter_table("tenants") as b:
        b.add_column(sa.Column("org_type", sa.String(length=32), nullable=False, server_default="capacity_provider"))
        b.add_column(sa.Column("require_2fa", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute("UPDATE memberships SET role = 'ANALYST' WHERE role = 'REVIEWER'")
    op.create_table(
        "invitations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("invited_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_invitations_tenant_id_tenants"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["invited_by_user_id"],
            ["users.id"],
            name=op.f("fk_invitations_invited_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invitations")),
    )
    op.create_index(op.f("ix_invitations_tenant_id"), "invitations", ["tenant_id"])
    op.create_index(op.f("ix_invitations_token_hash"), "invitations", ["token_hash"], unique=True)
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE invitations ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE invitations FORCE ROW LEVEL SECURITY")
        using = f"({_TENANT}) OR ({_BY_INVITE_HASH})"
        op.execute(f"CREATE POLICY tenant_isolation ON invitations USING ({using}) WITH CHECK ({_TENANT})")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS tenant_isolation ON invitations")
    op.drop_index(op.f("ix_invitations_token_hash"), table_name="invitations")
    op.drop_index(op.f("ix_invitations_tenant_id"), table_name="invitations")
    op.drop_table("invitations")
    op.execute("DELETE FROM memberships WHERE role = 'SENDER'")
    op.execute("UPDATE memberships SET role = 'REVIEWER' WHERE role = 'ANALYST'")
    with op.batch_alter_table("tenants") as b:
        b.drop_column("require_2fa")
        b.drop_column("org_type")
