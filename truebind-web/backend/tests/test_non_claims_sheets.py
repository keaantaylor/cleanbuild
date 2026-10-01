"""Non-claims tabs (Summary, Lookups, Log...) are pre-selected as skipped with
a reason, never silently; the reviewer can include them anyway, or skip a sheet
TrueBind proposed. Skipped sheets never reach the findings or the score."""

from __future__ import annotations

from conftest import run_jobs, simple_rows, xlsx_bytes

SUMMARY = [["Status", "Count", "Total paid"], ["Open", 2, 2000], ["Closed", 1, 1000]]


def _book() -> bytes:
    return xlsx_bytes(simple_rows(5), extra_sheets={"Summary": SUMMARY})


def _sheets(api, rid):
    return {s["sheet_name"]: s for s in api.get(f"/api/v1/reports/{rid}/sheets").json()}


def test_summary_tab_is_preselected_as_skipped_with_reason(api):
    rid = api.ingest("book.xlsx", _book())
    sheets = _sheets(api, rid)
    assert sheets["Claims"]["status"] == "PENDING_CONFIRMATION"
    summ = sheets["Summary"]
    assert summ["status"] == "SKIPPED" and summ["mapping_status"] == "non_claim_summary"
    assert summ["skip_reason"].startswith("Looks like a non-claims tab") and "include it anyway" in summ["skip_reason"]
    assert summ["row_count"] == 2  # the data is kept, so it can be included later


def test_include_anyway_then_skip_again_is_audited(api):
    rid = api.ingest("book.xlsx", _book())
    sid = _sheets(api, rid)["Summary"]["id"]
    r = api.post(f"/api/v1/reports/{rid}/sheets/{sid}/include")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "PENDING_CONFIRMATION" and r.json()["skip_reason"] is None
    m = api.get(f"/api/v1/reports/{rid}/sheets/{sid}/mapping").json()
    assert "Total paid" in m["headers"]
    r = api.post(f"/api/v1/reports/{rid}/sheets/{sid}/skip")
    assert r.status_code == 200 and r.json()["status"] == "SKIPPED"
    actions = [e["action_type"] for e in api.get(f"/api/v1/reports/{rid}/audit").json()["items"]]
    assert "SHEET_INCLUDED" in actions and "SHEET_SKIPPED" in actions


def test_empty_sheet_cannot_be_included(api):
    rid = api.ingest("book.xlsx", xlsx_bytes(simple_rows(3), extra_sheets={"Blank": []}))
    blank = _sheets(api, rid).get("Blank")
    if blank is None:  # the reader may drop a wholly empty tab
        return
    r = api.post(f"/api/v1/reports/{rid}/sheets/{blank['id']}/include")
    assert r.status_code == 409


def test_skipped_sheets_never_reach_findings(api):
    rid, report = api.full_run("book.xlsx", _book())
    assert report["rows_processed"] == 5
    exc = api.get(f"/api/v1/reports/{rid}/exceptions", params={"limit": 1000}).json()
    assert all(e.get("sheet_name") != "Summary" for e in exc["items"])


def test_reviewer_can_skip_a_proposed_sheet(api):
    rid = api.ingest("book.xlsx", xlsx_bytes(simple_rows(3), extra_sheets={"Claims Q2": simple_rows(4)}))
    sheets = _sheets(api, rid)
    assert sheets["Claims Q2"]["status"] == "PENDING_CONFIRMATION"
    assert api.post(f"/api/v1/reports/{rid}/sheets/{sheets['Claims Q2']['id']}/skip").status_code == 200
    api.confirm_all(rid)
    assert api.post(f"/api/v1/reports/{rid}/process").status_code == 202
    run_jobs()
    assert api.get(f"/api/v1/reports/{rid}").json()["rows_processed"] == 3


def test_process_refused_when_every_sheet_is_skipped(api):
    rid = api.ingest("book.xlsx", xlsx_bytes(simple_rows(3)))
    sid = next(iter(_sheets(api, rid).values()))["id"]
    api.post(f"/api/v1/reports/{rid}/sheets/{sid}/skip")
    r = api.post(f"/api/v1/reports/{rid}/process")
    assert r.status_code == 409 and "Include at least one" in r.json()["detail"]
