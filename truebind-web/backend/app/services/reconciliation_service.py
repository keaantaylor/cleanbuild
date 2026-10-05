"""Reconciliation that needs the database: record-level matching with the
previous submission from the same sender, and the re-check after corrections.

Deterministic only. The previous report is chosen by code (same tenant, same
sender, processed, received earlier); nothing comes from the request.
"""

from __future__ import annotations

import dataclasses
import logging
import os
import re
import tempfile
from pathlib import Path

import pandas as pd
from bordereaux import reconcile, validation
from bordereaux import schema as S
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models._util import utcnow
from ..models.corrections import Correction, WorkbookVersion
from ..models.reports import ClaimRow, Report, Sheet, ValidationResult
from . import audit_service, issues, persistence_service, pipeline_service

log = logging.getLogger("truebind.reconciliation")


def previous_report(db: Session, report: Report) -> Report | None:
    """The latest earlier processed report from the same sender. None when the
    sender is not recorded: matching another coverholder's file by claim
    reference would compare unrelated claims."""
    if not (report.sender or "").strip():
        return None
    return (db.query(Report)
            .filter(Report.tenant_id == report.tenant_id, Report.id != report.id, Report.status == "COMPLETE",
                    func.lower(Report.sender) == report.sender.strip().lower(),
                    Report.created_at <= report.created_at)
            .order_by(Report.created_at.desc()).first())


def previous_frame(db: Session, prev: Report) -> pd.DataFrame:
    rows = (db.query(ClaimRow.claim_reference, ClaimRow.paid_amount, ClaimRow.currency, ClaimRow.source_row_number,
                     Sheet.sheet_name)
            .join(Sheet, Sheet.id == ClaimRow.sheet_id)
            .filter(ClaimRow.report_id == prev.id, ClaimRow.tenant_id == prev.tenant_id)
            .order_by(Sheet.sheet_name, ClaimRow.row_index).all())
    return pd.DataFrame([{S.CLAIM_REF_CODE: r[0], S.PAID_TD_CODE: float(r[1]) if r[1] is not None else None,
                          S.CURRENCY_CODE: r[2], "_source_row": r[3], S.SOURCE_SHEET_CODE: r[4]} for r in rows])


def with_previous_submission(db: Session, report: Report, result):
    """The pipeline result with paid_decreased / rollforward_break findings
    added from the previous submission, when there is one."""
    prev = previous_report(db, report)
    if prev is None:
        return result
    found = reconcile.against_previous(result.canonical.reset_index(drop=True), previous_frame(db, prev),
                                       f"previous submission '{prev.file_name}'")
    if found.empty:
        return result
    return dataclasses.replace(result, validation_result=validation.add_exceptions(result.validation_result, [found]))


_ROW = re.compile(r"[A-Z]+(\d+)$")


def _row_of(cell: str | None) -> int | None:
    m = _ROW.search(cell or "")
    return int(m.group(1)) if m else None


