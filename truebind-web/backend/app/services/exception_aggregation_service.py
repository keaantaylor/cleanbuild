"""Deterministic exception aggregation for the AI triage summariser (see
exception_narrative_service.py). Every number the narrative may mention is
computed here, in SQL, from persisted findings; the model is told never to
compute anything itself.

Money is never summed across currencies: every "value at stake" is a list
of {currency, amount} (rows without a currency are grouped as "UNKNOWN").
A row's value at stake is its total incurred if present, else paid to date
plus reserve (each only if present); it is counted once per row even if
the row has several findings.

Root cause: a MAPPING_COMPLETENESS finding is "ingestion"; any other
finding on a sheet that also has one is "ingestion" too (a sheet whose
columns did not map makes its other findings suspect); everything else is
"data_quality"."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from ..models.reports import ClaimRow, Report, Sheet, ValidationResult

ROOT_CAUSE_INGESTION = "ingestion"
ROOT_CAUSE_DATA_QUALITY = "data_quality"

_VALUE = func.coalesce(ClaimRow.incurred_amount,
                       func.coalesce(ClaimRow.paid_amount, 0.0) + func.coalesce(ClaimRow.reserve_amount, 0.0))
_CCY = func.coalesce(ClaimRow.currency, "UNKNOWN")


def _pct(part: float, total: float) -> float:
    return round(100.0 * part / total, 1) if total else 0.0


def _money(pairs) -> list[dict]:
    return [{"currency": c, "amount": round(float(a or 0.0), 2)} for c, a in sorted(pairs, key=lambda p: p[0])]


def build_aggregate(db: Session, report: Report) -> dict:
    rid = report.id
    sheet_names = dict(db.query(Sheet.id, Sheet.sheet_name).filter(Sheet.report_id == rid).all())
    base = (db.query(ValidationResult).join(ClaimRow, ValidationResult.claim_row_id == ClaimRow.id)
            .filter(ValidationResult.report_id == rid))

    low_sheet_ids = {sid for (sid,) in base.filter(ValidationResult.check_type == "MAPPING_COMPLETENESS")
                     .with_entities(ClaimRow.sheet_id).distinct()}
    mc_findings = [{"sheet_name": sheet_names.get(sid, "unknown sheet"), "message": msg}
                   for sid, msg in base.filter(ValidationResult.check_type == "MAPPING_COMPLETENESS")
                   .with_entities(ClaimRow.sheet_id, ValidationResult.message).limit(50)]

    total = base.with_entities(func.count(ValidationResult.id)).scalar() or 0
    severity_counts = dict(base.with_entities(ValidationResult.severity, func.count()).group_by(ValidationResult.severity))
    status_counts = dict(base.with_entities(ValidationResult.status, func.count()).group_by(ValidationResult.status))

    # Per-category counts and value at stake (a row counted once per category).
    cat_counts = dict(base.with_entities(ValidationResult.check_type, func.count())
                      .group_by(ValidationResult.check_type))
    cat_sheets = dict(base.with_entities(ValidationResult.check_type, func.count(func.distinct(ClaimRow.sheet_id)))
                      .group_by(ValidationResult.check_type))
    rbc = (base.with_entities(ValidationResult.check_type.label("ct"), ClaimRow.id.label("rid"), _CCY.label("ccy"),
                              _VALUE.label("v")).distinct().subquery())
    cat_money: dict[str, list] = defaultdict(list)
    for ct, ccy, amount in db.query(rbc.c.ct, rbc.c.ccy, func.sum(rbc.c.v)).group_by(rbc.c.ct, rbc.c.ccy):
        cat_money[ct].append((ccy, amount))
    by_category = sorted([{"check_type": ct, "count": n, "pct_of_total_exceptions": _pct(n, total),
                           "sheet_count": cat_sheets.get(ct, 0), "value_at_stake": _money(cat_money.get(ct, []))}
                          for ct, n in cat_counts.items()], key=lambda x: -x["count"])

    by_sheet = sorted([{"sheet_name": sheet_names.get(sid, "unknown sheet"), "count": n,
                        "pct_of_total_exceptions": _pct(n, total), "low_mapping_completeness": sid in low_sheet_ids}
                       for sid, n in base.with_entities(ClaimRow.sheet_id, func.count()).group_by(ClaimRow.sheet_id)],
                      key=lambda x: -x["count"])[:50]

    is_ingestion = case((ValidationResult.check_type == "MAPPING_COMPLETENESS", True),
                        (ClaimRow.sheet_id.in_(low_sheet_ids or {""}), True), else_=False)
    rc = dict(base.with_entities(is_ingestion, func.count()).group_by(is_ingestion))
    root_cause = {ROOT_CAUSE_INGESTION: {"count": rc.get(True, 0), "pct_of_total_exceptions": _pct(rc.get(True, 0), total)},
                  ROOT_CAUSE_DATA_QUALITY: {"count": rc.get(False, 0),
                                            "pct_of_total_exceptions": _pct(rc.get(False, 0), total)}}

    dr = base.with_entities(ClaimRow.id.label("rid"), _CCY.label("ccy"), _VALUE.label("v")).distinct().subquery()
    total_money = db.query(dr.c.ccy, func.sum(dr.c.v)).group_by(dr.c.ccy).all()
    dup_counts = dict(base.filter(ValidationResult.check_type == "DUPLICATE")
                      .with_entities(ValidationResult.rule, func.count()).group_by(ValidationResult.rule))

    return {
        "report_id": rid,
        "file_name": report.file_name,
        "rows_total": report.rows_total,
        "rows_processed": report.rows_processed,
        "total_exceptions": total,
        "status_counts": status_counts,
        "total_value_at_stake": _money(total_money),
        "arithmetic_not_evaluable_count": report.arithmetic_not_evaluable,
        "by_category": by_category,
        "by_sheet": by_sheet,
        "root_cause_split": root_cause,
        "severity_counts": severity_counts,
        "duplicate_counts": dup_counts,
        "mapping_completeness_findings": mc_findings,
        "value_definition": "total incurred if present, else paid to date + reserve; per currency; one count per row",
    }
