"""End-to-end through the API and the real job system:
upload -> INGEST job -> review mapping -> PROCESS job -> results.
Numbers are checked against an independent direct call into the engine
on the same file (parity), and against the engine's own fixtures."""

from __future__ import annotations

import sys

import pytest

from bordereaux import pipeline as bpipeline
from conftest import BORDEREAUX_ROOT, run_jobs, simple_rows, xlsx_bytes

BOUNDARY = BORDEREAUX_ROOT / "data" / "synthetic" / "test_boundary_cases.xlsx"
FIXTURES = BORDEREAUX_ROOT / "tests" / "fixtures"


def _fixture(name: str, builder_module: str, builder: str):
    path = FIXTURES / name
    if not path.exists():
        sys.path.insert(0, str(BORDEREAUX_ROOT / "tests"))
        getattr(__import__(builder_module), builder)()
    return path.read_bytes()


def _reference(path):
    sheets = bpipeline.load_workbook(path)
    proposals = bpipeline.propose_mapping_for_workbook(sheets)
    confirmed = {p.sheet.sheet_name: {s.source_column: s.field_code for s in p.mapping.suggestions if s.field_code}
                 for p in proposals}
    return bpipeline.run_workbook_pipeline(sheets, confirmed, proposals, source_name=path.name)


def test_upload_is_queued_not_processed_inline(api):
    r = api.upload("a.xlsx", xlsx_bytes(simple_rows()))
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "QUEUED"
    assert body["job"]["kind"] == "INGEST" and body["job"]["status"] == "QUEUED"
    assert body["source_sha256"] and len(body["source_sha256"]) == 64
    assert "storage_key" not in body


def test_ingest_proposes_mapping_with_evidence_and_waits_for_review(api):
    rid = api.ingest("a.xlsx", xlsx_bytes(simple_rows()))
    report = api.get(f"/api/v1/reports/{rid}").json()
    assert report["status"] == "WAITING_FOR_REVIEW" and report["job"]["status"] == "SUCCEEDED"
    sheets = api.get(f"/api/v1/reports/{rid}/sheets").json()
    assert len(sheets) == 1 and sheets[0]["status"] == "PENDING_CONFIRMATION"
    m = api.get(f"/api/v1/reports/{rid}/sheets/{sheets[0]['id']}/mapping").json()
    by = {f["field_code"]: f for f in m["fields"]}
    assert by["CR0104M"]["source_column"] == "Claim Reference"
    assert by["CR0104M"]["review_state"] == "HIGH_CONFIDENCE" and by["CR0104M"]["evidence"]
    assert by["CR0104M"]["sample_values"][:1] == ["CLM-0000"]
    assert "Claim Reference" in m["headers"]


def test_process_blocked_until_every_sheet_confirmed(api):
    rid = api.ingest("a.xlsx", xlsx_bytes(simple_rows()))
    r = api.post(f"/api/v1/reports/{rid}/process")
    assert r.status_code == 409 and "confirmed" in r.json()["detail"]


def test_full_run_matches_direct_engine_call(api):
    rid, report = api.full_run(BOUNDARY.name, BOUNDARY.read_bytes())
    ref = _reference(BOUNDARY)
    summary = api.get(f"/api/v1/reports/{rid}/summary").json()["summary"]
    assert report["rows_processed"] == len(ref.canonical)
    assert report["grade"] == str(ref.health.grade)
    assert summary["missing_mandatory_rows"] == ref.health.missing_mandatory_rows
    assert summary["arithmetic_mismatches"] == ref.health.arithmetic_mismatches
    assert summary["arithmetic_not_evaluable"] == ref.health.arithmetic_not_evaluable
    assert summary["exact_duplicates"] == ref.health.exact_duplicates
    assert summary["probable_duplicates"] == ref.health.probable_duplicates
    assert summary["reconciliation"]["reconciles"] is True
    exc = api.get(f"/api/v1/reports/{rid}/exceptions", params={"limit": 1}).json()
    expected = len(ref.validation_result.exceptions) + len(ref.validation_result.not_evaluable_detail)
    assert exc["total"] >= expected  # + mapping-completeness findings
    dups = api.get(f"/api/v1/reports/{rid}/duplicates").json()
    assert dups["total"] == len(ref.duplicates)


def test_reconciliation_scenario_via_api(api):
    content = _fixture("reconciliation_scenario.xlsx", "test_reconciliation", "_build_fixture")
    rid, _ = api.full_run("reconciliation_scenario.xlsx", content)
    sheets = {s["sheet_name"]: s for s in api.get(f"/api/v1/reports/{rid}/sheets").json()}
    assert sheets["Unmappable_Gibberish"]["mapping_status"] == "unmapped"
    assert sheets["Normal"]["mapping_status"] == "mapped"
    summary = api.get(f"/api/v1/reports/{rid}/summary").json()["summary"]
    assert {s["sheet_name"] for s in summary["unmapped_sheets"]} >= {"Unmappable_Gibberish"}
    assert summary["reconciliation"]["reconciles"] is True, summary["reconciliation"]


