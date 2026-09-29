"""Row-Level Security on the identity tables that carry tenant_id.

memberships and auth_sessions are read before a tenant is known (sign-in,
session lookup), so their policies admit exactly the caller's own rows in
that phase and nothing else:
- memberships:   own tenant, OR user_id = app.user_id (set after the
                 password/session is proven);
- auth_sessions: own tenant, OR token_hash = app.session_token_hash (the
                 hash of the cookie presented).
Writes must always be inside the tenant. No-op on SQLite.

Revision ID: 0007_identity_rls
Revises: 0006_roles_orgs_invitations
"""

from __future__ import annotations

from alembic import op

revision = "0007_identity_rls"
down_revision = "0006_roles_orgs_invitations"
branch_labels = None
depends_on = None

_TENANT = "tenant_id = current_setting('app.tenant_id', true)"
_POLICIES = {
    "memberships": "user_id = current_setting('app.user_id', true)",
    "auth_sessions": "token_hash = current_setting('app.session_token_hash', true)",
}


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table, identity in _POLICIES.items():
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        using = f"({_TENANT}) OR ({identity})"
        op.execute(f"CREATE POLICY tenant_isolation ON {table} USING ({using}) WITH CHECK ({_TENANT})")


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in _POLICIES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
