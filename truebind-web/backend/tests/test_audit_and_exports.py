"""Audit chain integrity and export safety."""

from __future__ import annotations

import csv
import io

import pytest
from sqlalchemy import text

from app.models.audit import AuditLogEntry
from conftest import IS_PG, SIMPLE_HEADER, simple_rows, xlsx_bytes


def test_workflow_produces_an_intact_hash_chain(api):
    api.full_run("a.xlsx", xlsx_bytes(simple_rows()))
    v = api.get("/api/v1/audit/verify").json()
    assert v["intact"] is True and v["first_bad_seq"] is None and v["entries"] > 10
    seqs = [e["seq"] for e in api.get("/api/v1/audit", params={"limit": 1000}).json()["items"]]
    assert sorted(seqs) == list(range(1, len(seqs) + 1)), "gapless per-tenant sequence"


@pytest.mark.skipif(IS_PG, reason="on PostgreSQL the trigger blocks the edit itself (see test below)")
def test_tampering_with_an_entry_is_detected(api, db):
    api.full_run("a.xlsx", xlsx_bytes(simple_rows()))
    victim = db.query(AuditLogEntry).filter_by(action_type="MAPPING_CONFIRMED").first()
    db.execute(text("UPDATE audit_log SET actor = 'someone-else' WHERE id = :id"), {"id": victim.id})
    db.commit()
    v = api.get("/api/v1/audit/verify").json()
    assert v["intact"] is False and v["first_bad_seq"] == victim.seq


@pytest.mark.skipif(not IS_PG, reason="append-only trigger exists on PostgreSQL only")
def test_audit_log_is_append_only_in_the_database(api, db):
    from app.database import set_tenant
    api.full_run("a.xlsx", xlsx_bytes(simple_rows()))
    set_tenant(db, api.me["tenant"]["id"])
    with pytest.raises(Exception, match="append-only"):
        db.execute(text("UPDATE audit_log SET actor = 'x'"))
    db.rollback()
    set_tenant(db, api.me["tenant"]["id"])
    with pytest.raises(Exception, match="append-only"):
        db.execute(text("DELETE FROM audit_log"))
    db.rollback()


def _csv(resp) -> list[list[str]]:
    assert resp.status_code == 200, resp.text
    return list(csv.reader(io.StringIO(resp.text)))


def test_exports_neutralise_formula_injection_and_keep_lineage(api):
    # CSV input: openpyxl would store "=..." strings as formulas (no value).
    body = io.StringIO()
    csv.writer(body).writerows([SIMPLE_HEADER,
                                ["=HYPERLINK(\"http://evil\",\"x\")", "@SUM(A1)", "2024-01-15", "+cmd", "GBP",
                                 -50, 0, -50],
                                ["CLM-2", "-negative name", "2024-01-15", "Open", "GBP", 10, 5, 15]])
    rid, _ = api.full_run("inj.csv", body.getvalue().encode())
    table = _csv(api.get(f"/api/v1/reports/{rid}/export/claims.csv"))
    header, body = table[0], table[1:]
    assert header[:2] == ["sheet_name", "source_row_number"] and "findings" in header
    cells = [c for r in body for c in r]
    assert not any(c.startswith(("=", "+", "@")) for c in cells), cells
    assert "'=HYPERLINK(\"http://evil\",\"x\")" in cells and "'@SUM(A1)" in cells and "'-negative name" in cells
    assert "-50.0" in cells, "numbers stay numeric (a negative amount is not escaped)"
    assert {r[1] for r in body} == {"2", "3"}, "source row numbers point at the original sheet rows"


def test_exception_and_audit_exports_are_audited(api):
    rid, _ = api.full_run("a.xlsx", xlsx_bytes(simple_rows()))
    _csv(api.get(f"/api/v1/reports/{rid}/export/exceptions.csv"))
    audit = _csv(api.get(f"/api/v1/reports/{rid}/export/audit.csv"))
    assert audit[0][0] == "seq" and "entry_hash" in audit[0]
    exports = api.get(f"/api/v1/reports/{rid}/audit", params={"action_type": "EXPORT_GENERATED"}).json()
    assert exports["total"] == 2
