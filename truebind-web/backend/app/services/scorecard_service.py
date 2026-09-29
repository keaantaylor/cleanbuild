"""P6 Coverholder / TPA scorecard: how well each sender reports, over time.

One row per sender (the "sender" recorded on the report; reports without one
are grouped as "Sender not recorded"). Every metric is computed from stored,
processed reports only, states its sample size, and is None -- shown as
"not assessed" -- when there is nothing to compute it from. Nothing is
estimated.
Metrics:
- reports, rows: processed reports and claim rows in the window;
- latest and average health score, the grade of the latest report and the
  last six scores oldest first (trend);
- exceptions per 1,000 rows: rows missing mandatory fields plus arithmetic
  mismatches, per thousand rows;
- exact resubmissions per 1,000 rows;
- binder breaches, sanctions potential matches still open, and leakage
  exposure (FAIL amounts) per currency -- never summed across currencies;
- mapping first time right: share of reports whose mapping needed no manual
  change (every confirmed field mapped by alias).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models.modules import Finding
from ..models.reports import Mapping, Report

UNKNOWN = "Sender not recorded"


def _per_thousand(n: int, rows: int) -> float | None:
    return round(1000 * n / rows, 2) if rows else None


def build(db: Session, tenant_id: str, since: datetime | None) -> list[dict[str, Any]]:
    q = db.query(Report).filter(Report.tenant_id == tenant_id, Report.status == "COMPLETE")
    if since is not None:
        q = q.filter(Report.created_at >= since)
    groups: dict[str, list[Report]] = defaultdict(list)
    for r in q.order_by(Report.created_at):
        groups[(r.sender or "").strip() or UNKNOWN].append(r)
    ids = [r.id for reps in groups.values() for r in reps]
    if not ids:
        return []

    fcounts: dict[tuple[str, str, str, str], int] = defaultdict(int)
    exposure: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for rid, module, status, disposition, amount, ccy in db.query(
        Finding.report_id, Finding.module, Finding.status, Finding.disposition, Finding.amount, Finding.currency
    ).filter(Finding.tenant_id == tenant_id, Finding.report_id.in_(ids)):
        fcounts[(rid, module, status, disposition)] += 1
        if module == "leakage" and status == "FAIL" and disposition != "DISMISSED" and amount is not None and ccy:
            exposure[rid][ccy] += amount
    manual = dict(
        db.query(Mapping.report_id, func.count(Mapping.id))
        .filter(
            Mapping.tenant_id == tenant_id,
            Mapping.report_id.in_(ids),
            Mapping.mapping_state == "MANUAL",
        )
        .group_by(Mapping.report_id)
        .all()
    )

    out = []
    for sender, reps in groups.items():
        rows = sum(r.rows_processed or 0 for r in reps)
        summaries = [r.summary or {} for r in reps]
        scores = [r.score for r in reps if r.score is not None]
        exc = sum(
            int(s.get("missing_mandatory_rows") or 0) + int(s.get("arithmetic_mismatches") or 0) for s in summaries
        )
        dups = sum(int(s.get("exact_duplicates") or 0) for s in summaries)

        rep_ids = {r.id for r in reps}
        binder_breaches = sum(
            n for (rid, m, st, _d), n in fcounts.items() if rid in rep_ids and m == "binder" and st == "FAIL"
        )
        sanctions_open = sum(
            n
            for (rid, m, st, d), n in fcounts.items()
            if rid in rep_ids and m == "sanctions" and st == "REVIEW" and d == "OPEN"
        )

        exp: dict[str, Decimal] = defaultdict(Decimal)
        for r in reps:
            for ccy, amt in exposure.get(r.id, {}).items():
                exp[ccy] += amt
        latest = reps[-1]
        out.append(
            {
                "sender": sender,
                "reports": len(reps),
                "rows": rows,
                "first_report_at": reps[0].created_at,
                "latest_report_at": latest.created_at,
                "latest_grade": latest.grade,
                "latest_score": round(latest.score, 1) if latest.score is not None else None,
                "average_score": round(sum(scores) / len(scores), 1) if scores else None,
                "score_trend": [round(s, 1) for s in scores[-6:]],
                "exceptions_per_1000_rows": _per_thousand(exc, rows),
                "resubmissions_per_1000_rows": _per_thousand(dups, rows),
                "binder_breaches": binder_breaches,
                "sanctions_open_matches": sanctions_open,
                "leakage_exposure": {c: str(v.quantize(Decimal("0.01"))) for c, v in sorted(exp.items())},
                "mapping_first_time_right_pct": round(
                    100 * sum(1 for r in reps if not manual.get(r.id)) / len(reps), 1
                ),
            }
        )
    out.sort(key=lambda x: (x["latest_score"] is None, x["latest_score"] or 0, x["sender"]))
    return out