def test_dashboard_sheet_never_emitted_as_claims(api):
    content = _fixture("dashboard_summary.xlsx", "test_non_claim_summary_sheet", "_build_dashboard_fixture")
    rid, _ = api.full_run("dashboard_summary.xlsx", content)
    sheets = {s["sheet_name"]: s for s in api.get(f"/api/v1/reports/{rid}/sheets").json()}
    assert sheets["Dashboard"]["mapping_status"] == "non_claim_summary"
    summary = api.get(f"/api/v1/reports/{rid}/summary").json()["summary"]
    assert summary["reconciliation"]["exported_rows"] == 10
    assert summary["reconciliation"]["reconciles"] is True


def test_reprocessing_is_idempotent(api, db):
    from app.models.reports import ClaimRow, ValidationResult
    rid, first = api.full_run("a.xlsx", xlsx_bytes(simple_rows(20)))
    n_rows = db.query(ClaimRow).filter_by(report_id=rid).count()
    n_vr = db.query(ValidationResult).filter_by(report_id=rid).count()
    assert n_rows == 20
    assert api.post(f"/api/v1/reports/{rid}/process").status_code == 202
    run_jobs()
    db.expire_all()
    assert db.query(ClaimRow).filter_by(report_id=rid).count() == n_rows
    assert db.query(ValidationResult).filter_by(report_id=rid).count() == n_vr


def test_second_process_request_while_queued_conflicts(api):
    rid = api.ingest("a.xlsx", xlsx_bytes(simple_rows()))
    api.confirm_all(rid)
    assert api.post(f"/api/v1/reports/{rid}/process").status_code == 202
    assert api.post(f"/api/v1/reports/{rid}/process").status_code == 409


def test_mapping_change_blocked_while_job_active(api):
    rid = api.ingest("a.xlsx", xlsx_bytes(simple_rows()))
    api.confirm_all(rid)
    api.post(f"/api/v1/reports/{rid}/process")
    sheet = api.get(f"/api/v1/reports/{rid}/sheets").json()[0]
    r = api.post(f"/api/v1/reports/{rid}/sheets/{sheet['id']}/mapping", json={"mappings": {"CR0035M": None}})
    assert r.status_code == 409


@pytest.mark.parametrize("choices,fragment", [
    ({"CR0104M": "Does Not Exist"}, "does not exist"),
    ({"NOT_A_FIELD": "Claim Reference"}, "Unknown field"),
    ({"CR0035M": "Claim Reference"}, "assigned to both"),  # already bound to CR0104M
])
def test_mapping_confirmation_is_validated_server_side(api, choices, fragment):
    rid = api.ingest("a.xlsx", xlsx_bytes(simple_rows()))
    sheet = api.get(f"/api/v1/reports/{rid}/sheets").json()[0]
    r = api.post(f"/api/v1/reports/{rid}/sheets/{sheet['id']}/mapping", json={"mappings": choices})
    assert r.status_code == 422 and fragment in r.json()["detail"]


def test_mapping_override_is_audited_with_session_identity(api):
    rid = api.ingest("a.xlsx", xlsx_bytes(simple_rows()))
    sheet = api.get(f"/api/v1/reports/{rid}/sheets").json()[0]
    r = api.post(f"/api/v1/reports/{rid}/sheets/{sheet['id']}/mapping",
                 json={"mappings": {"CR0035M": None}, "actor": "someone-else"})
    assert r.status_code == 422, "actor is derived from the session, never accepted from the body"
    r = api.post(f"/api/v1/reports/{rid}/sheets/{sheet['id']}/mapping", json={"mappings": {"CR0035M": None}})
    assert r.status_code == 200
    audit = api.get(f"/api/v1/reports/{rid}/audit", params={"action_type": "MAPPING_OVERRIDDEN"}).json()
    assert audit["total"] == 1 and audit["items"][0]["actor"] == "owner@a.example"


def test_lists_are_paginated(api):
    rows = simple_rows(0) + [[f"DUP", "Same Insured", "2024-01-15", "Open", "GBP", 1, 1, 99]] * 30
    rid, _ = api.full_run("dups.xlsx", xlsx_bytes(rows))
    page = api.get(f"/api/v1/reports/{rid}/exceptions", params={"limit": 5, "offset": 0}).json()
    assert len(page["items"]) == 5 and page["total"] > 5
    page2 = api.get(f"/api/v1/reports/{rid}/exceptions", params={"limit": 5, "offset": 5}).json()
    assert {i["validation_result_id"] for i in page["items"]}.isdisjoint(i["validation_result_id"] for i in page2["items"])
    assert api.get(f"/api/v1/reports/{rid}/exceptions", params={"limit": 5000}).status_code == 422
    claims = api.get(f"/api/v1/reports/{rid}/claims", params={"limit": 10}).json()
    assert claims["total"] == 30 and claims["items"][0]["source_row_number"] == 2


