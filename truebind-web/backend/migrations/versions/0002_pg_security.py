"""PostgreSQL security: Row Level Security on every tenant-owned table and an
append-only audit log.

Tenant isolation is enforced by the database, not only by application code:
each request/job sets `app.tenant_id` for its transaction
(app/database.py -> set_tenant) and every policy compares against it.
`FORCE ROW LEVEL SECURITY` makes the policies apply to the table owner too.
A PostgreSQL *superuser* still bypasses RLS by design, so the application
must connect as a non-superuser role (see AI/ARCHITECTURE/TRUEBIND_SECURITY_MODEL.md).

The worker needs to *claim* the next job across tenants; that single query
runs with `app.worker = 'on'`, which only the jobs policy honours. After
claiming, the worker switches to the job's tenant like any request.

No-op on SQLite (local development / unit tests).

Revision ID: 0002_pg_security
Revises: 0001_baseline
"""
from __future__ import annotations

from alembic import op

revision = "0002_pg_security"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

TENANT_TABLES = (
    "reports", "sheets", "excluded_rows", "mappings", "claim_rows", "validation_results", "alerts",
    "obligations", "templates", "exception_summaries", "leakage_flags", "audit_log", "jobs",
)
_MATCH = "tenant_id = current_setting('app.tenant_id', true)"


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for t in TENANT_TABLES:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")
        if t == "jobs":
            using = f"({_MATCH}) OR current_setting('app.worker', true) = 'on'"
        else:
            using = _MATCH
        op.execute(f"CREATE POLICY tenant_isolation ON {t} USING ({using}) WITH CHECK ({using})")
    op.execute("""
        CREATE OR REPLACE FUNCTION truebind_audit_append_only() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only (% rejected)', TG_OP;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER audit_log_append_only BEFORE UPDATE OR DELETE ON audit_log
        FOR EACH ROW EXECUTE FUNCTION truebind_audit_append_only()
    """)


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP TRIGGER IF EXISTS audit_log_append_only ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS truebind_audit_append_only()")
    for t in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {t}")
        op.execute(f"ALTER TABLE {t} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {t} DISABLE ROW LEVEL SECURITY")
