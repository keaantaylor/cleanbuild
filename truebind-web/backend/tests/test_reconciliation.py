"""Reconciliation through the API: totals vs detail, the previous submission
from the same sender, and the re-check that runs after corrections."""

from __future__ import annotations

from conftest import Api, run_jobs
from test_deliverables import _book, _clean, _rows, _run


def _items(api: Api, rid: str) -> list[dict]:
    r = api.get(f"/api/v1/reports/{rid}/issues", params={"limit": 1000})
    assert r.status_code == 200, r.text
    return r.json()["items"]


def _run_from(api: Api, content: bytes, sender: str, name: str) -> str:
    r = api.post("/api/v1/reports/upload", files={"file": (name, content, "application/octet-stream")},
                 data={"sender": sender})
    assert r.status_code == 202, r.text
    rid = r.json()["id"]
    run_jobs()
    api.confirm_all(rid)
    assert api.post(f"/api/v1/reports/{rid}/process").status_code == 202
    run_jobs()
    assert api.get(f"/api/v1/reports/{rid}").json()["status"] == "COMPLETE"
    return rid


def test_total_line_is_reconciled_against_its_rows(api: Api):
    rows = [_clean(i) for i in range(3)] + [["Total", None, None, None, None, None, 3000, 1500, 4600]]
    rid = _run(api, _book(rows))
    hit = [i for i in _items(api, rid) if i["rule"] == "totals_mismatch"]
    assert len(hit) == 1
    t = hit[0]
    # Header on row 2, claims on rows 3-5, the total line on row 6, Total Incurred in column I.
    assert t["cell"] == "I6" and t["expected"] == 4500.0 and t["actual"] == 4600.0 and t["difference"] == 100.0
    assert t["rule_version"] == "1.0" and t["ruleset_version"] == "2026.10.2"


def test_previous_submission_from_the_same_sender_is_matched_claim_by_claim(api: Api):
    feb = [_clean(i, paid=1000, res=500, inc=1500) for i in range(3)]
    _run_from(api, _book(feb), "Coastline", "feb.xlsx")
    mar = [_clean(0, paid=800, res=700, inc=1500)] + [_clean(i, paid=1000, res=500, inc=1500) for i in (1, 2)]
    rid = _run_from(api, _book(mar), "Coastline", "mar.xlsx")
    dec = [i for i in _items(api, rid) if i["rule"] == "paid_decreased"]
    assert len(dec) == 1 and dec[0]["claim_reference"] == "CLM-0000"
    assert dec[0]["expected"] == 1000.0 and dec[0]["actual"] == 800.0 and dec[0]["cell"] == "G3"
    assert "feb.xlsx" in dec[0]["evidence"]
    # Another sender's file is never used as the previous submission.
    other = _run_from(api, _book(mar), "Meridian", "mar-other.xlsx")
    assert not [i for i in _items(api, other) if i["rule"] == "paid_decreased"]


def test_correction_is_rechecked_and_reopened_when_the_rule_still_fails(api: Api):
    rid = _run(api, _book(_rows()))
    sheet = next(s for s in api.get(f"/api/v1/reports/{rid}/sheets").json() if s["sheet_name"] == "Claims")
    arith = next(i for i in _items(api, rid) if i["rule"] == "arithmetic_mismatch")
    # A wrong "fix": 1400 still does not equal paid + reserve (1500).
    c = api.post(f"/api/v1/reports/{rid}/corrections", json={"sheet_id": sheet["id"], "cell": "I15",
                                                             "after_value": "1400", "reason": "typo",
                                                             "issue_id": arith["id"]}).json()
    d = api.post(f"/api/v1/reports/{rid}/corrections/{c['id']}/decision", json={"approve": True}).json()
    # Approval re-runs the checks at once, on an in-memory corrected copy.
    assert d["recheck"]["status"] == "ran" and d["recheck"]["still_failing"] == 1 and d["recheck"]["passed"] == 0
    issue = api.get(f"/api/v1/reports/{rid}/issues/{arith['id']}").json()
    assert issue["status"] == "DETECTED" and "still fails at Claims!I15" in issue["history"][-1]["note"]
    assert issue["history"][-2]["status"] == "RESOLVED"  # the approval, then the re-check reopening it
    # Building the version re-checks again and records the version it checked.
    v = api.post(f"/api/v1/reports/{rid}/versions").json()
    assert v["recheck"]["still_failing"] == 1


def test_correction_that_fixes_the_value_is_verified(api: Api):
    rid = _run(api, _book(_rows()))
    sheet = next(s for s in api.get(f"/api/v1/reports/{rid}/sheets").json() if s["sheet_name"] == "Claims")
    arith = next(i for i in _items(api, rid) if i["rule"] == "arithmetic_mismatch")
    c = api.post(f"/api/v1/reports/{rid}/corrections", json={"sheet_id": sheet["id"], "cell": "I15",
                                                             "after_value": "1500", "reason": "confirmed",
                                                             "issue_id": arith["id"]}).json()
    d = api.post(f"/api/v1/reports/{rid}/corrections/{c['id']}/decision", json={"approve": True}).json()
    assert d["recheck"]["passed"] == 1
    v = api.post(f"/api/v1/reports/{rid}/versions").json()
    assert v["recheck"]["passed"] == 1 and v["recheck"]["still_failing"] == 0
    assert api.get(f"/api/v1/reports/{rid}/issues/{arith['id']}").json()["status"] == "RESOLVED"