def test_duplicate_review_is_recorded_not_merged(api, db):
    from app.models.reports import ClaimRow
    rows = simple_rows(0) + [["DUP-1", "Same Insured", "2024-01-15", "Open", "GBP", 1, 1, 2]] * 2
    rid, _ = api.full_run("d.xlsx", xlsx_bytes(rows))
    pair = api.get(f"/api/v1/reports/{rid}/duplicates").json()["items"][0]
    r = api.patch(f"/api/v1/reports/{rid}/duplicates/{pair['validation_result_id']}/review",
                  json={"review_status": "confirmed_duplicate"})
    assert r.status_code == 200 and r.json()["review_status"] == "confirmed_duplicate"
    assert db.query(ClaimRow).filter_by(report_id=rid).count() == 2
    bad = api.patch(f"/api/v1/reports/{rid}/duplicates/{pair['validation_result_id']}/review",
                    json={"review_status": "delete_it"})
    assert bad.status_code == 422


def test_totals_are_per_currency(api):
    rows = [["Claim Reference", "Insured Name", "Currency", "Paid to Date", "Outstanding Reserve", "Total Incurred"],
            ["A1", "X", "GBP", 100, 0, 100], ["A2", "Y", "USD", 200, 0, 200], ["A3", "Z", "GBP", 50, 0, 50]]
    rid, _ = api.full_run("ccy.xlsx", xlsx_bytes(rows))
    totals = {t["currency"]: t for t in api.get(f"/api/v1/reports/{rid}/summary").json()["summary"]["totals_by_currency"]}
    assert totals["GBP"]["paid_to_date"] == 150 and totals["USD"]["paid_to_date"] == 200


def test_file_with_no_data_fails_clearly(api):
    rid = api.ingest("empty.xlsx", xlsx_bytes([["just a title"]]))
    report = api.get(f"/api/v1/reports/{rid}").json()
    assert report["status"] == "FAILED" and report["error_code"] == "no_data"
    assert report["job"]["error_message"] and "Traceback" not in (report["processing_error"] or "")
    sheets = api.get(f"/api/v1/reports/{rid}/sheets").json()
    assert sheets and sheets[0]["status"] == "SKIPPED" and sheets[0]["skip_reason"]


def test_unreadable_file_fails_with_safe_message(api, db):
    import io
    import zipfile
    from app.models.jobs import Job
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("xl/workbook.xml", "<this is not valid xml")
    rid = api.ingest("broken.xlsx", buf.getvalue())
    report = api.get(f"/api/v1/reports/{rid}").json()
    assert report["status"] == "FAILED" and report["error_code"] == "unreadable_file"
    assert "Traceback" not in str(report) and "error_detail" not in str(report)
    job = db.query(Job).filter_by(report_id=rid).one()
    assert job.error_detail, "internal detail is kept server-side for diagnosis"


def test_failed_report_can_be_retried(api, db):
    from app.models.jobs import Job
    rid = api.ingest("empty.xlsx", xlsx_bytes([["just a title"]]))
    assert api.post(f"/api/v1/reports/{rid}/retry").status_code == 202
    assert db.query(Job).filter_by(report_id=rid).count() == 2


def test_delete_removes_file_and_data_but_keeps_audit(api, db):
    from app.config import STORAGE_DIR
    from app.models.audit import AuditLogEntry
    from app.models.reports import ClaimRow, Report
    rid, _ = api.full_run("a.xlsx", xlsx_bytes(simple_rows()))
    report = db.get(Report, rid)
    path = STORAGE_DIR / report.storage_key
    assert path.exists()
    assert api.delete(f"/api/v1/reports/{rid}").status_code == 204
    db.expire_all()
    assert not path.exists()
    assert db.get(Report, rid) is None and db.query(ClaimRow).filter_by(report_id=rid).count() == 0
    assert db.query(AuditLogEntry).filter_by(report_id=rid, action_type="REPORT_DELETED").count() == 1


def test_retention_expires_reports(api, db):
    from datetime import timedelta
    from app.models._util import utcnow
    from app.models.reports import Report
    from app.services import retention_service
    rid, _ = api.full_run("a.xlsx", xlsx_bytes(simple_rows()))
    db.get(Report, rid).expires_at = utcnow() - timedelta(days=1)
    db.commit()
    assert retention_service.expire_due_reports(db) == 1
    assert api.get(f"/api/v1/reports/{rid}").status_code == 404


