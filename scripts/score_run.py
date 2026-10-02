"""Score a processed report against a generated answer key.

Inputs: the dump written by stress_bench.py --dump (report, summary, exceptions,
duplicates) and the generator's *.answers.json.

- Recall: a planted problem counts as found when a finding with the expected
  rule is on the planted row (duplicates: a pair of that type containing the
  planted row).
- False positives: errors and warnings on rows where nothing was planted,
  grouped by rule. Findings on a planted row that are a consequence of the
  planted problem are not counted as false positives.
- Agreement: the health view's error/warning counts against the exceptions
  list and duplicates list.

    python scripts/score_run.py DUMP.json ANSWERS.json [--out score.json]
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def score(dump: dict, key: dict) -> dict:
    exc = dump["exceptions"]["items"]
    dups = dump["duplicates"]["items"]
    hv = dump["summary"]["summary"].get("health_view") or {}
    by_row: dict[int, set[str]] = defaultdict(set)
    for e in exc:
        if e.get("sheet_name") == "Claims" and e.get("source_row_number"):
            by_row[int(e["source_row_number"])].add(e["rule"])
    pairs: dict[int, set[str]] = defaultdict(set)
    for p in dups:
        for side in ("row_a", "row_b"):
            r = (p.get(side) or {}).get("source_row_number")
            if r:
                pairs[int(r)].add(p["match_type"])

    found = Counter()
    planted = Counter()
    missed = []
    for a in key["planted"]:
        planted[a["kind"]] += 1
        hit = a["rule"] in (pairs if a["rule"].endswith("duplicate") else by_row).get(a["row"], set())
        if hit:
            found[a["kind"]] += 1
        else:
            missed.append({"kind": a["kind"], "row": a["row"], "cell": a["cell"],
                           "found_on_row": sorted(by_row.get(a["row"], set()) | pairs.get(a["row"], set()))})
    planted_rows = set(key["planted_rows"])
    fp = Counter()
    fp_examples: dict[str, list] = defaultdict(list)
    for e in exc:
        if e.get("status") not in ("FAIL", "REVIEW") or e.get("sheet_name") != "Claims":
            continue
        r = e.get("source_row_number")
        if r is not None and int(r) not in planted_rows:
            fp[e["rule"]] += 1
            if len(fp_examples[e["rule"]]) < 3:
                fp_examples[e["rule"]].append({"row": r, "message": e.get("message", "")[:160]})
    for p in dups:
        rows = {int((p.get(s) or {}).get("source_row_number") or 0) for s in ("row_a", "row_b")}
        if not rows & planted_rows:
            fp[p["match_type"]] += 1
    total_planted = sum(planted.values())
    total_found = sum(found.values())
    exc_fail = sum(1 for e in exc if e.get("status") == "FAIL")
    exc_review = sum(1 for e in exc if e.get("status") == "REVIEW")
    dup_fail = sum(1 for p in dups if p.get("status") == "FAIL")
    dup_review = sum(1 for p in dups if p.get("status") == "REVIEW")
    counts = hv.get("counts") or {}
    return {
        "file": key["file"], "claim_rows": key["claim_rows"],
        "recall": round(total_found / total_planted, 4) if total_planted else None,
        "planted": total_planted, "found": total_found,
        "by_kind": {k: {"planted": planted[k], "found": found[k]} for k in sorted(planted)},
        "missed": missed[:50],
        "false_positives": sum(fp.values()), "false_positives_by_rule": dict(fp.most_common()),
        "false_positive_examples": fp_examples,
        "agreement": {
            "report_errors": counts.get("errors"), "list_errors": exc_fail + dup_fail,
            "report_warnings": counts.get("warnings"), "list_warnings": exc_review + dup_review,
            "errors_agree": counts.get("errors") == exc_fail + dup_fail,
            "warnings_agree": counts.get("warnings") == exc_review + dup_review,
            "exceptions_complete": dump["exceptions"].get("total") == len(exc),
        },
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("dump")
    ap.add_argument("answers")
    ap.add_argument("--out")
    a = ap.parse_args()
    s = score(json.loads(Path(a.dump).read_text(encoding="utf-8")), json.loads(Path(a.answers).read_text(encoding="utf-8")))
    text = json.dumps(s, indent=1)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    print(text)
