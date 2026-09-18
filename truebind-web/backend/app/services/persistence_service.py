"""Bridges a pipeline run into the database. This is where the web app's
persistence model genuinely differs from the Streamlit build: the
Streamlit app kept full canonical rows in-memory per session and only
persisted the health-report summary + exceptions/leakage/audit. Here,
every claim row is persisted (claim_rows + validation_results) so the
Exceptions/Duplicates screens can query results independently of the
upload session that produced them, per the redesign doc's schema."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models._util import new_uuid
from ..models.alerts import Alert
from ..models.reports import ClaimRow, ExcludedRow, Mapping, Report, Sheet, ValidationResult
from . import audit_service
from .pipeline_service import FIELDS, FIELDS_BY_CODE, field_suggestions_by_code

_FIELD_TO_CLAIMROW_COL = {
    "CR0104M": "claim_reference",
    "CR0105CM": "claim_status",
    "CR0119CM": "date_of_loss",
    "CR0136CM": "date_notified",
    "CR0035M": "insured_name",
    "CR0029M": "policy_reference",
    "CR0126CM": "paid_amount",
    "CR0130CM": "reserve_amount",
    "CR0155CM": "incurred_amount",
    "CR0110CM": "currency",
}


def create_report_from_upload(db: Session, file_name: str, file_size_bytes: int, sheets, proposals) -> Report:
    report = Report(
        file_name=file_name,
        file_size_bytes=file_size_bytes,
        sheet_count_total=len(sheets),
        status="PENDING_MAPPING",
    )
    db.add(report)
    db.flush()

    proposal_by_sheet = {p.sheet.sheet_name: p for p in proposals}

    for i, s in enumerate(sheets):
        sheet_row = Sheet(
            report_id=report.id,
            sheet_name=s.sheet_name,
            sheet_index=i,
            header_row_index=s.header_row_index if not s.skipped else None,
            row_count=len(s.raw) if not s.skipped else 0,
            status="SKIPPED" if s.skipped else "PENDING_CONFIRMATION",
            skip_reason=s.skip_reason,
        )
        db.add(sheet_row)
        db.flush()

        for er in s.excluded_rows:
            db.add(ExcludedRow(
                report_id=report.id, sheet_name=er.sheet_name, row_number=er.row_number,
                reason=er.reason, detail=er.detail, values=er.values,
            ))

        proposal = proposal_by_sheet.get(s.sheet_name)
        if proposal is None:
            continue
        by_field = field_suggestions_by_code(proposal.mapping)
        for code, suggestion in by_field.items():
            field_name = FIELDS_BY_CODE[code].name
            if suggestion is None or suggestion.method == "unmapped":
                state, source_col, confidence = "UNMAPPED", None, None
            else:
                state = "MAPPED_BY_ALIAS" if suggestion.method == "alias" else "MAPPED_BY_AI"
                source_col, confidence = suggestion.source_column, suggestion.confidence
            db.add(Mapping(
                report_id=report.id,
                sheet_id=sheet_row.id,
                field_code=code,
                field_name=field_name,
                source_column=source_col,
                mapping_state=state,
                confidence_score=confidence,
            ))

    db.commit()
    db.refresh(report)
    return report


def confirm_sheet_mapping(
    db: Session, report: Report, sheet: Sheet, field_choices: dict[str, str | None], actor: str,
) -> None:
    """field_choices: {field_code: source_column_or_None}. A choice that
    matches the existing suggestion keeps its alias/ai provenance; any
    other non-null choice is recorded as a human override (fix spec
    3.3's tri-state + "manual" -- see mapping.derive_field_state upstream)."""
    existing = {m.field_code: m for m in db.query(Mapping).filter_by(sheet_id=sheet.id).all()}
    now = datetime.now(timezone.utc)

    for code, source_col in field_choices.items():
        row = existing.get(code)
        if row is None:
            continue
        before = {"field_code": code, "source_column": row.source_column, "mapping_state": row.mapping_state}

        if source_col is None:
            row.mapping_state = "UNMAPPED"
            row.source_column = None
        elif row.source_column == source_col and row.mapping_state in ("MAPPED_BY_ALIAS", "MAPPED_BY_AI"):
            pass  # confirmed as suggested, provenance unchanged
        else:
            row.mapping_state = "MANUAL"
            row.source_column = source_col

        row.confirmed_at = now
        row.confirmed_by = actor

        after = {"field_code": code, "source_column": row.source_column, "mapping_state": row.mapping_state}
        action = "MAPPING_CONFIRMED" if before == after or before["source_column"] is None else "MAPPING_OVERRIDDEN"
        audit_service.log_action(db, report.id, action, "MAPPING", row.id, before=before, after=after, actor=actor)

    sheet.status = "CONFIRMED"
    db.commit()


def confirmed_mapping_for_sheet(db: Session, sheet: Sheet) -> dict[str, str]:
    """{source_column: field_code} -- the shape bordereaux.ingest.apply_mapping expects."""
    rows = db.query(Mapping).filter_by(sheet_id=sheet.id).all()
    return {m.source_column: m.field_code for m in rows if m.source_column and m.mapping_state != "UNMAPPED"}


def _severity_for_rule(rule: str) -> str:
    if rule in ("missing_mandatory_field",):
        return "CRITICAL"
    if rule in ("arithmetic_mismatch", "invalid_currency", "currency_inconsistency"):
        return "HIGH"
    if rule in ("date_order", "date_in_future", "invalid_status"):
        return "MEDIUM"
    return "INFO"


# Not-evaluable is deliberately never CRITICAL/HIGH: it means "we don't have
# enough information to check this", not "this is wrong" -- see
# bordereaux.validation._check_arithmetic's not_evaluable_detail, which is
# kept separate from `exceptions` for the same reason (doesn't penalize the
# composite score the way a real exception does).
_NOT_EVALUABLE_SEVERITY = "MEDIUM"


def _persist_sheet_mapping_completeness(
    db: Session, canonical: pd.DataFrame, coverage, claim_row_ids: list[str], report_id: str,
) -> None:
    """Section 5: a sheet whose columns mostly failed to map (an
    unrecognized layout, a language the alias dictionary doesn't cover,
    or -- see bordereaux.ingest's header fallback -- any sheet Truebind
    processed with much lower mapping confidence than the rest of the
    file) must be a first-class, visible exception, not an inference a
    reviewer has to make from an inflated not-evaluable count. One
    exception per affected sheet (not one per row -- a per-row entry
    would just flood the Exceptions table with identical messages),
    attached to that sheet's first row so it's findable there, plus one
    Alert so it also surfaces in the To-do inbox like every other
    report-level issue."""
    sheet_field_state = coverage.sheet_field_state
    if not sheet_field_state or canonical.empty:
        return

    total_fields = len(FIELDS)
    mapped_counts = {
        sheet_name: sum(1 for v in state.values() if v != "unmapped")
        for sheet_name, state in sheet_field_state.items()
    }
    if not mapped_counts:
        return
    best = max(mapped_counts.values())

    for sheet_name, mapped in mapped_counts.items():
        poorly_mapped = mapped == 0 or (best > 0 and mapped < best / 2)
        if not poorly_mapped:
            continue

        severity = "CRITICAL" if mapped == 0 else "HIGH"
        message = (
            f"Sheet {sheet_name!r}: {mapped} of {total_fields} canonical fields mapped — "
            + ("no columns on this sheet matched a known field; needs manual review."
               if mapped == 0 else "well below the rest of this file; needs manual review.")
        )
        # Section 7: the Alert fires unconditionally -- it's report-level,
        # not tied to any one row, so a poorly-mapped sheet is never
        # dropped from the To-do inbox just because there happens to be no
        # row to also anchor a per-row exception to (below).
        db.add(Alert(report_id=report_id, severity=severity, source="MAPPING_COMPLETENESS", message=message))

        sheet_rows = canonical.index[canonical["_source_sheet"] == sheet_name]
        if len(sheet_rows) == 0:
            continue  # nothing to attach a row-level exception to; the Alert above still surfaces this sheet
        first_pos = canonical.index.get_loc(sheet_rows[0])
        if first_pos >= len(claim_row_ids):
            # Same invariant as the exceptions/not-evaluable/duplicates
            # loops above: first_pos is a position in the same canonical
            # DataFrame claim_row_ids was built from, so this should never
            # happen. Raise rather than silently drop the exception.
            raise RuntimeError(
                f"sheet {sheet_name!r} row_index {first_pos} has no matching claim row "
                f"(only {len(claim_row_ids)} persisted) -- data integrity bug, not a normal input case"
            )

        db.add(ValidationResult(
            claim_row_id=claim_row_ids[first_pos],
            check_type="MAPPING_COMPLETENESS",
            status="FAIL",
            severity=severity,
            message=message,
            extra={"sheet_name": sheet_name, "mapped": mapped, "total_fields": total_fields},
        ))


def persist_pipeline_result(
    db: Session, report: Report, sheets, workbook_result, sheet_id_by_name: dict[str, str],
) -> None:
    canonical = workbook_result.canonical
    health = workbook_result.health
    coverage = workbook_result.coverage

    local_row_index = (
        canonical.groupby(canonical["_source_sheet"]).cumcount()
        if not canonical.empty else pd.Series(dtype="int64")
    )

    # Section 6: this used to be db.add() + db.flush() per row, one round
    # trip per claim -- fine at the small fixture sizes the original test
    # suite used, but the dominant cost by far at realistic volume
    # (profiling an 8,000-row workbook showed this loop alone accounting
    # for the majority of a ~10s request). The id has to be known before
    # the row is inserted anyway (it's a client-side default, not a
    # database identity/sequence -- see models._util.uuid_pk), so
    # generating it up front and inserting every row in one flush is a
    # correctness-neutral change, not a shortcut: the same ids land in
    # the same columns, just via one round trip instead of N.
    claim_row_ids: list[str] = []
    claim_rows: list[ClaimRow] = []
    for pos, (idx, row) in enumerate(canonical.iterrows()):
        sheet_name = row["_source_sheet"]
        claim_row = ClaimRow(
            id=new_uuid(),
            report_id=report.id,
            sheet_id=sheet_id_by_name.get(sheet_name),
            row_index=int(local_row_index.iloc[pos]) if len(local_row_index) else pos,
            **{
                col: (row[code].date() if col in ("date_of_loss", "date_notified") and pd.notna(row[code])
                      else (row[code] if pd.notna(row[code]) else None))
                for code, col in _FIELD_TO_CLAIMROW_COL.items()
            },
        )
        claim_rows.append(claim_row)
        claim_row_ids.append(claim_row.id)
    db.add_all(claim_rows)
    db.flush()

    exceptions = workbook_result.validation_result.exceptions
    if not exceptions.empty:
        for _, exc in exceptions.iterrows():
            row_pos = int(exc["row_index"])
            if row_pos >= len(claim_row_ids):
                # Section 7: row_pos is a position in the same canonical
                # DataFrame claim_row_ids was built from (see
                # run_workbook_pipeline's `ignore_index=True` concat), so
                # this should never happen -- but silently skipping it
                # here would understate the persisted exception count
                # against bordereaux's own health.missing_mandatory_rows
                # with nothing to say why. Raising surfaces it as a
                # visible FAILED report instead (see routes/mapping.py's
                # _run_pipeline_job), which is strictly better than a
                # report that looks clean but is quietly wrong.
                raise RuntimeError(
                    f"exception row_index {row_pos} has no matching claim row "
                    f"(only {len(claim_row_ids)} persisted) -- data integrity bug, not a normal input case"
                )
            db.add(ValidationResult(
                claim_row_id=claim_row_ids[row_pos],
                check_type="ARITHMETIC" if exc["rule"] == "arithmetic_mismatch"
                    else "MANDATORY_FIELD" if exc["rule"] == "missing_mandatory_field" else "MAPPING_COMPLETENESS",
                status="FAIL",
                severity=_severity_for_rule(exc["rule"]),
                message=exc["detail"],
                extra={"rule": exc["rule"]},
            ))

    not_evaluable = workbook_result.validation_result.not_evaluable_detail
    if not not_evaluable.empty:
        for _, ne in not_evaluable.iterrows():
            row_pos = int(ne["row_index"])
            if row_pos >= len(claim_row_ids):
                raise RuntimeError(
                    f"not-evaluable row_index {row_pos} has no matching claim row "
                    f"(only {len(claim_row_ids)} persisted) -- data integrity bug, not a normal input case"
                )
            db.add(ValidationResult(
                claim_row_id=claim_row_ids[row_pos],
                check_type="ARITHMETIC",
                status="NOT_EVALUABLE",
                severity=_NOT_EVALUABLE_SEVERITY,
                message=ne["detail"],
                extra={"rule": ne["reason"]},
            ))

    duplicates = workbook_result.duplicates
    if not duplicates.empty:
        for _, dup in duplicates.iterrows():
            a, b = int(dup["row_index_a"]), int(dup["row_index_b"])
            if a >= len(claim_row_ids) or b >= len(claim_row_ids):
                raise RuntimeError(
                    f"duplicate pair references row_index {a}/{b} with no matching claim row "
                    f"(only {len(claim_row_ids)} persisted) -- data integrity bug, not a normal input case"
                )
            severity = "HIGH" if dup["match_type"] == "exact_duplicate" else "MEDIUM"
            db.add(ValidationResult(
                claim_row_id=claim_row_ids[a],
                check_type="DUPLICATE",
                status="FAIL",
                severity=severity,
                message=dup["detail"],
                extra={"match_type": dup["match_type"], "match_claim_row_id": claim_row_ids[b]},
            ))

    _persist_sheet_mapping_completeness(db, canonical, coverage, claim_row_ids, report.id)

    report.rows_processed = len(canonical)
    report.rows_total = coverage.rows_total
    report.coverage_pct = (100.0 * coverage.rows_assessed / coverage.rows_total) if coverage.rows_total else 0.0
    report.grade = str(health.grade)
    report.score = health.composite_score
    report.arithmetic_not_evaluable = health.arithmetic_not_evaluable
    report.status = "COMPLETE"

    if not coverage.fully_covered:
        skipped_note = ""
        if coverage.skipped_sheets:
            named = "; ".join(f"{name!r} ({reason})" for name, reason in coverage.skipped_sheets)
            skipped_note = f" Skipped: {named}."
        db.add(Alert(report_id=report.id, severity="HIGH", source="COVERAGE",
                      message=f"Assessed {coverage.rows_assessed} of {coverage.rows_total} rows across "
                              f"{coverage.sheets_processed} of {coverage.sheets_total} sheets.{skipped_note}"))
    if health.missing_mandatory_rows:
        db.add(Alert(report_id=report.id, severity="CRITICAL", source="MANDATORY_FAIL",
                      message=f"{health.missing_mandatory_rows} row(s) missing a mandatory field."))
    if health.arithmetic_not_evaluable:
        db.add(Alert(report_id=report.id, severity="MEDIUM", source="NOT_EVALUABLE",
                      message=f"{health.arithmetic_not_evaluable} row(s) not evaluable for arithmetic reconciliation."))
    if health.exact_duplicates or health.probable_duplicates:
        db.add(Alert(report_id=report.id, severity="MEDIUM", source="DUPLICATE",
                      message=f"{health.exact_duplicates} certain + {health.probable_duplicates} probable duplicate(s)."))

    db.commit()


def list_excluded_rows(db: Session, report_id: str) -> list[ExcludedRow]:
    return (
        db.query(ExcludedRow)
        .filter(ExcludedRow.report_id == report_id)
        .order_by(ExcludedRow.sheet_name, ExcludedRow.row_number)
        .all()
    )


def compute_report_summary(db: Session, report: Report) -> dict:
    """Rebuilds the dashboard's headline numbers from already-persisted
    rows -- no re-read of the source file needed, since claim_rows,
    mappings and validation_results already carry everything the health
    report screen shows."""
    sheets = db.query(Sheet).filter_by(report_id=report.id).all()
    sheets_processed = sum(1 for s in sheets if s.status == "CONFIRMED")
    skipped_sheets = [{"sheet_name": s.sheet_name, "reason": s.skip_reason or "skipped"}
                       for s in sheets if s.status == "SKIPPED"]

    mandatory_vr = (
        db.query(ValidationResult)
        .join(ClaimRow, ValidationResult.claim_row_id == ClaimRow.id)
        .filter(ClaimRow.report_id == report.id, ValidationResult.check_type == "MANDATORY_FIELD")
        .all()
    )
    missing_mandatory_rows = len({vr.claim_row_id for vr in mandatory_vr})

    arithmetic_mismatches = (
        db.query(ValidationResult)
        .join(ClaimRow, ValidationResult.claim_row_id == ClaimRow.id)
        .filter(ClaimRow.report_id == report.id, ValidationResult.check_type == "ARITHMETIC",
                ValidationResult.status != "NOT_EVALUABLE")
        .count()
    )

    duplicate_vr = (
        db.query(ValidationResult)
        .join(ClaimRow, ValidationResult.claim_row_id == ClaimRow.id)
        .filter(ClaimRow.report_id == report.id, ValidationResult.check_type == "DUPLICATE")
        .all()
    )
    exact_duplicates = sum(1 for vr in duplicate_vr if (vr.extra or {}).get("match_type") == "exact_duplicate")
    probable_duplicates = len(duplicate_vr) - exact_duplicates

    not_evaluable_vr = (
        db.query(ValidationResult)
        .join(ClaimRow, ValidationResult.claim_row_id == ClaimRow.id)
        .filter(ClaimRow.report_id == report.id, ValidationResult.status == "NOT_EVALUABLE")
        .all()
    )
    not_evaluable_by_reason: dict[str, int] = {}
    for vr in not_evaluable_vr:
        reason = (vr.extra or {}).get("rule", "unknown")
        not_evaluable_by_reason[reason] = not_evaluable_by_reason.get(reason, 0) + 1

    excluded_rows = list_excluded_rows(db, report.id)
    excluded_row_counts: dict[str, int] = {}
    for er in excluded_rows:
        excluded_row_counts[er.reason] = excluded_row_counts.get(er.reason, 0) + 1

    sheet_row_counts = {s.id: s.row_count for s in sheets if s.status == "CONFIRMED"}
    mapping_rows = db.query(Mapping).filter(Mapping.report_id == report.id, Mapping.sheet_id.in_(sheet_row_counts)).all()

    field_completeness = []
    for f in FIELDS:
        col = _FIELD_TO_CLAIMROW_COL[f.code]
        mapped_sheet_ids = [m.sheet_id for m in mapping_rows if m.field_code == f.code and m.mapping_state != "UNMAPPED"]
        denominator = sum(sheet_row_counts.get(sid, 0) for sid in mapped_sheet_ids)
        if denominator == 0:
            field_completeness.append({"field_code": f.code, "field_name": f.name, "present": 0,
                                        "denominator": 0, "never_mapped": True})
            continue
        present = (
            db.query(func.count(getattr(ClaimRow, col)))
            .filter(ClaimRow.report_id == report.id, ClaimRow.sheet_id.in_(mapped_sheet_ids),
                     getattr(ClaimRow, col).isnot(None))
            .scalar()
        ) or 0
        field_completeness.append({"field_code": f.code, "field_name": f.name, "present": present,
                                    "denominator": denominator, "never_mapped": False})

    sheet_names = {s.id: s.sheet_name for s in sheets}
    seen_rows_per_sheet: dict[str, set] = {}
    for vr in mandatory_vr:
        sid = vr.claim_row.sheet_id
        name = sheet_names.get(sid, "unknown")
        seen_rows_per_sheet.setdefault(name, set()).add(vr.claim_row_id)
    missing_mandatory_by_sheet = {name: len(rows) for name, rows in seen_rows_per_sheet.items()}

    return {
        "sheets_total": len(sheets),
        "sheets_processed": sheets_processed,
        "missing_mandatory_rows": missing_mandatory_rows,
        "arithmetic_mismatches": arithmetic_mismatches,
        "arithmetic_not_evaluable": report.arithmetic_not_evaluable,
        "exact_duplicates": exact_duplicates,
        "probable_duplicates": probable_duplicates,
        "field_completeness": field_completeness,
        "missing_mandatory_by_sheet": missing_mandatory_by_sheet,
        "not_evaluable_by_reason": not_evaluable_by_reason,
        "excluded_row_counts": excluded_row_counts,
        "skipped_sheets": skipped_sheets,
    }