def _plain(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    return v.item() if hasattr(v, "item") else v


def _finding_keys(db: Session, report: Report, result) -> dict[tuple, dict]:
    """(rule, sheet, cell) -> evidence, for every row finding in a pipeline result."""
    locator = persistence_service._cell_locator(db, report)
    canon = result.canonical.reset_index(drop=True)
    sheets = canon[S.SOURCE_SHEET_CODE].tolist() if S.SOURCE_SHEET_CODE in canon.columns else []
    src = canon["_source_row"].tolist() if "_source_row" in canon.columns else []
    out: dict[tuple, dict] = {}
    for rec in result.validation_result.exceptions.to_dict("records"):
        pos = int(rec["row_index"])
        if pos >= len(sheets):
            continue
        at = rec.get("at_row")
        row = at if at is not None and not pd.isna(at) else src[pos]
        cell, _ = locator.locate(sheets[pos], rec.get("field_code"), row)
        out[(rec["rule"], sheets[pos], cell)] = {"expected": _plain(rec.get("expected")),
                                                 "actual": _plain(rec.get("actual")), "detail": str(rec["detail"])}
    return out


RECHECK_INLINE_MAX_ROWS = int(os.environ.get("RECHECK_INLINE_MAX_ROWS", "2000"))


def run_recheck(db: Session, report: Report, actor: str, version_id: str | None = None) -> dict:
    """The re-check itself (inline, or inside a RECHECK job): against a stored
    corrected version when one is named, else an in-memory corrected copy."""
    from . import corrections_service

    if version_id:
        v = db.query(WorkbookVersion).filter(WorkbookVersion.id == version_id,
                                             WorkbookVersion.report_id == report.id).first()
        if v is None:
            raise ValueError("version not found")
        return recheck_after_corrections(db, report, corrections_service.version_bytes(db, report, v), v, actor)
    body, approved = corrections_service.corrected_bytes(db, report)
    return recheck_after_corrections(db, report, body, None, actor, [c.id for c in approved])


def schedule_recheck(db: Session, report: Report, actor: str, actor_user_id: str | None,
                     version_id: str | None = None) -> dict:
    """Re-check after corrections. Small workbooks inline; large ones as a
    RECHECK job, never inside the HTTP request. A re-check already queued
    for the report is reused rather than duplicated."""
    from . import job_service

    if (report.rows_processed or 0) <= RECHECK_INLINE_MAX_ROWS:
        try:
            return run_recheck(db, report, actor, version_id)
        except Exception as exc:  # noqa: BLE001 -- reported to the caller, never swallowed
            log.exception("re-check after corrections failed for report %s", report.id)
            return {"status": "not_run", "reason": f"The re-check could not run ({type(exc).__name__}). "
                                                   "Treat the corrections as unverified."}
    active = job_service.active_job(db, report.id)
    if active is not None:
        return {"status": "queued", "job_id": active.id, "reason": "A job for this report is already queued or running."}
    job = job_service.enqueue(db, report, "RECHECK", actor, actor_user_id,
                              params={"actor": actor, "version_id": version_id})
    return {"status": "queued", "job_id": job.id}


def recheck_after_corrections(db: Session, report: Report, body: bytes, version: WorkbookVersion | None, actor: str,
                              correction_ids: list[str] | None = None) -> dict:
    """Re-run every check on the corrected workbook. An issue a correction was
    meant to fix counts as fixed only if its rule no longer fires on that
    cell; otherwise it is reopened with the re-check's numbers. Findings the
    corrections introduced on the rows they touched are reported, not hidden."""
    db_sheets = db.query(Sheet).filter(Sheet.report_id == report.id).all()
    stem = Path(report.file_name).stem
    with tempfile.TemporaryDirectory(prefix="tb-recheck-") as tmp:
        path = Path(tmp) / f"{stem}.xlsx"
        path.write_bytes(body)
        sheets = pipeline_service.load_workbook(path, source_stem=stem)
    skipped = {s.sheet_name: s.skip_reason for s in db_sheets if s.status == "SKIPPED"}
    for s in sheets:
        if not s.skipped and s.sheet_name in skipped:
            s.skipped, s.skip_reason = True, skipped[s.sheet_name] or "skipped in review"
    confirmed = {s.sheet_name: persistence_service.confirmed_mapping_for_sheet(db, s)
                 for s in db_sheets if s.status == "CONFIRMED"}
    proposals = persistence_service.proposals_from_db(db, report, sheets)
    result = with_previous_submission(db, report, pipeline_service.run_workbook_pipeline(
        sheets, confirmed, proposals, source_name=report.file_name))
    after = _finding_keys(db, report, result)

    ids = list(correction_ids if correction_ids is not None else (version.corrections or []))
    corrections = (db.query(Correction).filter(Correction.report_id == report.id, Correction.id.in_(ids)).all()
                   if ids else [])
    located = (db.query(ValidationResult, Sheet.sheet_name)
               .join(ClaimRow, ClaimRow.id == ValidationResult.claim_row_id)
               .join(Sheet, Sheet.id == ClaimRow.sheet_id)
               .filter(ValidationResult.report_id == report.id).all())
    before = {(vr.rule, name, (vr.extra or {}).get("cell")) for vr, name in located}
    by_id = {vr.id: (vr, name) for vr, name in located}
    passed = failed = 0
    stamp = {"version": version.number if version else None, "sha256": version.sha256 if version else None,
             "at": utcnow().isoformat()}
    label = f"v{version.number}" if version else "(draft)"
    for c in corrections:
        hit = by_id.get(c.issue_id or "")
        if hit is None:
            # No linked issue: verified when no rule fires on the corrected cell.
            fired = [k for k in after if k[1] == c.sheet_name and k[2] == c.cell]
            c.result = {**stamp, "passed": not fired, **({"rules": [k[0] for k in fired]} if fired else {})}
            passed += not fired
            failed += bool(fired)
            continue
        vr, sheet_name = hit
        x = dict(vr.extra or {})
        key = (vr.rule, sheet_name, x.get("cell"))
        if key in after:
            failed += 1
            x["verification"] = {**stamp, "passed": False, **after[key]}
            note = (f"Re-check after correction {label}: {vr.rule} still fails at {sheet_name}!{key[2]} "
                    f"(expected {after[key]['expected']}, actual {after[key]['actual']})")
            try:
                x = issues.transition(x, "DETECTED", "system", note)
            except issues.TransitionError:
                pass  # already open; the verification record still says it failed
        else:
            passed += 1
            x["verification"] = {**stamp, "passed": True}
        vr.extra = x
        c.result = x["verification"]
    touched = {(c.sheet_name, _row_of(c.cell)) for c in corrections}
    new = [{"rule": k[0], "sheet": k[1], "cell": k[2], **v} for k, v in after.items()
           if k not in before and (k[1], _row_of(k[2])) in touched]
    summary = {"status": "ran", "rechecked": passed + failed, "passed": passed, "still_failing": failed,
               "new_findings": len(new), "new": new[:20], "findings_after": len(after)}
    audit_service.log_action(db, report.tenant_id, report.id, "CORRECTIONS_RECHECKED",
                             "WORKBOOK_VERSION" if version else "REPORT", version.id if version else report.id,
                             after={k: v for k, v in summary.items() if k != "new"}, actor=actor)
    return summary
