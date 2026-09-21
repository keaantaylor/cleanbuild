"""AI exception-triage summariser: the deterministic aggregation (this is
the part that MUST be correct -- covered thoroughly) and graceful
degradation when the LLM is unavailable, times out, or errors (the
Exceptions page must never break because of it)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app import database
from app.models.reports import ClaimRow, Report, Sheet, ValidationResult
from app.services import exception_aggregation_service, exception_narrative_service


def _make_report_with_findings(db):
    report = Report(file_name="f.xlsx", file_size_bytes=1, sheet_count_total=2, status="COMPLETE",
                     rows_total=4, rows_processed=4)
    db.add(report)
    db.flush()

    good_sheet = Sheet(report_id=report.id, sheet_name="Zurich Re", sheet_index=0, row_count=3, status="CONFIRMED")
    bad_sheet = Sheet(report_id=report.id, sheet_name="French Sheet", sheet_index=1, row_count=1, status="CONFIRMED")
    db.add_all([good_sheet, bad_sheet])
    db.flush()

    # Well-mapped sheet: one genuine arithmetic mismatch (data quality),
    # one duplicate finding.
    row1 = ClaimRow(report_id=report.id, sheet_id=good_sheet.id, row_index=0, claim_reference="C1",
                     paid_amount=1000.0, reserve_amount=500.0, incurred_amount=2000.0)
    row2 = ClaimRow(report_id=report.id, sheet_id=good_sheet.id, row_index=1, claim_reference="C2",
                     paid_amount=100.0, reserve_amount=0.0, incurred_amount=100.0)
    # Poorly-mapped sheet: a MAPPING_COMPLETENESS finding plus a
    # mandatory-field finding that should be classified "ingestion" too,
    # since it's on the same low-completeness sheet.
    row3 = ClaimRow(report_id=report.id, sheet_id=bad_sheet.id, row_index=0, incurred_amount=5000.0)
    db.add_all([row1, row2, row3])
    db.flush()

    db.add_all([
        ValidationResult(claim_row_id=row1.id, check_type="ARITHMETIC", status="FAIL", severity="HIGH",
                          message="incurred=2000 but paid+reserve=1500"),
        ValidationResult(claim_row_id=row2.id, check_type="DUPLICATE", status="FAIL", severity="MEDIUM",
                          message="probable duplicate", extra={"match_type": "probable_duplicate"}),
        ValidationResult(claim_row_id=row3.id, check_type="MAPPING_COMPLETENESS", status="FAIL",
                          severity="CRITICAL", message="Sheet 'French Sheet': only 1 of 10 expected fields mapped."),
        ValidationResult(claim_row_id=row3.id, check_type="MANDATORY_FIELD", status="FAIL", severity="CRITICAL",
                          message="CR0104M (Claim reference) is missing"),
    ])
    db.commit()
    db.refresh(report)
    return report


@pytest.fixture
def db_session(client):
    # `client` fixture (conftest.py) already points database.get_session_
    # factory() at this test's isolated in-memory engine.
    session = database.get_session_factory()()
    yield session
    session.close()


def test_aggregate_groups_by_category_sheet_and_root_cause(db_session):
    report = _make_report_with_findings(db_session)
    aggregate = exception_aggregation_service.build_aggregate(db_session, report)

    assert aggregate["total_exceptions"] == 4
    # Deduped by row (row3 has 2 exceptions but counts once):
    # row1 (incurred 2000) + row2 (incurred 100) + row3 (incurred 5000) = 7100
    assert aggregate["total_value_at_stake"] == 7100.0

    by_category = {c["check_type"]: c for c in aggregate["by_category"]}
    assert by_category["ARITHMETIC"]["count"] == 1
    assert by_category["ARITHMETIC"]["value_at_stake"] == 2000.0
    assert by_category["MAPPING_COMPLETENESS"]["count"] == 1
    assert by_category["MAPPING_COMPLETENESS"]["value_at_stake"] == 5000.0
    assert by_category["DUPLICATE"]["count"] == 1
    assert by_category["DUPLICATE"]["value_at_stake"] == 100.0

    by_sheet = {s["sheet_name"]: s for s in aggregate["by_sheet"]}
    assert by_sheet["French Sheet"]["low_mapping_completeness"] is True
    assert by_sheet["French Sheet"]["count"] == 2  # MAPPING_COMPLETENESS + MANDATORY_FIELD
    assert by_sheet["French Sheet"]["value_at_stake"] == 10000.0  # 5000 counted once per exception on it
    assert by_sheet["Zurich Re"]["low_mapping_completeness"] is False
    assert by_sheet["Zurich Re"]["value_at_stake"] == 2100.0

    root = aggregate["root_cause_split"]
    # MAPPING_COMPLETENESS itself + the MANDATORY_FIELD finding on the
    # SAME low-completeness sheet both count as ingestion.
    assert root["ingestion"]["count"] == 2
    assert root["ingestion"]["value_at_stake"] == 10000.0
    # The arithmetic mismatch and duplicate are on the well-mapped sheet.
    assert root["data_quality"]["count"] == 2
    assert root["data_quality"]["value_at_stake"] == 2100.0

    assert aggregate["duplicate_counts"]["probable_duplicate"] == 1
    assert len(aggregate["mapping_completeness_findings"]) == 1


def test_aggregate_handles_report_with_no_exceptions(db_session):
    report = Report(file_name="clean.xlsx", file_size_bytes=1, sheet_count_total=1, status="COMPLETE",
                     rows_total=0, rows_processed=0)
    db_session.add(report)
    db_session.commit()
    db_session.refresh(report)

    aggregate = exception_aggregation_service.build_aggregate(db_session, report)
    assert aggregate["total_exceptions"] == 0
    assert aggregate["total_value_at_stake"] == 0
    assert aggregate["by_category"] == []
    assert aggregate["by_sheet"] == []
    assert aggregate["root_cause_split"]["ingestion"]["count"] == 0


def test_narrative_unavailable_when_no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert exception_narrative_service.narrative_available() is False

    result = exception_narrative_service.generate_narrative({"total_exceptions": 0})
    assert result.status == "UNAVAILABLE"
    assert result.narrative is None
    assert result.error


def test_narrative_completes_on_a_well_formed_tool_response(monkeypatch):
    """Confirms the actual response-parsing path (block.type ==
    'tool_use', reading .input) against a realistic anthropic SDK
    response shape, and that a clean tool call round-trips into a
    COMPLETE result with no warning."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    class _FakeBlock:
        type = "tool_use"
        name = "triage_summary"
        input = {
            "executive_summary": "42 exceptions were found across the file.",
            "actions": [
                {"title": "Review French Sheet mapping", "rationale": "It has 42 exceptions.",
                 "category": "ingestion", "filter_check_type": "MAPPING_COMPLETENESS",
                 "filter_sheet_name": "French Sheet"},
            ],
            "ingestion_issues": ["French Sheet mapped too few fields."],
            "data_issues": [],
        }

    class _FakeResponse:
        content = [_FakeBlock()]

    class _FakeClient:
        def __init__(self, *a, **kw):
            self.messages = self

        def create(self, *a, **kw):
            return _FakeResponse()

    with patch("anthropic.Anthropic", _FakeClient):
        result = exception_narrative_service.generate_narrative({"total_exceptions": 42})

    assert result.status == "COMPLETE"
    assert result.warning is None
    assert result.narrative["executive_summary"].startswith("42 exceptions")
    assert result.model == exception_narrative_service.MODEL


