"""Score a TrueBind run on TrueBind_Stress_Test_N_rows.xlsx against the
hand-reviewed answer key REVIEWED_Stress_Test_N_rows.xlsx (its Issues sheet).

Each reviewed issue type is mapped to the TrueBind rule(s) that should report
it; a reviewed issue is "found" when such a finding is on the same sheet and
row. Types TrueBind does not check (by design, or not built yet) are listed
separately, never counted as misses or hits.

    python scripts/score_reviewed.py DUMP.json REVIEWED.xlsx [--out score.json]
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import openpyxl

MAP: dict[str, set[str]] = {
    "Excel serial date": {"date_stored_as_text"},
    "Date stored as text or serial": {"date_stored_as_text"},
    "Closed claim still holds a reserve": {"closed_with_reserve"},
    "Total incurred does not reconcile": {"arithmetic_mismatch"},
    "Currency problem": {"invalid_currency", "currency_inconsistency", "missing_mandatory_field"},
    "Date problem": {"date_unreadable"},
    "Loss outside policy period": {"loss_outside_policy_period"},
    "Date sequence error": {"date_order"},
    "Paid exceeds incurred": {"paid_exceeds_incurred"},
    "Negative reserve": {"negative_reserve"},
    "Amount stored as text": {"amount_stored_as_text"},
    "Exact duplicate row": {"exact_duplicate"},
    "Possible duplicate under a different reference": {"probable_duplicate", "exact_duplicate"},
    "Missing claim reference": {"missing_mandatory_field"},
    "Status not recognised": {"invalid_status"},
    "Policy limit missing": {"policy_limit_missing"},
    "Amount unreadable": {"amount_unparseable", "paid_unparseable", "reserve_unparseable", "incurred_unparseable"},
    "Incurred exceeds policy limit": {"incurred_over_limit"},
    "Missing policy number": {"missing_policy_reference"},
    "Claim reference format": {"claim_ref_format"},
    "Policy number format": {"policy_ref_format"},
}


def _cell(v) -> tuple[str, int] | None:
    m = re.search(r"#'([^']+)'!([A-Z]+)(\d+)", str(v or ""))
    return (m.group(1), int(m.group(3))) if m else None


def score(dump: dict, reviewed: Path) -> dict:
    found_rules: dict[tuple[str, int], set[str]] = defaultdict(set)
    for e in dump["exceptions"]["items"]:
        if e.get("source_row_number"):
            found_rules[(e["sheet_name"], int(e["source_row_number"]))].add(e["rule"])
    for p in dump["duplicates"]["items"]:
        for side in ("row_a", "row_b"):
            r = p.get(side) or {}
            if r.get("source_row_number"):
                found_rules[(r.get("sheet_name"), int(r["source_row_number"]))].add(p["match_type"])
    ws = openpyxl.load_workbook(reviewed, read_only=True)["Issues"]
    per_type: dict[str, Counter] = defaultdict(Counter)
    not_checked: Counter = Counter()
    misses: dict[str, list] = defaultdict(list)
    for r in ws.iter_rows(min_row=4, values_only=True):
        kind, loc = r[2], _cell(r[4])
        if not kind or not loc:
            continue
        if kind not in MAP:
            not_checked[kind] += 1
            continue
        per_type[kind]["reviewed"] += 1
        if found_rules.get(loc, set()) & MAP[kind]:
            per_type[kind]["found"] += 1
        elif len(misses[kind]) < 5:
            misses[kind].append({"cell": f"{loc[0]}!{r[4]}", "value": str(r[6])[:60],
                                 "truebind_on_row": sorted(found_rules.get(loc, set()))})
    reviewed_n = sum(c["reviewed"] for c in per_type.values())
    found_n = sum(c["found"] for c in per_type.values())
    return {"reviewed_issues_checked_by_truebind": reviewed_n, "found": found_n,
            "recall": round(found_n / reviewed_n, 4) if reviewed_n else None,
            "by_type": {k: dict(v) for k, v in sorted(per_type.items())},
            "misses": dict(misses),
            "reviewed_types_truebind_does_not_check": dict(not_checked.most_common())}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("dump")
    ap.add_argument("reviewed")
    ap.add_argument("--out")
    a = ap.parse_args()
    s = score(json.loads(Path(a.dump).read_text(encoding="utf-8")), Path(a.reviewed))
    text = json.dumps(s, indent=1)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    print(text)
