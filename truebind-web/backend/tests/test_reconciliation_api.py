"""Regression test for the forensic repair brief: the real upload ->
mapping -> process -> summary API path must surface per-sheet mapping
status (mapped/partial/unmapped/empty) and a row-count reconciliation
that actually reconciles, for a workbook containing a fully-opaque-
header sheet and a large foreign-language sheet alongside a normal one.
Reuses bordereaux's own reconciliation_scenario.xlsx fixture (built by
bordereaux/tests/test_reconciliation.py) rather than a disconnected
duplicate, so this exercises the exact file bordereaux's own test
already proves the numbers for."""

from __future__ import annotations

import sys
import time
from pathlib import Path

BORDEREAUX_ROOT = Path(__file__).resolve().parents[3] / "bordereaux"
sys.path.insert(0, str(BORDEREAUX_ROOT / "src"))

FIXTURE = BORDEREAUX_ROOT / "tests" / "fixtures" / "reconciliation_scenario.xlsx"


def _build_fixture_if_missing() -> None:
    if FIXTURE.exists():
        return
    sys.path.insert(0, str(BORDEREAUX_ROOT / "tests"))
    import test_reconciliation as bordereaux_recon_test  # noqa: PLC0415

    bordereaux_recon_test._build_fixture()


def _upload_map_and_process(client) -> tuple[str, dict]:
    _build_fixture_if_missing()
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

    process = client.post(f"/api/v1/reports/{report_id}/process")
    assert process.status_code == 202, process.text

    deadline = time.time() + 15
    report = client.get(f"/api/v1/reports/{report_id}").json()
    while report["status"] == "PROCESSING" and time.time() < deadline:
        time.sleep(0.02)
        report = client.get(f"/api/v1/reports/{report_id}").json()
    assert report["status"] == "COMPLETE", report
    return report_id, report


def test_sheet_mapping_status_exposed_via_api(client) -> None:
    report_id, _ = _upload_map_and_process(client)
    sheets = {s["sheet_name"]: s for s in client.get(f"/api/v1/reports/{report_id}/sheets").json()}

    assert sheets["Unmappable_Gibberish"]["mapping_status"] == "unmapped"
    assert sheets["Unmappable_Gibberish"]["fields_mapped"] == 0
    assert sheets["FR_Cedante_Full"]["mapping_status"] == "unmapped"
    assert sheets["Normal"]["mapping_status"] == "mapped"
    assert sheets["Normal"]["fields_mapped"] > 0


def test_unmapped_sheets_and_reconciliation_in_summary(client) -> None:
    report_id, _ = _upload_map_and_process(client)
    summary = client.get(f"/api/v1/reports/{report_id}/summary").json()

    unmapped_names = {s["sheet_name"] for s in summary["unmapped_sheets"]}
    assert unmapped_names == {"Unmappable_Gibberish", "FR_Cedante_Full"}

    recon = summary["reconciliation"]
    assert recon["source_worksheets"] == 3
    assert recon["mapped_rows"] == 2
    assert recon["unmapped_rows"] == 1100
    assert recon["rejected_rows"] == 1
    assert recon["duplicate_rows"] == 2
    assert recon["exported_rows"] == 1102
    assert recon["source_data_rows"] == 1103
    assert recon["rows_requiring_review"] == 1102
    assert recon["reconciles"] is True, recon


DASHBOARD_FIXTURE = BORDEREAUX_ROOT / "tests" / "fixtures" / "dashboard_summary.xlsx"


def _build_dashboard_fixture_if_missing() -> None:
    if DASHBOARD_FIXTURE.exists():
        return
    sys.path.insert(0, str(BORDEREAUX_ROOT / "tests"))
    import test_non_claim_summary_sheet as bordereaux_ncs_test  # noqa: PLC0415

    bordereaux_ncs_test._build_dashboard_fixture()


def test_non_claim_summary_sheet_excluded_via_full_api_path(client) -> None:
    """TB-001 end-to-end: the real upload -> mapping -> process -> summary
    API path must never emit a Dashboard tab's aggregate rows as claims,
    and must name it explicitly as recognised-but-excluded rather than
    silently dropping it or silently inflating the total."""
    _build_dashboard_fixture_if_missing()
    with open(DASHBOARD_FIXTURE, "rb") as f:
        resp = client.post("/api/v1/reports/upload", files={"file": (DASHBOARD_FIXTURE.name, f,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert resp.status_code == 200, resp.text
    report_id = resp.json()["id"]

    sheets_list = client.get(f"/api/v1/reports/{report_id}/sheets").json()
    for sheet in sheets_list:
        if sheet["status"] == "SKIPPED":
            continue
        mapping = client.get(f"/api/v1/reports/{report_id}/sheets/{sheet['sheet_name']}/mapping").json()
        choices = {m["field_code"]: m["source_column"] for m in mapping}
        confirm = client.post(
            f"/api/v1/reports/{report_id}/sheets/{sheet['sheet_name']}/mapping/confirm",
            json={"mappings": choices, "actor": "pytest"},
        )
        assert confirm.status_code == 200, confirm.text

    process = client.post(f"/api/v1/reports/{report_id}/process")
    assert process.status_code == 202, process.text

    deadline = time.time() + 15
    report = client.get(f"/api/v1/reports/{report_id}").json()
    while report["status"] == "PROCESSING" and time.time() < deadline:
        time.sleep(0.02)
        report = client.get(f"/api/v1/reports/{report_id}").json()
    assert report["status"] == "COMPLETE", report

    sheets = {s["sheet_name"]: s for s in client.get(f"/api/v1/reports/{report_id}/sheets").json()}
    assert sheets["Dashboard"]["mapping_status"] == "non_claim_summary"
    assert sheets["Direct_GBP"]["mapping_status"] == "mapped"

    summary = client.get(f"/api/v1/reports/{report_id}/summary").json()
    ncs_names = {s["sheet_name"] for s in summary["non_claim_summary_sheets"]}
    assert ncs_names == {"Dashboard"}

    recon = summary["reconciliation"]
    assert recon["exported_rows"] == 10, "only the real claims sheet's 10 rows, never the Dashboard's"
    assert recon["non_claim_summary_rows"] == 3
    assert recon["reconciles"] is True, recon
