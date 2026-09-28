"""TOTP second factor (user_mfa), how each session was authenticated, and
users may see all of their own sessions (to revoke them on 2FA changes).

Revision ID: 0008_mfa
Revises: 0007_identity_rls
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_mfa"
down_revision = "0007_identity_rls"
branch_labels = None
depends_on = None

_TENANT = "tenant_id = current_setting('app.tenant_id', true)"
_BY_HASH = "token_hash = current_setting('app.session_token_hash', true)"
_BY_USER = "user_id = current_setting('app.user_id', true)"


def _session_policy(using: str) -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON auth_sessions")
    op.execute(f"CREATE POLICY tenant_isolation ON auth_sessions USING ({using}) WITH CHECK ({_TENANT})")


def upgrade() -> None:
    op.create_table(
        "user_mfa",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("secret_enc", sa.String(length=500), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recovery_code_hashes", sa.JSON(), nullable=False),
        sa.Column("last_used_step", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_user_mfa_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_mfa")),
    )
    with op.batch_alter_table("auth_sessions") as b:
        b.add_column(sa.Column("auth_method", sa.String(length=24), nullable=False, server_default="password"))
    if op.get_bind().dialect.name == "postgresql":
        _session_policy(f"({_TENANT}) OR ({_BY_HASH}) OR ({_BY_USER})")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        _session_policy(f"({_TENANT}) OR ({_BY_HASH})")
    with op.batch_alter_table("auth_sessions") as b:
        b.drop_column("auth_method")
    op.drop_table("user_mfa")
