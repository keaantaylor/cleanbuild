"""Phase 5 privacy controls: configurable retention (default 30 days) with real
deletion of the data, and the anonymise-names option."""

from __future__ import annotations

import datetime as dt

from app.database import get_session_factory, set_tenant
from app.models.reports import ClaimRow, Report, ValidationResult
from app.services import retention_service
from app.services.storage import get_store
from conftest import Api, simple_rows, xlsx_bytes


def _session(tid: str):
    s = get_session_factory()()
    set_tenant(s, tid)
    return s


def _tid(api: Api) -> str:
    return api.me["tenant"]["id"]


def test_retention_defaults_to_30_days_and_is_configurable(api: Api):
    assert api.get("/api/v1/org").json()["retention_days"] == 30
    rid = api.ingest("a.xlsx", xlsx_bytes(simple_rows()))
    r = api.get(f"/api/v1/reports/{rid}").json()
    created, expires = (dt.datetime.fromisoformat(r[k].replace("Z", "+00:00")) for k in ("created_at", "expires_at"))
    assert round((expires - created).total_seconds() / 86400) == 30
    assert api.patch("/api/v1/org", json={"retention_days": 7}).json()["retention_days"] == 7
    r = api.get(f"/api/v1/reports/{rid}").json()
    expires = dt.datetime.fromisoformat(r["expires_at"].replace("Z", "+00:00"))
    assert round((expires - created).total_seconds() / 86400) == 7
    assert api.patch("/api/v1/org", json={"retention_days": 0}).status_code == 422
    assert api.patch("/api/v1/org", json={"retention_days": 400}).status_code == 422


def _original_readable(key: str, sha: str) -> int:
    try:
        with get_store().local_copy(key, sha):
            return 1
    except Exception:  # noqa: BLE001 -- missing in whichever backend is configured
        return 0


def _counts(tid: str, rid: str, key: str = "", sha: str = "") -> tuple[int, int, int]:
    s = _session(tid)
    try:
        return (s.query(ClaimRow).filter_by(report_id=rid).count(),
                s.query(ValidationResult).filter_by(report_id=rid).count(),
                _original_readable(key, sha) if key else 0)
    finally:
        s.close()


def test_deleted_report_data_is_purged(api: Api):
    tid = _tid(api)
    rows = simple_rows(5) + [["ARI-1", "Arith Ltd", "2024-01-15", "Open", "GBP", 100, 50, 999]]
    rid, _ = api.full_run("a.xlsx", xlsx_bytes(rows))
    s = _session(tid)
    rep = s.query(Report).filter_by(id=rid).one()
    key, sha = rep.storage_key, rep.source_sha256
    s.close()
    claims, findings, blobs = _counts(tid, rid, key, sha)
    assert claims == 6 and findings >= 1 and blobs >= 1
    assert api.delete(f"/api/v1/reports/{rid}").status_code in (200, 204)
    s = get_session_factory()()
    try:
        assert retention_service.purge_deleted_reports(s) == 1
    finally:
        s.close()
    assert _counts(tid, rid, key, sha) == (0, 0, 0), "rows, findings and the stored original are gone"
    s = _session(tid)
    try:
        rep = s.query(Report).execution_options(include_deleted=True).filter_by(id=rid).one()
        assert rep.purged_at is not None and rep.summary is None and rep.storage_key is None
    finally:
        s.close()
    assert api.get("/api/v1/audit/verify").json()["intact"] is True


def test_expired_report_is_deleted_then_purged_but_shared_original_kept(api: Api):
    tid = _tid(api)
    content = xlsx_bytes(simple_rows(4))
    old, _ = api.full_run("a.xlsx", content)
    keep, _ = api.full_run("a-again.xlsx", content)  # the very same file uploaded again
    s = _session(tid)
    try:
        s.query(Report).filter_by(id=old).one().expires_at = dt.datetime.now(dt.UTC) - dt.timedelta(days=1)
        s.commit()
    finally:
        s.close()
    s = get_session_factory()()
    try:
        assert retention_service.expire_due_reports(s) == 1
        assert retention_service.purge_deleted_reports(s) == 1
    finally:
        s.close()
    assert api.get(f"/api/v1/reports/{old}").status_code == 404
    assert _counts(tid, old)[:2] == (0, 0)
    # The other report still has its original: its annotated workbook still builds.
    assert api.get(f"/api/v1/reports/{keep}/export/annotated.xlsx").status_code == 200


def test_anonymise_names(api: Api):
    assert api.patch("/api/v1/org", json={"anonymise_names": True}).json()["anonymise_names"] is True
    rows = simple_rows(3) + [["CLM-9", "Wexford Distinctive Holdings", "2024-01-15", "Open", "GBP", 100, 50, 999],
                             ["CLM-10", "Wexford Distinctive Holdings", "2024-01-16", "Open", "GBP", 100, 50, 150]]
    rid, _ = api.full_run("names.xlsx", xlsx_bytes(rows))
    claims = api.get(f"/api/v1/reports/{rid}/claims", params={"limit": 50}).json()["items"]
    names = {c["claim_reference"]: c["insured_name"] for c in claims}
    assert names["CLM-9"].startswith("Insured ") and names["CLM-9"] == names["CLM-10"], "same name, same code"
    everything = (api.get(f"/api/v1/reports/{rid}/claims", params={"limit": 50}).text
                  + api.get(f"/api/v1/reports/{rid}/exceptions", params={"limit": 500}).text
                  + api.get(f"/api/v1/reports/{rid}/duplicates").text
                  + api.get(f"/api/v1/reports/{rid}/summary").text
                  + api.get(f"/api/v1/reports/{rid}/export/claims.csv").text)
    sheet = api.get(f"/api/v1/reports/{rid}/sheets").json()[0]
    everything += api.get(f"/api/v1/reports/{rid}/sheets/{sheet['id']}/mapping").text
    assert "Wexford" not in everything
