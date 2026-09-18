"""Senior-pass fix spec Section 5 (mapping-completeness as a first-class
exception category, and DATA_QUALITY no longer mislabeled as it) and
Section 6.2/6.5 (report processing runs as a background task, returns
immediately, and a report interrupted by a crash/restart resolves to a
clear FAILED state instead of spinning forever)."""

from __future__ import annotations

import io

import openpyxl

from app import database
from app.models.reports import Report


def _workbook_bytes(headers: list[str], rows: list[list]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_process_returns_immediately_and_report_reaches_complete(client):
    content = _workbook_bytes(
        ["Claim Reference", "Insured Name", "Date of Loss", "Paid Amount", "Reserve Amount", "Incurred Amount"],
        [["CLM-1", "Acme Ltd", "2024-01-05", 1000, 500, 1500]],
    )
    resp = client.post("/api/v1/reports/upload", files={"file": ("f.xlsx", content,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    report_id = resp.json()["id"]

    sheets = client.get(f"/api/v1/reports/{report_id}/sheets").json()
    for sheet in sheets:
        mapping = client.get(f"/api/v1/reports/{report_id}/sheets/{sheet['sheet_name']}/mapping").json()
        choices = {m["field_code"]: m["source_column"] for m in mapping}
        client.post(f"/api/v1/reports/{report_id}/sheets/{sheet['sheet_name']}/mapping/confirm",
                    json={"mappings": choices, "actor": "pytest"})

    process = client.post(f"/api/v1/reports/{report_id}/process")
    # Fix spec 6.2: 202 + PROCESSING immediately, not the finished report.
    assert process.status_code == 202
    assert process.json()["status"] == "PROCESSING"

    final = client.get(f"/api/v1/reports/{report_id}").json()
    assert final["status"] == "COMPLETE"
    assert final["processing_phase"] is None
    assert final["processing_error"] is None


def test_mapping_completeness_is_a_first_class_exception(client):
    """A sheet with unmappable (non-English) headers alongside a normal
    English sheet must produce a visible MAPPING_COMPLETENESS exception
    -- fix spec Section 1's confirmed symptom surfaced through Section
    5's dashboard category, not just an inflated not-evaluable count."""
    content = _workbook_bytes(
        ["Référence du sinistre", "Nom de l'assuré", "Date du sinistre", "Montant payé", "Réserve", "Montant total"],
        [["SIN-1", "Société Dupont", "2024-01-05", 1200, 300, 1500],
         ["SIN-2", "Société Martin", "2024-02-10", 800, 200, 1000]],
    )
    resp = client.post("/api/v1/reports/upload", files={"file": ("french.xlsx", content,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    report_id = resp.json()["id"]
    assert resp.json()["sheet_count_total"] == 1, "the low-confidence sheet must still be counted, not dropped"

    sheets = client.get(f"/api/v1/reports/{report_id}/sheets").json()
    assert sheets[0]["status"] != "SKIPPED", "an unmappable-header sheet is processed, not skipped"

    for sheet in sheets:
        mapping = client.get(f"/api/v1/reports/{report_id}/sheets/{sheet['sheet_name']}/mapping").json()
        choices = {m["field_code"]: m["source_column"] for m in mapping}
        confirm = client.post(f"/api/v1/reports/{report_id}/sheets/{sheet['sheet_name']}/mapping/confirm",
                               json={"mappings": choices, "actor": "pytest"})
        assert confirm.status_code == 200

    process = client.post(f"/api/v1/reports/{report_id}/process")
    assert process.status_code == 202

    exceptions = client.get(f"/api/v1/reports/{report_id}/exceptions?check_type=MAPPING_COMPLETENESS").json()
    assert len(exceptions) >= 1, "expected a first-class mapping-completeness exception, got none"
    assert "needs manual review" in exceptions[0]["message"]


def test_data_quality_rules_are_not_mislabeled_as_mapping_completeness(client):
    """Date/currency/status rule violations are their own DATA_QUALITY
    category -- previously they fell into the MAPPING_COMPLETENESS
    catch-all just because they weren't ARITHMETIC or MANDATORY_FIELD."""
    content = _workbook_bytes(
        ["Claim Reference", "Insured Name", "Date of Loss", "Date First Notified",
         "Paid Amount", "Reserve Amount", "Incurred Amount"],
        # date of loss AFTER date first notified -> date_order violation
        [["CLM-1", "Acme Ltd", "2024-06-01", "2024-01-01", 1000, 500, 1500]],
    )
    resp = client.post("/api/v1/reports/upload", files={"file": ("f.xlsx", content,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    report_id = resp.json()["id"]

    sheets = client.get(f"/api/v1/reports/{report_id}/sheets").json()
    for sheet in sheets:
        mapping = client.get(f"/api/v1/reports/{report_id}/sheets/{sheet['sheet_name']}/mapping").json()
        choices = {m["field_code"]: m["source_column"] for m in mapping}
        client.post(f"/api/v1/reports/{report_id}/sheets/{sheet['sheet_name']}/mapping/confirm",
                    json={"mappings": choices, "actor": "pytest"})

    client.post(f"/api/v1/reports/{report_id}/process")

    data_quality = client.get(f"/api/v1/reports/{report_id}/exceptions?check_type=DATA_QUALITY").json()
    assert any("date of loss" in e["message"] for e in data_quality), (
        f"expected the date_order violation under DATA_QUALITY, got: {data_quality}"
    )
    mapping_completeness = client.get(
        f"/api/v1/reports/{report_id}/exceptions?check_type=MAPPING_COMPLETENESS").json()
    assert not any("date of loss" in e["message"] for e in mapping_completeness), (
        "a date-order violation must never show up under MAPPING_COMPLETENESS"
    )


def test_csv_upload_sheet_name_is_stable_across_requests(client):
    """A CSV's implicit single "sheet" used to be named after whatever
    path happened to be read from: a random temp filename at upload time
    (upload.py stages the file under tempfile.NamedTemporaryFile before
    it has a report id to store it under), but the real stored filename
    at every later read (mapping confirmation, /process) -- so the name
    recorded in the Sheet row never matched what get_sheet_mapping/
    confirm_sheet_mapping/process_report looked up, and every CSV upload
    404'd immediately after the initial upload response. Reproduced live
    against a running server before this fix; this locks it down."""
    csv_bytes = (
        b"Claim Reference,Insured Name,Date of Loss,Paid Amount,Reserve Amount,Incurred Amount\n"
        b"CLM-1,Acme Ltd,2024-01-05,1000,500,1500\n"
    )
    resp = client.post("/api/v1/reports/upload", files={"file": ("my_bordereau.csv", csv_bytes, "text/csv")})
    assert resp.status_code == 200, resp.text
    report_id = resp.json()["id"]

    sheets = client.get(f"/api/v1/reports/{report_id}/sheets").json()
    assert len(sheets) == 1
    sheet_name = sheets[0]["sheet_name"]
    assert sheet_name == "my_bordereau", f"expected the sheet to be named after the upload, got {sheet_name!r}"

    headers = client.get(f"/api/v1/reports/{report_id}/sheets/{sheet_name}/headers")
    assert headers.status_code == 200, headers.text

    mapping = client.get(f"/api/v1/reports/{report_id}/sheets/{sheet_name}/mapping")
    assert mapping.status_code == 200, mapping.text
    choices = {m["field_code"]: m["source_column"] for m in mapping.json()}
    confirm = client.post(f"/api/v1/reports/{report_id}/sheets/{sheet_name}/mapping/confirm",
                           json={"mappings": choices, "actor": "pytest"})
    assert confirm.status_code == 200, confirm.text

    process = client.post(f"/api/v1/reports/{report_id}/process")
    assert process.status_code == 202, process.text


def test_interrupted_processing_resolves_to_failed_on_restart(client):
    """Fix spec Section 6.5: simulate a backend crash mid-run by leaving
    a report stuck at status=PROCESSING, then simulate a restart by
    re-running the startup repair directly (lifespan already ran once
    when `client` was created; call it again here to simulate the NEXT
    restart finding this leftover state)."""
    from app.main import _fail_interrupted_processing_runs

    db = database.get_session_factory()()
    try:
        report = Report(file_name="stuck.xlsx", file_size_bytes=10, sheet_count_total=1, status="PROCESSING",
                         processing_phase="validating and deduplicating")
        db.add(report)
        db.commit()
        report_id = report.id
    finally:
        db.close()

    _fail_interrupted_processing_runs()

    resp = client.get(f"/api/v1/reports/{report_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "FAILED"
    assert body["processing_phase"] is None
    assert body["processing_error"], "a named reason must be shown, not a bare FAILED with no explanation"
