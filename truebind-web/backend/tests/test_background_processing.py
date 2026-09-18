"""Section 6: /process moved the ingest/mapping/validation/dedupe/persist
pipeline off the request thread onto a background thread with its own DB
session, returning immediately at PROCESSING for the caller to poll via
GET /{report_id}. These tests cover the contract that move introduces --
none of it was exercised by test_pipeline_parity.py, which only ever
waited for the end state."""

from __future__ import annotations

import time
from pathlib import Path

from app.services import pipeline_service

FIXTURE = Path(__file__).resolve().parents[3] / "bordereaux" / "data" / "synthetic" / "test_boundary_cases.xlsx"


def _upload_and_confirm(client) -> str:
    with open(FIXTURE, "rb") as f:
        resp = client.post("/api/v1/reports/upload", files={"file": (FIXTURE.name, f,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert resp.status_code == 200, resp.text
    report_id = resp.json()["id"]

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
    return report_id


def _wait_for_terminal_status(client, report_id: str, timeout: float = 10.0) -> dict:
    deadline = time.time() + timeout
    report = client.get(f"/api/v1/reports/{report_id}").json()
    while report["status"] == "PROCESSING" and time.time() < deadline:
        time.sleep(0.02)
        report = client.get(f"/api/v1/reports/{report_id}").json()
    return report


def test_process_returns_immediately_at_processing_status(client):
    report_id = _upload_and_confirm(client)

    process = client.post(f"/api/v1/reports/{report_id}/process")
    assert process.status_code == 202, process.text
    assert process.json()["status"] == "PROCESSING"

    # The pipeline for this small fixture may already be done by the time
    # we ask -- what matters is the /process response itself never blocked
    # for the pipeline to finish, which the 202 + PROCESSING body proves.
    report = _wait_for_terminal_status(client, report_id)
    assert report["status"] == "COMPLETE"


def test_process_failure_marks_report_failed_not_stuck_processing(client, monkeypatch):
    """A pipeline exception must never vanish into the background thread
    and leave the report stuck at PROCESSING forever -- it has to land as
    a visible FAILED status with the error message, the same
    never-silent-drop standard the rest of this round holds every other
    layer to."""
    report_id = _upload_and_confirm(client)

    def boom(*args, **kwargs):
        raise RuntimeError("synthetic pipeline failure for test coverage")

    monkeypatch.setattr(pipeline_service, "run_workbook_pipeline", boom)

    process = client.post(f"/api/v1/reports/{report_id}/process")
    assert process.status_code == 202, process.text

    report = _wait_for_terminal_status(client, report_id)
    assert report["status"] == "FAILED"
    assert "synthetic pipeline failure" in report["processing_error"]


def test_process_rejects_concurrent_reprocessing(client, monkeypatch):
    report_id = _upload_and_confirm(client)

    real_run = pipeline_service.run_workbook_pipeline

    def slow_run(*args, **kwargs):
        time.sleep(0.3)
        return real_run(*args, **kwargs)

    monkeypatch.setattr(pipeline_service, "run_workbook_pipeline", slow_run)

    first = client.post(f"/api/v1/reports/{report_id}/process")
    assert first.status_code == 202
    assert first.json()["status"] == "PROCESSING"

    second = client.post(f"/api/v1/reports/{report_id}/process")
    assert second.status_code == 409, second.text

    report = _wait_for_terminal_status(client, report_id)
    assert report["status"] == "COMPLETE"


def test_failed_report_can_be_reprocessed(client, monkeypatch):
    """FAILED isn't a dead end -- once whatever caused the failure is
    addressed, re-submitting /process must be allowed to try again."""
    report_id = _upload_and_confirm(client)

    def boom(*args, **kwargs):
        raise RuntimeError("transient failure")

    monkeypatch.setattr(pipeline_service, "run_workbook_pipeline", boom)
    client.post(f"/api/v1/reports/{report_id}/process")
    failed = _wait_for_terminal_status(client, report_id)
    assert failed["status"] == "FAILED"

    monkeypatch.undo()
    retry = client.post(f"/api/v1/reports/{report_id}/process")
    assert retry.status_code == 202, retry.text

    report = _wait_for_terminal_status(client, report_id)
    assert report["status"] == "COMPLETE"
    assert report["processing_error"] is None
