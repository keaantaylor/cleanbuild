"""Golden: binder compliance end to end (upload -> map -> process -> check).

- dirty.xlsx: every planted breach found, nothing else (precision and recall
  100%), amounts exact to the penny, ambiguous dates REVIEW not guessed;
- clean.xlsx: zero findings, fully assessed;
- unmapped.xlsx: the date and currency columns cannot be mapped -> the module
  is NOT_ASSESSED with reasons, no findings;
- no binder assigned -> NOT_ASSESSED.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from golden_util import assert_amounts, findings, load_key, process, run_state, score, seed_fx
from sqlalchemy.orm import Session

HERE = Path(__file__).resolve().parent
KEY = load_key(HERE)


def _with_binder(api: Any) -> Any:
    binder = api.post("/api/v1/binders", json=KEY["binder"])
    assert binder.status_code == 201, binder.text

    def assign(rid: str) -> None:
        r = api.client.put(
            f"/api/v1/reports/{rid}/binder", json={"binder_id": binder.json()["id"]}, headers={"X-CSRF-Token": api.csrf}
        )
        assert r.status_code == 200, r.text

    return assign


def test_dirty_file_all_breaches_and_nothing_else(api: Any, db: Session) -> None:
    seed_fx(db, KEY["fx_per_eur"], dt.date(2024, 1, 1), dt.date(2025, 3, 31))
    rid = process(api, HERE / "dirty.xlsx", _with_binder(api))
    found = findings(api, rid, "binder")
    precision, recall, extra, missed = score(found, KEY["findings"])
    assert (precision, recall) == (1.0, 1.0), {"false_positives": extra, "missed": missed}
    assert_amounts(found, KEY["findings"])
    run = run_state(api, rid, "binder")
    assert run["state"] == "PARTIAL"  # JPY cannot be converted: said so, not passed
    auth = next(r for r in run["rules"] if r["code"] == "BND_OVER_AUTHORITY")
    assert auth["not_assessed"] == 1 and "JPY" in auth["reasons"][0]
    assert all(f["explanation"] and f["sheet_name"] in (None, "Claims", "Ambiguous dates") for f in found)


def test_clean_file_has_zero_findings(api: Any, db: Session) -> None:
    seed_fx(db, KEY["fx_per_eur"], dt.date(2024, 1, 1), dt.date(2025, 3, 31))
    rid = process(api, HERE / "clean.xlsx", _with_binder(api))
    assert findings(api, rid, "binder") == []
    run = run_state(api, rid, "binder")
    assert run["state"] == "ASSESSED", run
    assert all(r["not_assessed"] == 0 and r["assessed"] > 0 for r in run["rules"]), run["rules"]


def test_unmapped_inputs_are_not_assessed(api: Any, db: Session) -> None:
    seed_fx(db, KEY["fx_per_eur"], dt.date(2024, 1, 1), dt.date(2025, 3, 31))
    rid = process(api, HERE / "unmapped.xlsx", _with_binder(api))
    assert findings(api, rid, "binder") == []
    run = run_state(api, rid, "binder")
    assert run["state"] == "NOT_ASSESSED", run
    assert "Date of loss is not mapped" in run["reason"] and "Settlement currency" in run["reason"]
    assert "not assessed" in run["coverage_statement"]


def test_without_a_binder_nothing_is_assessed(api: Any) -> None:
    rid = process(api, HERE / "dirty.xlsx")
    assert findings(api, rid, "binder") == []
    run = run_state(api, rid, "binder")
    assert run["state"] == "NOT_ASSESSED" and "No binder is assigned" in run["reason"]
