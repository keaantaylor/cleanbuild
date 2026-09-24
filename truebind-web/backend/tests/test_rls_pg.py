"""Row Level Security, enforced by PostgreSQL itself: even a query with NO
tenant filter only sees the current tenant's rows, and a write for another
tenant is refused. Requires TRUEBIND_TEST_DATABASE_URL with a NON-superuser
role (superusers bypass RLS by design)."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from conftest import IS_PG, simple_rows, xlsx_bytes

pytestmark = [pytest.mark.pg, pytest.mark.skipif(not IS_PG, reason="PostgreSQL only")]


def test_connection_role_cannot_bypass_rls(db):
    row = db.execute(text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")).one()
    assert row == (False, False)


def test_unfiltered_queries_only_see_current_tenant(api, api_b, db):
    from app.database import set_tenant
    api.full_run("a.xlsx", xlsx_bytes(simple_rows(5)))
    api_b.full_run("b.xlsx", xlsx_bytes(simple_rows(3)))
    ta, tb = api.me["tenant"]["id"], api_b.me["tenant"]["id"]
    set_tenant(db, ta)
    assert db.execute(text("SELECT count(*) FROM claim_rows")).scalar() == 5
    set_tenant(db, tb)
    assert db.execute(text("SELECT count(*) FROM claim_rows")).scalar() == 3
    set_tenant(db, None)
    for table in ("reports", "claim_rows", "audit_log", "sheets", "validation_results"):
        assert db.execute(text(f"SELECT count(*) FROM {table}")).scalar() == 0, table
    db.rollback()


def test_cannot_write_rows_for_another_tenant(api, api_b, db):
    from app.database import set_tenant
    rid, _ = api.full_run("a.xlsx", xlsx_bytes(simple_rows(2)))
    set_tenant(db, api_b.me["tenant"]["id"])
    with pytest.raises(Exception, match="row-level security"):
        db.execute(text("INSERT INTO alerts (id, tenant_id, report_id, severity, source, message, acknowledged, "
                        "created_at) VALUES ('x', :t, :r, 'INFO', 'COVERAGE', 'm', false, now())"),
                   {"t": api.me["tenant"]["id"], "r": rid})
    db.rollback()
    set_tenant(db, api_b.me["tenant"]["id"])
    n = db.execute(text("UPDATE reports SET file_name = 'pwned' WHERE id = :r"), {"r": rid}).rowcount
    assert n == 0
    db.rollback()
