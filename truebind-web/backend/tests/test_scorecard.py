"""P6 -- coverholder / TPA scorecard.

Acceptance:
- one row per sender over processed reports; reports without a sender are
  grouped as "Sender not recorded"; unprocessed reports do not count;
- metrics come from stored results only: latest and average health score,
  trend, exceptions and resubmissions per 1,000 rows, binder breaches, open
  sanctions matches, leakage exposure per currency (never summed across
  currencies, dismissed findings excluded), mapping first time right;
- a metric with nothing to compute from is null, not zero; timeliness is
  stated as not assessed;
- tenant-scoped; `since` filters by upload date.
"""

from __future__ import annotations

from typing import Any

from conftest import XLSX, Api, simple_rows, xlsx_bytes


def _run(api: Api, name: str, rows: list[list[Any]], sender: str | None) -> str:
    data = {"sender": sender} if sender else {}
    r = api.post("/api/v1/reports/upload", files={"file": (name, xlsx_bytes(rows), XLSX)}, data=data)
    assert r.status_code == 202, r.text
    rid: str = r.json()["id"]
    from conftest import run_jobs

    run_jobs()
    api.confirm_all(rid)
    assert api.post(f"/api/v1/reports/{rid}/process").status_code == 202
    run_jobs()
    return rid


def test_scorecard_per_sender(api: Api, api_b: Api) -> None:
    clean = simple_rows(4)
    dirty = [*simple_rows(3), ["LK-1", "Closed Co", "2024-01-15", "Closed", "EUR", 10, 5, 15],
                              ["LK-2", "", "2024-01-15", "Open", "GBP", 1, 1, 9]]  # fmt: skip
    _run(api, "a1.xlsx", clean, "Harbour MGA")
    _run(api, "a2.xlsx", dirty, "Harbour MGA")
    _run(api, "b1.xlsx", clean, None)
    api.upload("pending.xlsx", xlsx_bytes(clean))  # not processed: not counted
    card = api.get("/api/v1/scorecard").json()
    by = {s["sender"]: s for s in card["senders"]}
    assert set(by) == {"Harbour MGA", "Sender not recorded"}
    h = by["Harbour MGA"]
    assert h["reports"] == 2 and h["rows"] == 9 and len(h["score_trend"]) == 2
    assert h["exceptions_per_1000_rows"] is not None and h["exceptions_per_1000_rows"] > 0
    assert h["leakage_exposure"] == {"EUR": "5.00"} and h["binder_breaches"] == 0
    assert h["mapping_first_time_right_pct"] == 100.0
    assert by["Sender not recorded"]["exceptions_per_1000_rows"] == 0.0
    assert any("Timeliness" in x for x in card["not_assessed"])
    assert api_b.get("/api/v1/scorecard").json()["senders"] == []
    assert api.get("/api/v1/scorecard", params={"since": "2999-01-01"}).json()["senders"] == []
