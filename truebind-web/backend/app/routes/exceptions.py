from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models.reports import ClaimRow, Sheet, ValidationResult
from ..schemas.reports import ExceptionRowOut
from .deps import get_report_or_404

router = APIRouter(prefix="/api/v1/reports", tags=["exceptions"])


@router.get("/{report_id}/exceptions", response_model=list[ExceptionRowOut])
def list_exceptions(
    report_id: str,
    check_type: str | None = Query(default=None, description="MANDATORY_FIELD | ARITHMETIC | MAPPING_COMPLETENESS"),
    status: str | None = Query(default=None, description="FAIL | NOT_EVALUABLE -- distinguishes a real "
                                                           "defect from a row Truebind couldn't check"),
    db: Session = Depends(get_db),
) -> list[ExceptionRowOut]:
    get_report_or_404(db, report_id)
    q = (
        db.query(ValidationResult)
        .join(ClaimRow, ValidationResult.claim_row_id == ClaimRow.id)
        .options(joinedload(ValidationResult.claim_row))
        .filter(ClaimRow.report_id == report_id, ValidationResult.check_type != "DUPLICATE")
    )
    if check_type:
        q = q.filter(ValidationResult.check_type == check_type)
    if status:
        q = q.filter(ValidationResult.status == status)

    sheet_names = {s.id: s.sheet_name for s in db.query(Sheet).filter_by(report_id=report_id).all()}

    out = []
    for vr in q.all():
        row = vr.claim_row
        out.append(ExceptionRowOut(
            claim_row_id=row.id,
            claim_reference=row.claim_reference,
            sheet_name=sheet_names.get(row.sheet_id),
            row_index=row.row_index,
            amount=row.incurred_amount if row.incurred_amount is not None else row.paid_amount,
            check_type=vr.check_type,
            status=vr.status,
            severity=vr.severity,
            message=vr.message,
            validation_result_id=vr.id,
        ))
    return out
