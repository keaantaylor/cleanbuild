"""Synthetic HealthReportData for timing the Health Report builder without a
database. Run directly for a timing line:

    .venv/Scripts/python tests/perf_health_report.py 10000 10 [findings per row, default 0.5]
"""

from __future__ import annotations

import datetime as dt
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.exports.data import (  # noqa: E402
    AuditEvent, ClaimInfo, ColumnInfo, FieldGap, HealthReportData, Issue, ReportMeta, SheetInfo,
)

HEADERS = ["Claim Reference", "Insured Name", "Policy Number", "Date of Loss", "Date Notified", "Claim Status",
           "Currency", "Paid to Date", "Reserve", "Fees Paid", "Total Incurred", "Broker", "Notes"]
STATES = ["MAPPED_BY_ALIAS"] * 9 + ["MAPPED_BY_AI", "MAPPED_BY_MEMORY", "UNMAPPED", "UNMAPPED"]
ISSUE_KINDS = [
    ("MANDATORY_FIELD", "missing_mandatory_field", "Required data missing", "FAIL", "CRITICAL", "CR0035M"),
    ("ARITHMETIC", "arithmetic_mismatch", "Total incurred does not reconcile", "FAIL", "HIGH", "CR0155CM"),
    ("DATE", "date_order", "Notified before the loss date", "FAIL", "MEDIUM", "CR0136CM"),
    ("CURRENCY", "currency_normalised", "Currency written non-standardly", "REVIEW", "INFO", "CR0110CM"),
    ("DUPLICATE", "exact_duplicate", "Exact duplicate", "FAIL", "HIGH", "CR0104M"),
    ("ARITHMETIC", "paid_unmapped", "Total incurred could not be reconciled", "NOT_EVALUABLE", "MEDIUM", "CR0155CM"),
]
WORD = {"FAIL": "Error", "REVIEW": "Warning", "NOT_EVALUABLE": "Couldn't check"}


def synthetic_data(rows: int = 10_000, sheets: int = 10, issue_rate: float = 0.5) -> HealthReportData:
    rnd = random.Random(7)
    per = rows // sheets
    now = dt.datetime(2026, 10, 12, 9, 30, tzinfo=dt.UTC)
    sheet_infos, columns, gaps, claims, issues = [], [], [], {}, []
    for s in range(sheets):
        name = f"Sender {s + 1:02d}"
        sheet_infos.append(SheetInfo(name, s, "CONFIRMED", None, per, per + 3, 3, HEADERS))
        for c, (h, st) in enumerate(zip(HEADERS, STATES)):
            columns.append(ColumnInfo(name, chr(65 + c), h, None if st == "UNMAPPED" else f"F{c}",
                                      None if st == "UNMAPPED" else h, st, 0.93 if st == "MAPPED_BY_AI" else 1.0,
                                      "analyst@example.com", now))
        gaps.append(FieldGap(name, "TB_POLICY_LIMIT", "Policy limit", False))
        for r in range(per):
            cid = f"c{s}-{r}"
            ccy = rnd.choice(["GBP", "GBP", "USD", "EUR"])
            paid, res = round(rnd.uniform(0, 90_000), 2), round(rnd.uniform(0, 40_000), 2)
            claims[cid] = ClaimInfo(name, r + 2, f"CLM-{s:02d}-{r:05d}", f"Insured {r}", f"POL-{r}",
                                    dt.date(2025, 1 + r % 12, 1 + r % 27), ccy, paid, res, 0.0, 0.0, paid + res)
    ids = list(claims)
    for n in range(int(rows * issue_rate)):
        cid = rnd.choice(ids)
        ct, rule, label, status, sev, fc = rnd.choice(ISSUE_KINDS)
        c = claims[cid]
        partner = rnd.choice(ids) if ct == "DUPLICATE" else None
        issues.append(Issue(
            id=f"i{n}", claim_row_id=cid, claim=c, check_type=ct, rule=rule, label=label, result=WORD[status],
            severity=sev, priority=sev.title(), field_code=fc, field_name="Field", column="Total Incurred",
            cell=f"K{c.row}", value_found=c.incurred, expected=(c.incurred or 0) + 100.0,
            actual=c.incurred, sentence=f"{label}: detail for row {c.row}.", fix="Ask the sender to correct it.",
            owner="Sender", status="Open", assignee=None, note=None, match_claim_row_id=partner,
            match_confidence=None, message=f"{label} on row {c.row}"))
    audit = [AuditEvent(i, now, "JOB_SUCCEEDED", "JOB", "system", None, {"stage": "done"}, "ab" * 32)
             for i in range(200)]
    summary = {"sheets_total": sheets, "sheets_processed": sheets, "total_claims": rows,
               "missing_mandatory_rows": 500, "arithmetic_mismatches": 300, "arithmetic_matches": rows - 400,
               "arithmetic_not_evaluable": 100, "score_reliable": True,
               "reconciliation": {"source_data_rows": rows + 3 * sheets},
               "health_view": {"counts": {"errors": 9000, "error_rows": 6000, "warnings": 2000},
                               "couldnt_check": [{"label": "Policy limit", "reason": "No column.", "rows": None,
                                                  "fix": "mapping"}],
                               "duplicates": {"exact_pairs": 400, "probable_pairs": 0}}}
    meta = ReportMeta("00000000-0000-0000-0000-000000000000", "perf_bordereau.xlsx", "xlsx", "Sample Sender",
                      None, now, "Analyst", now, now, "analyst@example.com", ["2026-09"], "0.1.0")
    return HealthReportData(meta, summary, "4", 78.0, sheet_infos, columns, gaps, issues, claims, audit)


if __name__ == "__main__":
    from app.exports.health_report import build_health_report

    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10_000
    k = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    rate = float(sys.argv[3]) if len(sys.argv) > 3 else 0.5
    data = synthetic_data(n, k, rate)
    t0 = time.perf_counter()
    body = build_health_report(data)
    print(f"{n:,} rows, {k} sheets, {len(data.issues):,} findings: {time.perf_counter() - t0:.2f}s, "
          f"{len(body) / 1e6:.1f} MB")