def test_every_source_row_and_sheet_is_accounted_for(api):
    """Ledger check through the whole API: claims + structural exclusions
    account for every row below the header; blank gaps do not truncate
    later data; the Total row is not a claim; every sheet ends in an
    explicit, reasoned status."""
    rows = simple_rows(5) + [[None] * 8] * 3 + simple_rows(2)[1:] + [["Total", None, None, None, None, 2021, 1000, 3021]]
    rows[-2][0] = "CLM-LATE"
    content = xlsx_bytes(rows, extra_sheets={"Empty": [], "Notes": [["Prepared by ops"], ["see email"]]})
    rid, report = api.full_run("ledger.xlsx", content)
    summary = api.get(f"/api/v1/reports/{rid}/summary").json()["summary"]
    rec = summary["reconciliation"]
    assert report["rows_processed"] == 7, "rows after the blank gap are kept; the Total row is not a claim"
    refs = {c["claim_reference"] for c in api.get(f"/api/v1/reports/{rid}/claims").json()["items"]}
    assert "CLM-LATE" in refs and "Total" not in refs
    excluded = api.get(f"/api/v1/reports/{rid}/excluded-rows").json()["items"]
    reasons = {e["reason"] for e in excluded}
    assert "subtotal" in reasons and reasons & {"blank", "blank_run"}
    accounted = rec["exported_rows"] + sum(e["row_count"] for e in excluded if e["sheet_name"] == "Claims")
    assert accounted == len(rows) - 1, "every row below the header is a claim or a recorded exclusion"
    assert rec["reconciles"] is True
    explicit = {"mapped", "partial", "unmapped", "empty", "error", "non_claim_summary"}
    for s in api.get(f"/api/v1/reports/{rid}/sheets").json():
        assert s["mapping_status"] in explicit, s
        if s["status"] == "SKIPPED":
            assert s["skip_reason"], s


# ---------------------------------------------------------------- user regression replicas (2026-09-24)

def _replica(name):
    sys.path.insert(0, str(BORDEREAUX_ROOT / "tests" / "regression_fixtures"))
    import build_replicas
    return build_replicas, getattr(build_replicas, name)()


def test_void_status_completes_not_failed(api):
    _, path = _replica("realworld_a")
    rid, report = api.full_run(path.name, path.read_bytes())
    assert report["status"] == "COMPLETE" and report["grade"] == "5"
    exc = api.get(f"/api/v1/reports/{rid}/exceptions", params={"check_type": "STATUS"}).json()
    assert exc["total"] == 0, "Void is an accepted status (domain_config.CLAIM_STATUSES)"


def test_paid_expenses_included_in_total_incurred(api):
    _, path = _replica("test1_basic")
    rid, report = api.full_run(path.name, path.read_bytes())
    s = api.get(f"/api/v1/reports/{rid}/summary").json()["summary"]
    assert s["arithmetic_mismatches"] == 0 and s["arithmetic_matches"] == 12
    assert s["composite_score"] == 100
    claims = api.get(f"/api/v1/reports/{rid}/claims").json()["items"]
    assert all(c["fees_paid_to_date"] is not None for c in claims)


def test_stress_unmapped_columns_and_period_aware_duplicates(api):
    br, path = _replica("stress_450")
    rid, report = api.full_run(path.name, path.read_bytes())
    s = api.get(f"/api/v1/reports/{rid}/summary").json()["summary"]
    unmapped = sorted(c for e in s["unmapped_source_columns"] for c in e["columns"])
    assert unmapped == sorted(c for pair in br.SENDER_COLS.values() for c in pair)
    audit = api.get(f"/api/v1/reports/{rid}/audit", params={"action_type": "SOURCE_COLUMN_UNMAPPED"}).json()
    assert audit["total"] == 6 and audit["items"][0]["after_value"]["field_code"] is None
    claims = api.get(f"/api/v1/reports/{rid}/claims", params={"limit": 1000}).json()["items"]
    pairs = [set(p) for p in br.SENDER_COLS.values()]
    assert all(set(c["unmapped_values"] or {}) in pairs for c in claims), "unclaimed data retained on every row"
    dups = api.get(f"/api/v1/reports/{rid}/duplicates", params={"limit": 1000}).json()["items"]
    exact = [d for d in dups if d["match_type"] == "exact_duplicate"]
    dup_refs = {d["row_a"]["claim_reference"] for d in dups}
    assert len(exact) == 6 and dup_refs == set(br.DUP_REFS)
    assert not dup_refs & set(br.DEV_REFS), "development pairs are never duplicates"
    assert s["development_pairs"] == 6 and set(s["development_refs"]) == set(br.DEV_REFS)
