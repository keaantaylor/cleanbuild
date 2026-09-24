"""Findings for a processed report: exceptions, duplicate pairs, excluded
rows and the extracted claim rows. Every list is paginated server-side
(forensic: unpaginated lists returned 100k+ objects per request)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.reports import ClaimRow, ExcludedRow, Sheet, ValidationResult
from ..schemas.reports import (
    ClaimRowOut, DuplicatePairOut, DuplicateReviewRequest, ExceptionRowOut, ExcludedRowOut, Page,
)
from ..security.auth import Context, get_context, require_writer
from ..services import audit_service
from .deps import Paging, get_report_or_404

router = APIRouter(prefix="/api/v1/reports", tags=["findings"])

_SEVERITY_RANK = case((ValidationResult.severity == "CRITICAL", 0), (ValidationResult.severity == "HIGH", 1),
                      (ValidationResult.severity == "MEDIUM", 2), else_=3)
CHECK_TYPES = ("MANDATORY_FIELD", "ARITHMETIC", "MAPPING_COMPLETENESS", "DATE", "CURRENCY", "STATUS", "OTHER")


@router.get("/{report_id}/exceptions", response_model=Page[ExceptionRowOut])
def list_exceptions(
    report_id: str,
    check_type: str | None = Query(default=None, max_length=32),
    status: str | None = Query(default=None, pattern="^(FAIL|NOT_EVALUABLE|REVIEW)$"),
    severity: str | None = Query(default=None, pattern="^(CRITICAL|HIGH|MEDIUM|INFO)$"),
    sheet_id: str | None = Query(default=None, max_length=36),
    q_ref: str | None = Query(default=None, max_length=100, alias="q"),
    sort: str = Query(default="row", pattern="^(row|severity)$"),
    paging: Paging = Depends(), ctx: Context = Depends(get_context), db: Session = Depends(get_db),
) -> Page[ExceptionRowOut]:
    report = get_report_or_404(db, ctx, report_id)
    if check_type and check_type not in CHECK_TYPES:
        raise HTTPException(status_code=422, detail=f"check_type must be one of {', '.join(CHECK_TYPES)}.")
    q = (db.query(ValidationResult, ClaimRow, Sheet.sheet_name)
         .join(ClaimRow, ValidationResult.claim_row_id == ClaimRow.id)
         .outerjoin(Sheet, Sheet.id == ClaimRow.sheet_id)
         .filter(ValidationResult.report_id == report.id, ValidationResult.check_type != "DUPLICATE"))
    if check_type:
        q = q.filter(ValidationResult.check_type == check_type)
    if status:
        q = q.filter(ValidationResult.status == status)
    if severity:
        q = q.filter(ValidationResult.severity == severity)
    if sheet_id:
        q = q.filter(ClaimRow.sheet_id == sheet_id)
    if q_ref:
        q = q.filter(ClaimRow.claim_reference.ilike(f"%{q_ref.replace('%', '').replace('_', '')}%"))
    total = q.with_entities(func.count(ValidationResult.id)).scalar()
    order = ([_SEVERITY_RANK, ClaimRow.sheet_id, ClaimRow.row_index] if sort == "severity"
             else [ClaimRow.sheet_id, ClaimRow.row_index, ValidationResult.check_type])
    rows = q.order_by(*order).limit(paging.limit).offset(paging.offset).all()
    items = [ExceptionRowOut(
        validation_result_id=vr.id, claim_row_id=row.id, claim_reference=row.claim_reference, sheet_name=sheet_name,
        source_row_number=row.source_row_number, row_index=row.row_index, currency=row.currency,
        amount=row.incurred_amount if row.incurred_amount is not None else row.paid_amount,
        check_type=vr.check_type, rule=vr.rule, status=vr.status, severity=vr.severity, message=vr.message,
        review_status=(vr.extra or {}).get("review_status"), assignee=(vr.extra or {}).get("assignee"),
        note=(vr.extra or {}).get("note"),
    ) for vr, row, sheet_name in rows]
    return Page(items=items, total=total, limit=paging.limit, offset=paging.offset)


def _row_dict(row: ClaimRow | None, sheet_names: dict[str, str]) -> dict:
    if row is None:
        return {}
    return {"id": row.id, "sheet_name": sheet_names.get(row.sheet_id), "source_row_number": row.source_row_number,
            "claim_reference": row.claim_reference, "insured_name": row.insured_name,
            "reporting_period": row.reporting_period, "currency": row.currency,
            "date_of_loss": row.date_of_loss.isoformat() if row.date_of_loss else None,
            "paid_amount": row.paid_amount, "reserve_amount": row.reserve_amount,
            "incurred_amount": row.incurred_amount}


def _pair(vr: ValidationResult, a: ClaimRow, b: ClaimRow | None, sheet_names) -> DuplicatePairOut:
    extra = vr.extra or {}
    return DuplicatePairOut(validation_result_id=vr.id, match_type=extra.get("match_type", vr.rule or "probable"),
                            status=vr.status, row_a=_row_dict(a, sheet_names), row_b=_row_dict(b, sheet_names),
                            detail=vr.message, review_status=extra.get("review_status"))


@router.get("/{report_id}/duplicates", response_model=Page[DuplicatePairOut])
def list_duplicates(report_id: str, match_type: str | None = Query(default=None, max_length=32),
                    paging: Paging = Depends(), ctx: Context = Depends(get_context),
                    db: Session = Depends(get_db)) -> Page[DuplicatePairOut]:
    report = get_report_or_404(db, ctx, report_id)
    sheet_names = dict(db.query(Sheet.id, Sheet.sheet_name).filter(Sheet.report_id == report.id).all())
    q = (db.query(ValidationResult, ClaimRow)
         .join(ClaimRow, ValidationResult.claim_row_id == ClaimRow.id)
         .filter(ValidationResult.report_id == report.id, ValidationResult.check_type == "DUPLICATE"))
    if match_type:
        q = q.filter(ValidationResult.rule == match_type)
    total = q.with_entities(func.count(ValidationResult.id)).scalar()
    page = q.order_by(ClaimRow.sheet_id, ClaimRow.row_index).limit(paging.limit).offset(paging.offset).all()
    match_ids = [(vr.extra or {}).get("match_claim_row_id") for vr, _ in page]
    matches = {r.id: r for r in db.query(ClaimRow).filter(ClaimRow.report_id == report.id,
                                                          ClaimRow.id.in_([m for m in match_ids if m]))}
    items = [_pair(vr, a, matches.get(mid), sheet_names) for (vr, a), mid in zip(page, match_ids)]
    return Page(items=items, total=total, limit=paging.limit, offset=paging.offset)


@router.patch("/{report_id}/duplicates/{validation_result_id}/review", response_model=DuplicatePairOut)
def review_duplicate(report_id: str, validation_result_id: str, body: DuplicateReviewRequest,
                     ctx: Context = Depends(require_writer), db: Session = Depends(get_db)) -> DuplicatePairOut:
    """Records a reviewer's decision. Never merges or deletes rows."""
    report = get_report_or_404(db, ctx, report_id)
    vr = (db.query(ValidationResult)
          .filter(ValidationResult.id == validation_result_id, ValidationResult.report_id == report.id,
                  ValidationResult.check_type == "DUPLICATE").first())
    if vr is None:
        raise HTTPException(status_code=404, detail="Duplicate finding not found.")
    before = dict(vr.extra or {})
    vr.extra = {**before, "review_status": body.review_status, "reviewed_by": ctx.actor}
    audit_service.log_action(db, ctx.tenant_id, report.id, "EXCEPTION_STATUS_CHANGED", "EXCEPTION", vr.id,
                             before={"review_status": before.get("review_status")},
                             after={"review_status": body.review_status}, actor=ctx.actor, actor_user_id=ctx.user_id)
    db.commit()
    sheet_names = dict(db.query(Sheet.id, Sheet.sheet_name).filter(Sheet.report_id == report.id).all())
    a = db.get(ClaimRow, vr.claim_row_id)
    mid = (vr.extra or {}).get("match_claim_row_id")
    b = db.query(ClaimRow).filter(ClaimRow.id == mid, ClaimRow.report_id == report.id).first() if mid else None
    return _pair(vr, a, b, sheet_names)