def test_narrative_fails_gracefully_on_api_error(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    class _BoomClient:
        def __init__(self, *a, **kw):
            self.messages = self

        def create(self, *a, **kw):
            raise RuntimeError("simulated network timeout")

    with patch("anthropic.Anthropic", _BoomClient):
        result = exception_narrative_service.generate_narrative({"total_exceptions": 3})

    assert result.status == "FAILED"
    assert "simulated network timeout" in result.error
    assert result.narrative is None


def test_narrative_flags_unverifiable_numbers_but_still_returns():
    aggregate = {"total_exceptions": 42, "total_value_at_stake": 1234.56}
    clean_narrative = {
        "executive_summary": "There are 42 exceptions worth 1234.56 in total.",
        "actions": [], "ingestion_issues": [], "data_issues": [],
    }
    assert exception_narrative_service._find_unverifiable_numbers(clean_narrative, aggregate) == []

    hallucinated_narrative = {
        "executive_summary": "Fixing this could save approximately 87500 in exposure.",
        "actions": [], "ingestion_issues": [], "data_issues": [],
    }
    unverifiable = exception_narrative_service._find_unverifiable_numbers(hallucinated_narrative, aggregate)
    assert 87500.0 in unverifiable


def test_small_numbers_are_not_flagged_as_unverifiable():
    aggregate = {"total_exceptions": 42}
    narrative = {
        "executive_summary": "Focus on the top 3 sheets first.",
        "actions": [], "ingestion_issues": [], "data_issues": [],
    }
    assert exception_narrative_service._find_unverifiable_numbers(narrative, aggregate) == []


def _upload_and_process_minimal(client) -> str:
    import io

    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Claim Reference", "Insured Name", "Date of Loss", "Paid Amount", "Reserve Amount", "Incurred Amount"])
    ws.append(["CLM-1", "Acme Ltd", "2024-01-05", 1000, 500, 1500])
    buf = io.BytesIO()
    wb.save(buf)

    resp = client.post("/api/v1/reports/upload", files={"file": ("f.xlsx", buf.getvalue(),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    report_id = resp.json()["id"]

    sheets = client.get(f"/api/v1/reports/{report_id}/sheets").json()
    for s in sheets:
        mapping = client.get(f"/api/v1/reports/{report_id}/sheets/{s['sheet_name']}/mapping").json()
        choices = {m["field_code"]: m["source_column"] for m in mapping}
        client.post(f"/api/v1/reports/{report_id}/sheets/{s['sheet_name']}/mapping/confirm",
                    json={"mappings": choices, "actor": "pytest"})
    client.post(f"/api/v1/reports/{report_id}/process")
    return report_id


def test_summary_endpoint_returns_aggregate_with_unavailable_narrative_when_no_key(client, monkeypatch):
    """End-to-end through the real API: no ANTHROPIC_API_KEY is set in
    the test environment (matches bordereaux's own test convention), so
    this exercises the actual "degrades gracefully" path a deployment
    without a key configured would hit for every request."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    report_id = _upload_and_process_minimal(client)

    none_yet = client.get(f"/api/v1/reports/{report_id}/exceptions/summary")
    assert none_yet.status_code == 204

    created = client.post(f"/api/v1/reports/{report_id}/exceptions/summary")
    assert created.status_code == 202
    body = created.json()
    assert body["narrative_status"] == "UNAVAILABLE"
    assert body["narrative"] is None
    assert body["aggregate"] is not None
    assert "total_exceptions" in body["aggregate"]

    fetched = client.get(f"/api/v1/reports/{report_id}/exceptions/summary")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == body["id"]
    assert fetched.json()["narrative_status"] == "UNAVAILABLE"


def test_summary_endpoint_404s_for_unknown_report(client):
    resp = client.post("/api/v1/reports/does-not-exist/exceptions/summary")
    assert resp.status_code == 404
