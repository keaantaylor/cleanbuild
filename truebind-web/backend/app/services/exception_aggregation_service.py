"""Deterministic exception aggregation for the AI triage summariser (see
exception_narrative_service.py). This module does every number the
narrative will ever reference -- grouping, counting, summing monetary
value at stake, and classifying each finding as a likely ingestion/
mapping problem (fix it in the tool) vs. a likely genuine data problem
(query the cedant). It never calls out to an LLM and never derives a
number the caller didn't ask for; the narrative service passes its
output to the model as read-only, already-correct data and instructs it
never to compute anything itself (see that module's docstring for the
full "why" -- this is a financial reconciliation tool, so a model doing
its own arithmetic on claim values is exactly the class of error the
product exists to catch).

Root-cause classification: a MAPPING_COMPLETENESS finding is always
"ingestion" by definition. Any OTHER finding on a sheet that ALSO has a
MAPPING_COMPLETENESS finding is classified "ingestion" too -- a sheet
whose columns didn't map correctly makes every other finding on it
suspect (a "missing mandatory field" on a sheet that only mapped 2 of 10
columns is much more likely a mapping gap than a genuine gap in the
cedant's data). Everything else defaults to "data_quality"."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session, joinedload

from ..models.reports import ClaimRow, Report, Sheet, ValidationResult

ROOT_CAUSE_INGESTION = "ingestion"
ROOT_CAUSE_DATA_QUALITY = "data_quality"


def _row_value(row: ClaimRow) -> float:
    """Best available "amount at stake" for one claim row -- incurred if
    we have it (it's the reconciled total), else whatever of paid/reserve
    is present, else 0. Never invented, never estimated -- always a value
    already sitting on the persisted row."""
    if row.incurred_amount is not None:
        return float(row.incurred_amount)
    return float(row.paid_amount or 0) + float(row.reserve_amount or 0)


def _pct(part: float, total: float) -> float:
    return round(100.0 * part / total, 1) if total else 0.0


@dataclass
class _Bucket:
    count: int = 0
    value_at_stake: float = 0.0
    sheets: set[str] = field(default_factory=set)


def build_aggregate(db: Session, report: Report) -> dict:
    """Everything the narrative prompt needs, pre-computed. Pure
    read/aggregate over already-persisted data -- safe to call as often
    as the user clicks "regenerate" without re-running the pipeline."""
    sheets = db.query(Sheet).filter_by(report_id=report.id).all()
    sheet_names = {s.id: s.sheet_name for s in sheets}

    validation_results = (
        db.query(ValidationResult)
        .join(ClaimRow, ValidationResult.claim_row_id == ClaimRow.id)
        .options(joinedload(ValidationResult.claim_row))
        .filter(ClaimRow.report_id == report.id)
        .all()
    )

    # A sheet is "low mapping completeness" if it has its own
    # MAPPING_COMPLETENESS finding -- see module docstring.
    low_completeness_sheets: set[str] = set()
    mapping_completeness_findings: list[dict] = []
    for vr in validation_results:
        if vr.check_type != "MAPPING_COMPLETENESS":
            continue
        name = sheet_names.get(vr.claim_row.sheet_id, "unknown sheet")
        low_completeness_sheets.add(name)
        mapping_completeness_findings.append({"sheet_name": name, "message": vr.message})

    by_category: dict[str, _Bucket] = {}
    by_sheet: dict[str, _Bucket] = {}
    root_cause: dict[str, _Bucket] = {ROOT_CAUSE_INGESTION: _Bucket(), ROOT_CAUSE_DATA_QUALITY: _Bucket()}
    severity_counts: dict[str, int] = {}
    duplicate_counts = {"exact_duplicate": 0, "probable_duplicate": 0}

    total_exceptions = 0
    total_value_at_stake = 0.0
    # A claim row can carry more than one exception; value-at-stake totals
    # should count that row's value once, not once per exception on it.
    seen_row_values: dict[str, float] = {}

    for vr in validation_results:
        row = vr.claim_row
        sheet_name = sheet_names.get(row.sheet_id, "unknown sheet")
        value = _row_value(row)
        seen_row_values[row.id] = value

        total_exceptions += 1
        severity_counts[vr.severity] = severity_counts.get(vr.severity, 0) + 1

        cat = by_category.setdefault(vr.check_type, _Bucket())
        cat.count += 1
        cat.value_at_stake += value
        cat.sheets.add(sheet_name)

        sh = by_sheet.setdefault(sheet_name, _Bucket())
        sh.count += 1
        sh.value_at_stake += value

        cause = (
            ROOT_CAUSE_INGESTION
            if vr.check_type == "MAPPING_COMPLETENESS" or sheet_name in low_completeness_sheets
            else ROOT_CAUSE_DATA_QUALITY
        )
        root_cause[cause].count += 1
        root_cause[cause].value_at_stake += value
        root_cause[cause].sheets.add(sheet_name)

        if vr.check_type == "DUPLICATE":
            match_type = (vr.extra or {}).get("match_type", "probable_duplicate")
            if match_type in duplicate_counts:
                duplicate_counts[match_type] += 1

    total_value_at_stake = sum(seen_row_values.values())

    by_category_list = sorted(
        [
            {
                "check_type": code,
                "count": b.count,
                "value_at_stake": round(b.value_at_stake, 2),
                "pct_of_total_exceptions": _pct(b.count, total_exceptions),
                "sheet_count": len(b.sheets),
            }
            for code, b in by_category.items()
        ],
        key=lambda x: x["count"],
        reverse=True,
    )
    by_sheet_list = sorted(
        [
            {
                "sheet_name": name,
                "count": b.count,
                "value_at_stake": round(b.value_at_stake, 2),
                "pct_of_total_exceptions": _pct(b.count, total_exceptions),
                "low_mapping_completeness": name in low_completeness_sheets,
            }
            for name, b in by_sheet.items()
        ],
        key=lambda x: x["count"],
        reverse=True,
    )
    root_cause_out = {
        cause: {
            "count": b.count,
            "value_at_stake": round(b.value_at_stake, 2),
            "pct_of_total_exceptions": _pct(b.count, total_exceptions),
            "sheet_count": len(b.sheets),
        }
        for cause, b in root_cause.items()
    }

    return {
        "report_id": report.id,
        "file_name": report.file_name,
        "rows_total": report.rows_total,
        "rows_processed": report.rows_processed,
        "total_exceptions": total_exceptions,
        "total_value_at_stake": round(total_value_at_stake, 2),
        "arithmetic_not_evaluable_count": report.arithmetic_not_evaluable,
        "by_category": by_category_list,
        "by_sheet": by_sheet_list,
        "root_cause_split": root_cause_out,
        "severity_counts": severity_counts,
        "duplicate_counts": duplicate_counts,
        "mapping_completeness_findings": mapping_completeness_findings,
    }
