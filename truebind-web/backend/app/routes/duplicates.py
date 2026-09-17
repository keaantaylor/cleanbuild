from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models.reports import ClaimRow, ValidationResult
from ..schemas.reports import DuplicatePairOut
from ..services import audit_service
from .deps import get_report_or_404

router = APIRouter(prefix="/api/v1/reports", tags=["duplicates"])

REVIEW_STATUSES = ("not_duplicate", "flagged_for_sender", "confirmed_duplicate")


class DuplicateReviewRequest(BaseModel):
    review_status: str
    actor: str | None = None


def _row_dict(row: ClaimRow) -> dict:
    return {
        "id": row.id,
        "claim_reference": row.claim_reference,
        "insured_name": row.insured_name,
        "date_of_loss": row.date_of_loss.isoformat() if row.date_of_loss else None,
        "paid_amount": row.paid_amount,
        "reserve_amount": row.reserve_amount,
        "incurred_amount": row.incurred_amount,
    }


@router.get("/{report_id}/duplicates", response_model=list[DuplicatePairOut])
def list_duplicates(report_id: str, db: Session = Depends(get_db)) -> list[DuplicatePairOut]:
    get_report_or_404(db, report_id)
    rows = (
        db.query(ValidationResult)
        .join(ClaimRow, ValidationResult.claim_row_id == ClaimRow.id)
        .options(joinedload(ValidationResult.claim_row))
        .filter(ClaimRow.report_id == report_id, ValidationResult.check_type == "DUPLICATE")
        .all()
    )

    out = []
    for vr in rows:
        match_id = (vr.extra or {}).get("match_claim_row_id")
        match_row = db.get(ClaimRow, match_id) if match_id else None
        out.append(DuplicatePairOut(
            validation_result_id=vr.id,
            match_type=(vr.extra or {}).get("match_type", "probable_duplicate"),
            row_a=_row_dict(vr.claim_row),
            row_b=_row_dict(match_row) if match_row else {},
            detail=vr.message,
            review_status=(vr.extra or {}).get("review_status"),
        ))
    return out


@router.patch("/{report_id}/duplicates/{validation_result_id}/review", response_model=DuplicatePairOut)
def review_duplicate(
    report_id: str, validation_result_id: str, body: DuplicateReviewRequest, db: Session = Depends(get_db),
) -> DuplicatePairOut:
    """Truebind never auto-merges a flagged duplicate -- this only records
    a human reviewer's call (not a duplicate / flag for the sender /
    confirmed duplicate) against the audit trail; the underlying rows are
    untouched either way."""
    get_report_or_404(db, report_id)
    if body.review_status not in REVIEW_STATUSES:
        raise HTTPException(status_code=422, detail=f"review_status must be one of {REVIEW_STATUSES}")

    vr = (
        db.query(ValidationResult)
        .options(joinedload(ValidationResult.claim_row))
        .filter_by(id=validation_result_id, check_type="DUPLICATE")
        .first()
    )
    if vr is None or vr.claim_row.report_id != report_id:
        raise HTTPException(status_code=404, detail="Duplicate finding not found on this report")

    before = dict(vr.extra or {})
    vr.extra = {**(vr.extra or {}), "review_status": body.review_status}
    audit_service.log_action(
        db, report_id, "EXCEPTION_STATUS_CHANGED", "EXCEPTION", vr.id,
        before=before, after=vr.extra, actor=body.actor or "web_user",
    )
    db.commit()
    db.refresh(vr)

    match_id = (vr.extra or {}).get("match_claim_row_id")
    match_row = db.get(ClaimRow, match_id) if match_id else None
    return DuplicatePairOut(
        validation_result_id=vr.id,
        match_type=(vr.extra or {}).get("match_type", "probable_duplicate"),
        row_a=_row_dict(vr.claim_row),
        row_b=_row_dict(match_row) if match_row else {},
        detail=vr.message,
        review_status=(vr.extra or {}).get("review_status"),
    )
