from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.audit import AuditLogEntry
from ..schemas.reports import AuditLogOut, AuditVerifyOut, Page
from ..security.auth import Context, get_context
from ..services import audit_service
from .deps import Paging, get_report_or_404

router = APIRouter(prefix="/api/v1", tags=["audit"])


@router.get("/reports/{report_id}/audit", response_model=Page[AuditLogOut])
def get_report_audit(report_id: str, action_type: str | None = Query(default=None, max_length=64),
                     paging: Paging = Depends(), ctx: Context = Depends(get_context),
                     db: Session = Depends(get_db)) -> Page[AuditLogOut]:
    report = get_report_or_404(db, ctx, report_id)
    q = db.query(AuditLogEntry).filter(AuditLogEntry.tenant_id == ctx.tenant_id, AuditLogEntry.report_id == report.id)
    if action_type:
        q = q.filter(AuditLogEntry.action_type == action_type)
    total = q.count()
    rows = q.order_by(AuditLogEntry.seq.desc()).limit(paging.limit).offset(paging.offset).all()
    return Page(items=[AuditLogOut.model_validate(e) for e in rows], total=total,
                limit=paging.limit, offset=paging.offset)


@router.get("/audit", response_model=Page[AuditLogOut])
def get_tenant_audit(paging: Paging = Depends(), ctx: Context = Depends(get_context),
                     db: Session = Depends(get_db)) -> Page[AuditLogOut]:
    q = db.query(AuditLogEntry).filter(AuditLogEntry.tenant_id == ctx.tenant_id)
    total = q.count()
    rows = q.order_by(AuditLogEntry.seq.desc()).limit(paging.limit).offset(paging.offset).all()
    return Page(items=[AuditLogOut.model_validate(e) for e in rows], total=total,
                limit=paging.limit, offset=paging.offset)


@router.get("/audit/verify", response_model=AuditVerifyOut)
def verify_audit_chain(ctx: Context = Depends(get_context), db: Session = Depends(get_db)) -> AuditVerifyOut:
    ok, bad = audit_service.verify_chain(db, ctx.tenant_id)
    n = db.query(AuditLogEntry).filter(AuditLogEntry.tenant_id == ctx.tenant_id).count()
    return AuditVerifyOut(intact=ok, entries=n, first_bad_seq=bad)
