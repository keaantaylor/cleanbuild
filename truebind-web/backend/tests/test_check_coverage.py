"""P1.7 -- a check that was not run is reported as NOT ASSESSED, never as 0.

The engine's probable-duplicate check has a work budget (see
bordereaux.dedupe.MAX_PROBABLE_CANDIDATE_PAIRS). When a file exceeds it,
the stored summary says so with the reason, the score is provisional, and
the coverage statement names the check -- the report never shows a clean
"0 probable duplicates" for a check that did not run.
"""

from __future__ import annotations

from typing import Any

import pytest
from conftest import Api, xlsx_bytes

from bordereaux import dedupe

HEADER = ["Claim Reference", "Insured Name", "Date of Loss", "Claim Status", "Currency",
          "Paid to Date", "Outstanding Reserve", "Total Incurred"]  # fmt: skip


def _rows() -> list[list[Any]]:
    return [HEADER] + [
        [f"P-{i}", "Fairwind Shipping Group", f"2024-01-{10 + i:02d}", "Open", "EUR", 100, 50, 150] for i in range(3)
    ]


def test_probable_check_over_budget_is_not_assessed(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dedupe, "MAX_PROBABLE_CANDIDATE_PAIRS", 1)
    rid, _ = api.full_run("budget.xlsx", xlsx_bytes(_rows()))
    s = api.get(f"/api/v1/reports/{rid}/summary").json()["summary"]
    [check] = s["not_assessed_checks"]
    assert check["check"] == "probable_duplicates"
    assert check["label"] == "Probable-duplicate check"
    assert "exceed the limit of 1" in check["reason"]
    assert s["probable_duplicates"] is None, "a check that did not run has no count"
    assert s["score_reliable"] is False
    assert "Not assessed: probable-duplicate check" in s["coverage_statement"]
    findings = api.get("/api/v1/overview").json()["findings"]
    assert findings["reports_with_checks_not_assessed"] == 1


def test_probable_check_within_budget_is_assessed(api: Api) -> None:
    rid, _ = api.full_run("fine.xlsx", xlsx_bytes(_rows()))
    s = api.get(f"/api/v1/reports/{rid}/summary").json()["summary"]
    assert s["not_assessed_checks"] == []
    assert s["probable_duplicates"] == 3  # 10/11, 10/12 and 11/12 January: all within 3 days
    assert "Assessed 3 of 3 total rows" in s["coverage_statement"]
