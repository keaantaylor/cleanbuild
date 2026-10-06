"""Execution policy on corrections, the RECHECK job, the trail, and in-flight duplicate uploads."""

from __future__ import annotations

import pytest
from conftest import Api, run_jobs
from test_deliverables import _book, _rows, _run

from app.services import policy, reconciliation_service
from app.services.policy import classify


def _c(**kw):
    base = dict(field_code=None, source="manual", rule=None, before="a", after="b", header_row=False)
    return classify(**{**base, **kw}).policy


def test_policy_classification_is_deterministic():
    assert _c(after="=SUM(A1:A3)") == policy.BLOCKED
    assert _c(header_row=True) == policy.BLOCKED
    assert _c(field_code="CR0104M", before="CLM-1", after="CLM-2") == policy.BLOCKED
    assert _c(field_code="CR0104M", before=" CLM-1 ", after="CLM-1") == policy.REVIEW_REQUIRED  # spaces only
    assert _c(source="auto", rule="amount_stored_as_text", before="1,500", after="1500") == policy.AUTO
    assert _c(source="auto", rule="date_stored_as_text", before="15/01/2024", after="2024-01-15") == policy.AUTO
    assert _c(source="auto", rule="currency_normalised", before="Euro", after="EUR") == policy.AUTO_WITH_POLICY
    assert _c(field_code="CR0155CM", before="999", after="1500") == policy.APPROVAL_REQUIRED
    assert _c(field_code="CR0155CM", before="1,500", after="1500") == policy.REVIEW_REQUIRED  # same value
    assert _c(field_code="CR0035M", before="Acme", after="Acme Ltd") == policy.REVIEW_REQUIRED
    assert _c(field_code="CR0155CM", before="1", after="-1500") == policy.APPROVAL_REQUIRED  # negative number is not a formula


def _sheet(api: Api, rid: str) -> dict:
    return next(s for s in api.get(f"/api/v1/reports/{rid}/sheets").json() if s["sheet_name"] == "Claims")


def test_blocked_change_is_refused_and_material_change_records_its_approval(api: Api):
    rid = _run(api, _book(_rows()))
    sid = _sheet(api, rid)["id"]
    r = api.post(f"/api/v1/reports/{rid}/corrections", json={"sheet_id": sid, "cell": "A3", "after_value": "CLM-9999",
                                                             "reason": "rename"})
    assert r.status_code == 422 and r.json()["detail"].startswith("Blocked")
    c = api.post(f"/api/v1/reports/{rid}/corrections", json={"sheet_id": sid, "cell": "I15", "after_value": "1500",
                                                             "reason": "sender confirmed"}).json()
    assert c["policy"] == policy.APPROVAL_REQUIRED and c["field_code"] == "CR0155CM"
    d = api.post(f"/api/v1/reports/{rid}/corrections/{c['id']}/decision", json={"approve": True}).json()
    # The only member who can write may approve their own change; that is recorded.
    assert d["approval"]["by"] == "person" and d["approval"]["sole_approver"] is True
    assert d["result"]["passed"] is True  # the re-check verified it


def test_safe_fixes_auto_apply_and_rewrites_apply_only_on_precedent(api: Api):
    rid = _run(api, _book(_rows()))
    out = api.post(f"/api/v1/reports/{rid}/corrections/auto").json()
    items = api.get(f"/api/v1/reports/{rid}/corrections").json()["items"]
    auto = [c for c in items if c["policy"] == policy.AUTO]
    assert auto and all(c["status"] == "APPROVED" and c["approval"]["by"] == "policy" for c in auto)
    assert out["auto_applied"] == len(auto) and out["recheck"]["status"] == "ran"
    euro = next(c for c in items if c["cell"] == "F16")
    assert euro["policy"] == policy.AUTO_WITH_POLICY and euro["status"] == "PROPOSED"
    api.post(f"/api/v1/reports/{rid}/corrections/{euro['id']}/decision", json={"approve": True})
    # Next file: the same rewrite was approved by a person, so it now applies by itself.
    rid2 = _run(api, _book(_rows()), name="book2.xlsx")
    api.post(f"/api/v1/reports/{rid2}/corrections/auto")
    euro2 = next(c for c in api.get(f"/api/v1/reports/{rid2}/corrections").json()["items"] if c["cell"] == "F16")
    assert euro2["status"] == "APPROVED" and euro2["approval"]["by"] == "policy"


def test_large_workbook_recheck_runs_as_a_job_not_in_the_request(api: Api, monkeypatch: pytest.MonkeyPatch):
    rid = _run(api, _book(_rows()))
    monkeypatch.setattr(reconciliation_service, "RECHECK_INLINE_MAX_ROWS", 0)
    arith = next(i for i in api.get(f"/api/v1/reports/{rid}/issues").json()["items"] if i["rule"] == "arithmetic_mismatch")
    c = api.post(f"/api/v1/reports/{rid}/corrections", json={"sheet_id": _sheet(api, rid)["id"], "cell": "I15",
                                                             "after_value": "1400", "reason": "typo",
                                                             "issue_id": arith["id"]}).json()
    d = api.post(f"/api/v1/reports/{rid}/corrections/{c['id']}/decision", json={"approve": True}).json()
    assert d["recheck"]["status"] == "queued" and d["recheck"]["job_id"]
    assert api.get(f"/api/v1/reports/{rid}").json()["status"] == "COMPLETE"  # the report is not re-queued
    run_jobs()
    assert api.get(f"/api/v1/reports/{rid}/issues/{arith['id']}").json()["status"] == "DETECTED"
    assert api.get(f"/api/v1/reports/{rid}").json()["status"] == "COMPLETE"


def test_trail_reconstructs_the_bordereau(api: Api):
    rid = _run(api, _book(_rows()))
    api.post(f"/api/v1/reports/{rid}/corrections/auto")
    t = api.get(f"/api/v1/reports/{rid}/trail").json()
    assert t["arrival"]["sha256"] and t["analysis"]["analysed_version_sha256"]
    assert {v["kind"] for v in t["versions"]} >= {"original", "analysed"}
    assert t["corrections"] and all(c["policy"] for c in t["corrections"])
    assert t["final_verification"]["audit_chain_intact"] is True
    assert t["final_verification"]["source_unchanged"] is True
    assert [p["kind"] for p in t["processing"]] == ["INGEST", "PROCESS"]
    # Fingerprinted once: a second build returns the same analysed hash.
    assert api.get(f"/api/v1/reports/{rid}/trail").json()["analysis"]["analysed_version_sha256"] == \
        t["analysis"]["analysed_version_sha256"]


def test_same_file_uploaded_twice_while_in_flight_is_processed_once(api: Api):
    body = _book(_rows())
    first = api.upload("a.xlsx", body)
    second = api.upload("a.xlsx", body)
    assert first.status_code == 202 and second.status_code == 200
    assert second.headers["X-Duplicate-Of"] == first.json()["id"] == second.json()["id"]
