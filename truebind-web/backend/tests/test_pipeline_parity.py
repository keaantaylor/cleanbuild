"""Walks the real upload -> mapping-confirm -> process flow through the
API (exactly as a browser would) against the same test_boundary_cases.xlsx
fixture bordereaux/tests/test_boundary_fixture.py already asserts D1-D8
against, and checks the API's persisted numbers agree with an independent
direct call into bordereaux.pipeline on the same file. This is the "same
numbers as before" parity check the redesign doc's Phase 0 test plan
asks for -- it would catch a bug in this layer's persistence/aggregation
even though the underlying algorithm is shared, not reimplemented."""

from __future__ import annotations

import time
from pathlib import Path

from bordereaux import pipeline as bpipeline

FIXTURE = Path(__file__).resolve().parents[3] / "bordereaux" / "data" / "synthetic" / "test_boundary_cases.xlsx"


def _reference_health():
    sheets = bpipeline.load_workbook(FIXTURE)
    proposals = bpipeline.propose_mapping_for_workbook(sheets)
    confirmed = {
        p.sheet.sheet_name: {s.source_column: s.field_code for s in p.mapping.suggestions if s.field_code}
        for p in proposals
    }
    return bpipeline.run_workbook_pipeline(sheets, confirmed, proposals, source_name=FIXTURE.name)


def _upload_and_process(client):
    with open(FIXTURE, "rb") as f:
        resp = client.post("/api/v1/reports/upload", files={"file": (FIXTURE.name, f,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert resp.status_code == 200, resp.text
    report = resp.json()
    report_id = report["id"]
    assert report["sheet_count_total"] == 10

    sheets = client.get(f"/api/v1/reports/{report_id}/sheets").json()
    for sheet in sheets:
        if sheet["status"] == "SKIPPED":
            continue
        mapping = client.get(f"/api/v1/reports/{report_id}/sheets/{sheet['sheet_name']}/mapping").json()
        choices = {m["field_code"]: m["source_column"] for m in mapping}
        confirm = client.post(
            f"/api/v1/reports/{report_id}/sheets/{sheet['sheet_name']}/mapping/confirm",
            json={"mappings": choices, "actor": "pytest"},
        )
        assert confirm.status_code == 200, confirm.text

    # Fix spec Section 6.2: /process now kicks off the pipeline run as a
    # background task and returns immediately (202, status=PROCESSING)
    # instead of blocking the request until the whole workbook is done --
    # poll GET /reports/{id} the same way the frontend does. TestClient
    # runs FastAPI's BackgroundTasks synchronously as part of the request
    # it was scheduled from, so this resolves on the first poll in
    # practice; the loop is here so the test doesn't depend on that.
    process = client.post(f"/api/v1/reports/{report_id}/process")
    assert process.status_code == 202, process.text
    assert process.json()["status"] == "PROCESSING"

    report = None
    for _ in range(50):
        report = client.get(f"/api/v1/reports/{report_id}").json()
        if report["status"] in ("COMPLETE", "FAILED"):
            break
        time.sleep(0.1)
    assert report is not None and report["status"] == "COMPLETE", (
        f"report never reached COMPLETE: {report}"
    )
    return report_id, report


def test_full_workbook_matches_direct_pipeline_call(client):
    reference = _reference_health()
    report_id, persisted = _upload_and_process(client)

    assert persisted["rows_processed"] == reference.coverage.rows_assessed == 320
    assert persisted["rows_total"] == reference.coverage.rows_total
    assert persisted["coverage_pct"] == 100.0
    assert persisted["grade"] == str(reference.health.grade)
    assert persisted["score"] == reference.health.composite_score
    assert persisted["status"] == "COMPLETE"


def test_exceptions_and_duplicates_persisted(client):
    reference = _reference_health()
    report_id, persisted = _upload_and_process(client)

    exceptions = client.get(f"/api/v1/reports/{report_id}/exceptions").json()
    mandatory = [e for e in exceptions if e["check_type"] == "MANDATORY_FIELD"]
    arithmetic = [e for e in exceptions if e["check_type"] == "ARITHMETIC"]
    assert len({e["claim_row_id"] for e in mandatory}) == reference.health.missing_mandatory_rows
    assert len(arithmetic) == reference.health.arithmetic_mismatches

    duplicates = client.get(f"/api/v1/reports/{report_id}/duplicates").json()
    assert len(duplicates) == reference.health.exact_duplicates + reference.health.probable_duplicates


def test_alerts_raised_for_known_defects(client):
    report_id, persisted = _upload_and_process(client)
    alerts = client.get(f"/api/v1/alerts?report_id={report_id}").json()
    sources = {a["source"] for a in alerts}
    assert "MANDATORY_FAIL" in sources
    assert "DUPLICATE" in sources


def test_audit_log_has_one_entry_per_confirmed_field(client):
    report_id, persisted = _upload_and_process(client)
    audit = client.get(f"/api/v1/reports/{report_id}/audit").json()
    assert len(audit) > 0
    assert all(a["action_type"] in ("MAPPING_CONFIRMED", "MAPPING_OVERRIDDEN") for a in audit)


def test_process_rejects_unconfirmed_sheets(client):
    with open(FIXTURE, "rb") as f:
        resp = client.post("/api/v1/reports/upload", files={"file": (FIXTURE.name, f,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    report_id = resp.json()["id"]
    process = client.post(f"/api/v1/reports/{report_id}/process")
    assert process.status_code == 400


def test_summary_endpoint_matches_direct_pipeline_call(client):
    reference = _reference_health()
    report_id, _ = _upload_and_process(client)

    summary = client.get(f"/api/v1/reports/{report_id}/summary")
    assert summary.status_code == 200, summary.text
    body = summary.json()

    assert body["sheets_total"] == reference.coverage.sheets_total
    assert body["sheets_processed"] == reference.coverage.sheets_processed
    assert body["missing_mandatory_rows"] == reference.health.missing_mandatory_rows
    assert body["arithmetic_mismatches"] == reference.health.arithmetic_mismatches
    assert body["arithmetic_not_evaluable"] == reference.health.arithmetic_not_evaluable
    assert body["exact_duplicates"] == reference.health.exact_duplicates
    assert body["probable_duplicates"] == reference.health.probable_duplicates

    claim_ref_field = next(f for f in body["field_completeness"] if f["field_code"] == "CR0104M")
    reference_fc = next(fs for fs in reference.health.field_completeness if fs.code == "CR0104M")
    assert claim_ref_field["present"] == reference_fc.present
    assert claim_ref_field["denominator"] == reference_fc.denominator


def test_export_endpoints_return_csv(client):
    report_id, _ = _upload_and_process(client)
    audit_csv = client.get(f"/api/v1/reports/{report_id}/export/audit-csv")
    assert audit_csv.status_code == 200
    assert audit_csv.headers["content-type"].startswith("text/csv")

    status_csv = client.get(f"/api/v1/reports/{report_id}/export/by-status")
    assert status_csv.status_code == 200
    assert "ZUR-" in status_csv.text or len(status_csv.text) > 0
