from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.audit import AuditLogEntry
from ..schemas.reports import AuditLogOut
from .deps import get_report_or_404

router = APIRouter(prefix="/api/v1/reports", tags=["audit"])


@router.get("/{report_id}/audit", response_model=list[AuditLogOut])
def get_audit_log(
    report_id: str,
    action_type: str | None = Query(default=None),
    actor: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[AuditLogOut]:
    get_report_or_404(db, report_id)
    q = db.query(AuditLogEntry).filter_by(report_id=report_id)
    if action_type:
        q = q.filter_by(action_type=action_type)
    if actor:
        q = q.filter_by(actor=actor)
    entries = q.order_by(AuditLogEntry.created_at.desc()).all()
    return [AuditLogOut.model_validate(e) for e in entries]
