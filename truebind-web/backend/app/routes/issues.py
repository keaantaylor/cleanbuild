"""Issues, corrections and workbook versions.

Code decides: statuses move only along the issue lifecycle, a correction's
"before" value is read from the stored original (never taken from the client),
and versions are fingerprinted. Every change is audited.
"""

from __future__ import annotations

from typing import Literal

from bordereaux.rules import RULES
from bordereaux.schema import FIELDS_BY_CODE
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.corrections import Correction, WorkbookVersion
from ..models.reports import ClaimRow, Report, Sheet, ValidationResult
from ..security.auth import Context, require_reader, require_writer
from ..services import audit_service, corrections_service, deliverables, issues
from ..services.persistence_service import FIELD_TO_COLUMN
from .deps import get_report_or_404

router = APIRouter(prefix="/api/v1/reports", tags=["issues"])


class _Req(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class StatusRequest(_Req):
    status: Literal["DETECTED", "AUTO_FIX_PROPOSED", "AUTO_FIXED", "REQUIRES_INFORMATION", "REQUIRES_HUMAN_REVIEW",
                    "RESOLVED", "OVERRIDDEN", "BLOCKED"]
    note: str | None = Field(default=None, max_length=2000)


class CorrectionRequest(_Req):
    sheet_id: str = Field(max_length=36)
    cell: str = Field(min_length=2, max_length=16)
    after_value: str | None = Field(default=None, max_length=32000)
    reason: str = Field(min_length=1, max_length=2000)
    issue_id: str | None = Field(default=None, max_length=36)


class DecisionRequest(_Req):
    approve: bool
    note: str | None = Field(default=None, max_length=2000)


class ApproveVersionRequest(_Req):
    note: str | None = Field(default=None, max_length=2000)


def _complete(db: Session, ctx: Context, report_id: str) -> Report:
    report = get_report_or_404(db, ctx, report_id)
    if report.status != "COMPLETE":
        raise HTTPException(status_code=409, detail="Available once the report is processed.")
    return report


def _issue(vr: ValidationResult, row: ClaimRow | None, sheet_name: str | None) -> dict:
    x = vr.extra or {}
    r = RULES.get(vr.rule or "")
    return {
        "id": vr.id, "rule": vr.rule, "rule_version": x.get("rule_version"), "ruleset_version": x.get("ruleset_version"),
        "label": r.label if r else (vr.rule or "").replace("_", " "), "severity": vr.severity, "outcome": vr.status,
        "status": x.get("issue_status") or issues.initial_status(vr.status, vr.rule or ""),
        "sheet": sheet_name, "cell": x.get("cell"), "column": x.get("column"), "field_code": x.get("field_code"),
        "row": row.source_row_number if row else None, "claim_reference": row.claim_reference if row else None,
        "expected": x.get("expected"), "actual": x.get("actual"), "difference": x.get("difference"),
        "evidence": vr.message, "sentence": x.get("sentence"), "suggested_action": r.fix if r else None,
        "owner": x.get("owner"), "root_cause": x.get("root_cause"), "history": x.get("history") or [],
    }


def _get_issue(db: Session, report: Report, issue_id: str):
    hit = (db.query(ValidationResult, ClaimRow, Sheet.sheet_name)
           .join(ClaimRow, ClaimRow.id == ValidationResult.claim_row_id)
           .outerjoin(Sheet, Sheet.id == ClaimRow.sheet_id)
           .filter(ValidationResult.id == issue_id, ValidationResult.report_id == report.id).first())
    if hit is None:
        raise HTTPException(status_code=404, detail="Issue not found.")
    return hit


@router.get("/{report_id}/issues")
def list_issues(report_id: str, status: str | None = Query(default=None, max_length=32),
                rule: str | None = Query(default=None, max_length=64),
                sheet_id: str | None = Query(default=None, max_length=36),
                root_cause: str | None = Query(default=None, max_length=300),
                limit: int = Query(default=100, ge=1, le=1000), offset: int = Query(default=0, ge=0),
                ctx: Context = Depends(require_reader), db: Session = Depends(get_db)) -> dict:
    """Every issue as a record, plus issues grouped by root cause (rule + column)."""
    report = _complete(db, ctx, report_id)
    q = (db.query(ValidationResult, ClaimRow, Sheet.sheet_name)
         .join(ClaimRow, ClaimRow.id == ValidationResult.claim_row_id)
         .outerjoin(Sheet, Sheet.id == ClaimRow.sheet_id)
         .filter(ValidationResult.report_id == report.id))
    if rule:
        q = q.filter(ValidationResult.rule == rule)
    if sheet_id:
        q = q.filter(ClaimRow.sheet_id == sheet_id)
    rows = q.order_by(ClaimRow.sheet_id, ClaimRow.row_index, ValidationResult.rule).all()
    items = [_issue(vr, row, name) for vr, row, name in rows]
    if status:
        items = [i for i in items if i["status"] == status]
    groups: dict[str, dict] = {}
    for i in items:
        g = groups.setdefault(i["root_cause"] or i["rule"], {"root_cause": i["root_cause"] or i["rule"], "rule": i["rule"],
                                                             "label": i["label"], "column": i["column"], "count": 0,
                                                             "open": 0})
        g["count"] += 1
        g["open"] += i["status"] not in issues.CLOSED
    if root_cause:
        items = [i for i in items if i["root_cause"] == root_cause]
    by_status: dict[str, int] = {}
    for i in items:
        by_status[i["status"]] = by_status.get(i["status"], 0) + 1
    return {"total": len(items), "items": items[offset:offset + limit], "by_status": by_status,
            "root_causes": sorted(groups.values(), key=lambda g: -g["count"])}


@router.get("/{report_id}/issues/{issue_id}")
def get_issue(report_id: str, issue_id: str, ctx: Context = Depends(require_reader),
              db: Session = Depends(get_db)) -> dict:
    """One issue with its lineage: where the value came from and what was done to it."""
    report = _complete(db, ctx, report_id)
    vr, row, sheet_name = _get_issue(db, report, issue_id)
    out = _issue(vr, row, sheet_name)
    field = out["field_code"]
    spec = FIELDS_BY_CODE.get(field or "")
    original = None
    if out["cell"] and not str(out["cell"]).startswith("row ") and sheet_name:
        try:
            original = corrections_service.original_value(db, report, sheet_name, out["cell"])
        except corrections_service.CorrectionError:
            original = None
    normalised = getattr(row, FIELD_TO_COLUMN[field], None) if field in FIELD_TO_COLUMN else None
    normalised = normalised.isoformat() if hasattr(normalised, "isoformat") else (
        float(normalised) if normalised is not None and not isinstance(normalised, str) else normalised)
    out["lineage"] = {
        "file": report.file_name, "file_sha256": report.source_sha256, "sheet": sheet_name, "row": out["row"],
        "cell": out["cell"], "column": out["column"], "original_value": original, "normalised_value": normalised,
        "mapped_field": {"code": field, "name": spec.name} if spec else None,
        "transformation": issues.describe_transformation(spec.dtype if spec else None, original, normalised),
    }
    out["corrections"] = [_correction(c) for c in db.query(Correction).filter(Correction.issue_id == vr.id,
                                                                              Correction.report_id == report.id)
                          .order_by(Correction.created_at)]
    return out


@router.post("/{report_id}/issues/{issue_id}/status")
def set_issue_status(report_id: str, issue_id: str, body: StatusRequest, ctx: Context = Depends(require_writer),
                     db: Session = Depends(get_db)) -> dict:
    report = _complete(db, ctx, report_id)
    vr, row, sheet_name = _get_issue(db, report, issue_id)
    before = (vr.extra or {}).get("issue_status")
    try:
        vr.extra = issues.transition(dict(vr.extra or {}), body.status, ctx.actor, body.note)
    except issues.TransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    audit_service.log_action(db, ctx.tenant_id, report.id, "ISSUE_STATUS_CHANGED", "EXCEPTION", vr.id,
                             before={"status": before}, after={"status": body.status, "note": body.note},
                             actor=ctx.actor, actor_user_id=ctx.user_id)
    db.commit()
    return _issue(vr, row, sheet_name)


def _correction(c: Correction) -> dict:
    return {"id": c.id, "issue_id": c.issue_id, "sheet": c.sheet_name, "cell": c.cell, "before": c.before_value,
            "after": c.after_value, "reason": c.reason, "rule": c.rule, "source": c.source, "status": c.status,
            "proposed_by": c.proposed_by, "created_at": c.created_at.isoformat(), "decided_by": c.decided_by,
            "decided_at": c.decided_at.isoformat() if c.decided_at else None, "decision_note": c.decision_note}


def _version(v: WorkbookVersion) -> dict:
    return {"id": v.id, "number": v.number, "kind": v.kind, "sha256": v.sha256, "size": v.size,
            "corrections": len(v.corrections or []), "based_on": v.based_on, "created_by": v.created_by,
            "created_at": v.created_at.isoformat()}


@router.get("/{report_id}/corrections")
def list_corrections(report_id: str, ctx: Context = Depends(require_reader), db: Session = Depends(get_db)) -> dict:
    report = _complete(db, ctx, report_id)
    items = [_correction(c) for c in db.query(Correction).filter(Correction.report_id == report.id)
             .order_by(Correction.created_at, Correction.id)]
    return {"items": items, "total": len(items)}


@router.post("/{report_id}/corrections", status_code=201)
def propose_correction(report_id: str, body: CorrectionRequest, ctx: Context = Depends(require_writer),
                       db: Session = Depends(get_db)) -> dict:
    """Propose a change to one cell. The source file is not touched; the change
    applies only to a corrected version, and only once approved."""
    report = _complete(db, ctx, report_id)
    sheet = db.query(Sheet).filter(Sheet.id == body.sheet_id, Sheet.report_id == report.id).first()
    if sheet is None:
        raise HTTPException(status_code=404, detail="Sheet not found.")
    rule = None
    if body.issue_id:
        vr = db.query(ValidationResult).filter(ValidationResult.id == body.issue_id,
                                               ValidationResult.report_id == report.id).first()
        rule = vr.rule if vr is not None else None
    try:
        c = corrections_service.propose(db, report, sheet.sheet_name, body.cell, body.after_value, body.reason,
                                        ctx.actor, issue_id=body.issue_id, rule=rule)
    except (corrections_service.CorrectionError, deliverables.SourceUnavailable) as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return _correction(c)


@router.post("/{report_id}/corrections/auto")
def propose_auto_corrections(report_id: str, ctx: Context = Depends(require_writer),
                             db: Session = Depends(get_db)) -> dict:
    """Propose the safe formatting fixes (dates and amounts held as text,
    currency spellings, spaces, policy-number zeros, status wording)."""
    report = _complete(db, ctx, report_id)
    try:
        n = corrections_service.propose_auto(db, report, ctx.actor)
    except deliverables.SourceUnavailable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if n == 0:
        audit_service.log_action(db, ctx.tenant_id, report.id, "CORRECTION_PROPOSED", "REPORT", report.id,
                                 after={"automatic": 0}, actor=ctx.actor, actor_user_id=ctx.user_id)
    db.commit()
    return {"proposed": n}


@router.post("/{report_id}/corrections/{correction_id}/decision")
def decide_correction(report_id: str, correction_id: str, body: DecisionRequest, ctx: Context = Depends(require_writer),
                      db: Session = Depends(get_db)) -> dict:
    report = _complete(db, ctx, report_id)
    c = db.query(Correction).filter(Correction.id == correction_id, Correction.report_id == report.id).first()
    if c is None:
        raise HTTPException(status_code=404, detail="Correction not found.")
    try:
        corrections_service.decide(db, report, c, body.approve, ctx.actor, body.note)
    except corrections_service.CorrectionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return _correction(c)


@router.get("/{report_id}/versions")
def list_versions(report_id: str, ctx: Context = Depends(require_reader), db: Session = Depends(get_db)) -> dict:
    report = _complete(db, ctx, report_id)
    versions = (db.query(WorkbookVersion).filter(WorkbookVersion.report_id == report.id)
                .order_by(WorkbookVersion.number).all())
    if not versions:
        versions = [WorkbookVersion(id="original", number=0, kind="original", sha256=report.source_sha256 or "",
                                    size=report.file_size_bytes or 0, corrections=[], created_by="upload",
                                    created_at=report.created_at)]
    return {"items": [_version(v) for v in versions]}


@router.post("/{report_id}/versions", status_code=201)
def create_corrected_version(report_id: str, ctx: Context = Depends(require_writer),
                             db: Session = Depends(get_db)) -> dict:
    """Build a corrected version: the original plus every approved correction."""
    report = _complete(db, ctx, report_id)
    try:
        v, _ = corrections_service.build_corrected(db, report, ctx.actor)
    except (corrections_service.CorrectionError, deliverables.SourceUnavailable) as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return _version(v)


@router.post("/{report_id}/versions/{version_id}/approve", status_code=201)
def approve_version(report_id: str, version_id: str, body: ApproveVersionRequest,
                    ctx: Context = Depends(require_writer), db: Session = Depends(get_db)) -> dict:
    report = _complete(db, ctx, report_id)
    v = db.query(WorkbookVersion).filter(WorkbookVersion.id == version_id, WorkbookVersion.report_id == report.id).first()
    if v is None:
        raise HTTPException(status_code=404, detail="Version not found.")
    try:
        a = corrections_service.approve_version(db, report, v, ctx.actor, body.note)
    except corrections_service.CorrectionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return _version(a)


@router.get("/{report_id}/versions/{version_id}/download")
def download_version(report_id: str, version_id: str, ctx: Context = Depends(require_reader),
                     db: Session = Depends(get_db)) -> Response:
    report = _complete(db, ctx, report_id)
    v = db.query(WorkbookVersion).filter(WorkbookVersion.id == version_id, WorkbookVersion.report_id == report.id).first()
    if v is None:
        raise HTTPException(status_code=404, detail="Version not found.")
    try:
        body = corrections_service.version_bytes(db, report, v)
    except (corrections_service.CorrectionError, deliverables.SourceUnavailable) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    stem = report.file_name.rsplit(".", 1)[0][:80] or "workbook"
    ext = "xlsx" if v.kind != "original" else (report.file_name.rsplit(".", 1)[-1] if "." in report.file_name else "xlsx")
    audit_service.log_action(db, ctx.tenant_id, report.id, "EXPORT_GENERATED", "WORKBOOK_VERSION", v.id,
                             after={"export": f"version_{v.kind}", "number": v.number, "sha256": v.sha256},
                             actor=ctx.actor, actor_user_id=ctx.user_id)
    db.commit()
    name = f"{stem}_v{v.number}_{v.kind}.{ext}".replace('"', "")
    return Response(body, media_type="application/octet-stream", headers={"Content-Disposition": f'attachment; filename="{name}"'})
