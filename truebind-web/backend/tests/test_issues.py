"""Issues as records, corrections kept apart from the source, fingerprinted versions."""

from __future__ import annotations

import hashlib
import io

import openpyxl
from conftest import Api
from test_deliverables import _book, _rows, _run


def _issues(api: Api, rid: str, **params) -> dict:
    r = api.get(f"/api/v1/reports/{rid}/issues", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_issue_records_carry_rule_version_values_status_and_history(api: Api):
    rid = _run(api, _book(_rows()))
    items = _issues(api, rid)["items"]
    arith = next(i for i in items if i["rule"] == "arithmetic_mismatch")
    assert arith["cell"] == "I15" and arith["rule_version"] == "1.1" and arith["ruleset_version"]
    assert arith["actual"] == 999.0 and arith["expected"] == 1500.0 and arith["difference"] == -501.0
    assert arith["status"] == "DETECTED" and len(arith["history"]) == 1 and arith["history"][0]["actor"] == "system"
    euro = next(i for i in items if i["rule"] == "currency_normalised")
    assert euro["status"] == "AUTO_FIX_PROPOSED"
    detail = api.get(f"/api/v1/reports/{rid}/issues/{euro['id']}").json()
    lin = detail["lineage"]
    assert lin["original_value"] == "Euro" and lin["normalised_value"] == "EUR" and lin["mapped_field"]["code"] == "CR0110CM"
    assert lin["file_sha256"] and lin["transformation"] != "none"
    causes = _issues(api, rid)["root_causes"]
    assert any(c["root_cause"] == "arithmetic_mismatch:Total Incurred" for c in causes)


def test_status_lifecycle_is_enforced_and_recorded(api: Api):
    rid = _run(api, _book(_rows()))
    arith = next(i for i in _issues(api, rid)["items"] if i["rule"] == "arithmetic_mismatch")
    url = f"/api/v1/reports/{rid}/issues/{arith['id']}/status"
    assert api.post(url, json={"status": "OVERRIDDEN"}).status_code == 409  # a reason is required
    r = api.post(url, json={"status": "OVERRIDDEN", "note": "Sender confirmed the total includes fees."})
    assert r.status_code == 200 and r.json()["status"] == "OVERRIDDEN" and len(r.json()["history"]) == 2
    assert api.post(url, json={"status": "AUTO_FIXED"}).status_code == 409  # not a permitted move
    actions = [e["action_type"] for e in api.get(f"/api/v1/reports/{rid}/audit").json()["items"]]
    assert "ISSUE_STATUS_CHANGED" in actions


def test_corrections_never_touch_the_source_and_versions_are_deterministic(api: Api):
    original = _book(_rows())
    rid = _run(api, original)
    sheet = next(s for s in api.get(f"/api/v1/reports/{rid}/sheets").json() if s["sheet_name"] == "Claims")
    arith = next(i for i in _issues(api, rid)["items"] if i["rule"] == "arithmetic_mismatch")
    r = api.post(f"/api/v1/reports/{rid}/corrections", json={"sheet_id": sheet["id"], "cell": "i15", "after_value": "1500",
                                                             "reason": "Sender confirmed 1,500", "issue_id": arith["id"]})
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["before"] == "999" and c["cell"] == "I15" and c["status"] == "PROPOSED"  # before read from the source
    assert api.post(f"/api/v1/reports/{rid}/versions").status_code == 409  # nothing approved yet
    d = api.post(f"/api/v1/reports/{rid}/corrections/{c['id']}/decision", json={"approve": True}).json()
    assert d["status"] == "APPROVED" and d["decided_by"]
    issue = api.get(f"/api/v1/reports/{rid}/issues/{arith['id']}").json()
    assert issue["status"] == "RESOLVED" and issue["corrections"][0]["id"] == c["id"]

    v1 = api.post(f"/api/v1/reports/{rid}/versions").json()
    v1_again = api.post(f"/api/v1/reports/{rid}/versions").json()
    assert v1["kind"] == "corrected" and v1_again["id"] == v1["id"], "same input, same version"
    body = api.get(f"/api/v1/reports/{rid}/versions/{v1['id']}/download").content
    assert hashlib.sha256(body).hexdigest() == v1["sha256"]
    assert openpyxl.load_workbook(io.BytesIO(body))["Claims"]["I15"].value == 1500
    versions = api.get(f"/api/v1/reports/{rid}/versions").json()["items"]
    orig = next(v for v in versions if v["kind"] == "original")
    assert api.get(f"/api/v1/reports/{rid}/versions/{orig['id']}/download").content == original  # untouched
    approved = api.post(f"/api/v1/reports/{rid}/versions/{v1['id']}/approve", json={"note": "Ready"}).json()
    assert approved["kind"] == "approved" and approved["sha256"] == v1["sha256"] and approved["based_on"] == v1["id"]


def test_automatic_corrections_are_proposed_once_and_mark_issues_fixed(api: Api):
    rid = _run(api, _book(_rows()))
    n = api.post(f"/api/v1/reports/{rid}/corrections/auto").json()["proposed"]
    assert n >= 3
    assert api.post(f"/api/v1/reports/{rid}/corrections/auto").json()["proposed"] == 0  # idempotent
    euro = next(c for c in api.get(f"/api/v1/reports/{rid}/corrections").json()["items"] if c["cell"] == "F16")
    assert euro["before"] == "Euro" and euro["after"] == "EUR" and euro["source"] == "auto"
    api.post(f"/api/v1/reports/{rid}/corrections/{euro['id']}/decision", json={"approve": True})
    issue = next(i for i in _issues(api, rid)["items"] if i["cell"] == "F16")
    assert issue["status"] == "AUTO_FIXED"