@router.get("/{report_id}/excluded-rows", response_model=Page[ExcludedRowOut])
def list_excluded_rows(report_id: str, reason: str | None = Query(default=None, max_length=32),
                       paging: Paging = Depends(), ctx: Context = Depends(get_context),
                       db: Session = Depends(get_db)) -> Page[ExcludedRowOut]:
    report = get_report_or_404(db, ctx, report_id)
    q = db.query(ExcludedRow).filter(ExcludedRow.report_id == report.id)
    if reason:
        q = q.filter(ExcludedRow.reason == reason)
    total = q.count()
    rows = q.order_by(ExcludedRow.sheet_name, ExcludedRow.row_number).limit(paging.limit).offset(paging.offset).all()
    return Page(items=[ExcludedRowOut.model_validate(r) for r in rows], total=total,
                limit=paging.limit, offset=paging.offset)


@router.get("/{report_id}/claims", response_model=Page[ClaimRowOut])
def list_claims(report_id: str, sheet_id: str | None = Query(default=None, max_length=36),
                q_ref: str | None = Query(default=None, max_length=100, alias="q"),
                paging: Paging = Depends(), ctx: Context = Depends(get_context),
                db: Session = Depends(get_db)) -> Page[ClaimRowOut]:
    report = get_report_or_404(db, ctx, report_id)
    q = db.query(ClaimRow).filter(ClaimRow.report_id == report.id)
    if sheet_id:
        q = q.filter(ClaimRow.sheet_id == sheet_id)
    if q_ref:
        q = q.filter(ClaimRow.claim_reference.ilike(f"%{q_ref.replace('%', '').replace('_', '')}%"))
    total = q.count()
    rows = q.order_by(ClaimRow.sheet_id, ClaimRow.row_index).limit(paging.limit).offset(paging.offset).all()
    return Page(items=[ClaimRowOut.model_validate(r) for r in rows], total=total,
                limit=paging.limit, offset=paging.offset)

