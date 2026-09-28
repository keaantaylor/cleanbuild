"""Golden: sanctions screening end to end (load list -> upload -> process -> check).

- dirty.xlsx against an OFSI-format list: every planted potential match
  (legal form, word order, alias, accents, one-letter typo) is raised as
  REVIEW and nothing else -- names that share only a word, and a 85% near
  miss below the 90% threshold, are not; the blank name is NOT_ASSESSED;
- clean.xlsx: zero findings, fully assessed;
- unmapped.xlsx: the insured-name column cannot be mapped -> NOT_ASSESSED;
- no list loaded -> NOT_ASSESSED.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from golden_util import findings, load_key, process, run_state, score

HERE = Path(__file__).resolve().parent
KEY = load_key(HERE)


def _load_list(api: Any) -> None:
    body = (HERE / "list_ofsi_format.csv").read_bytes()
    r = api.post(
        "/api/v1/sanctions/lists",
        files={"file": ("ConList.csv", body, "text/csv")},
        data={"name": "Fixture list (OFSI layout)"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["source"] == "OFSI" and r.json()["entry_count"] == KEY["list_entries"]


def test_dirty_file_all_potential_matches_and_nothing_else(api: Any) -> None:
    _load_list(api)
    rid = process(api, HERE / "dirty.xlsx")
    found = findings(api, rid, "sanctions")
    precision, recall, extra, missed = score(found, KEY["findings"])
    assert (precision, recall) == (1.0, 1.0), {"false_positives": extra, "missed": missed}
    assert all(f["status"] == "REVIEW" and "not a finding of fact" in f["explanation"] for f in found)
    run = run_state(api, rid, "sanctions")
    assert run["state"] == "PARTIAL", run
    assert run["rules"][0]["not_assessed"] == KEY["not_assessed_rows_dirty"]


def test_clean_file_has_zero_findings(api: Any) -> None:
    _load_list(api)
    rid = process(api, HERE / "clean.xlsx")
    assert findings(api, rid, "sanctions") == []
    run = run_state(api, rid, "sanctions")
    assert run["state"] == "ASSESSED" and run["rules"][0]["assessed"] == 11, run  # every name present


def test_unmapped_name_is_not_assessed(api: Any) -> None:
    _load_list(api)
    rid = process(api, HERE / "unmapped.xlsx")
    assert findings(api, rid, "sanctions") == []
    run = run_state(api, rid, "sanctions")
    assert run["state"] == "NOT_ASSESSED" and "Insured name is not mapped" in run["reason"]


def test_without_a_list_nothing_is_screened(api: Any) -> None:
    rid = process(api, HERE / "dirty.xlsx")
    run = run_state(api, rid, "sanctions")
    assert run["state"] == "NOT_ASSESSED" and "No sanctions list is loaded" in run["reason"]
