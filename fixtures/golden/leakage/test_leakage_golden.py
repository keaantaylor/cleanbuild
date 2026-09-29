"""Golden: leakage & overpayment end to end (upload -> map -> process -> check).

- dirty.xlsx: every planted leak found and nothing else (precision and recall
  100%), exposure amounts exact, a row without a currency says so;
- clean.xlsx: zero findings, fully assessed;
- unmapped.xlsx: status, period and reserve cannot be mapped -> NOT_ASSESSED.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from golden_util import assert_amounts, findings, load_key, process, run_state, score

HERE = Path(__file__).resolve().parent
KEY = load_key(HERE)


def test_dirty_file_all_leaks_and_nothing_else(api: Any) -> None:
    rid = process(api, HERE / "dirty.xlsx")
    found = findings(api, rid, "leakage")
    precision, recall, extra, missed = score(found, KEY["findings"])
    assert (precision, recall) == (1.0, 1.0), {"false_positives": extra, "missed": missed}
    assert_amounts(found, KEY["findings"])
    run = run_state(api, rid, "leakage")
    assert run["state"] == "ASSESSED", run
    assert run["exposure"] == {"GBP": "3700.00"}, run["exposure"]  # breaches only, per currency
    assert run["unpriced_findings"] == 1  # the negative reserve with no currency is counted, not summed
    no_ccy = next(f for f in found if f["currency"] is None)
    assert "currency not stated" in no_ccy["explanation"]


def test_clean_file_has_zero_findings(api: Any) -> None:
    rid = process(api, HERE / "clean.xlsx")
    assert findings(api, rid, "leakage") == []
    run = run_state(api, rid, "leakage")
    assert run["state"] == "ASSESSED", run
    assert all(r["not_assessed"] == 0 and r["assessed"] > 0 for r in run["rules"]), run["rules"]


def test_unmapped_inputs_are_not_assessed(api: Any) -> None:
    rid = process(api, HERE / "unmapped.xlsx")
    assert findings(api, rid, "leakage") == []
    run = run_state(api, rid, "leakage")
    assert run["state"] == "NOT_ASSESSED", run
    assert "Reporting period" in run["reason"] and "Indemnity reserve" in run["reason"]
