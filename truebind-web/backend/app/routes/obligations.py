from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.obligations import Obligation
from ..models.reports import ClaimRow
from ..schemas.reports import ObligationCreateRequest, ObligationOut, ObligationUpdateRequest, Page
from ..security.auth import Context, get_context, require_writer
from ..services import audit_service
from .deps import Paging, get_report_or_404

router = APIRouter(prefix="/api/v1", tags=["obligations"])


def _out(ob: Obligation) -> ObligationOut:
    """OVERDUE is derived (deadline passed, not resolved), never stored."""
    out = ObligationOut.model_validate(ob)
    if ob.status != "RESOLVED" and ob.deadline and ob.deadline < datetime.now(timezone.utc).date():
        out.status = "OVERDUE"
    return out


def _snapshot(ob: Obligation) -> dict:
    return {"owner": ob.owner, "deadline": str(ob.deadline) if ob.deadline else None, "status": ob.status}


@router.post("/reports/{report_id}/obligations", response_model=ObligationOut, status_code=201)
def create_obligation(report_id: str, body: ObligationCreateRequest, ctx: Context = Depends(require_writer),
                      db: Session = Depends(get_db)) -> ObligationOut:
    report = get_report_or_404(db, ctx, report_id)
    if body.claim_row_id and db.query(ClaimRow).filter(ClaimRow.id == body.claim_row_id,
                                                        ClaimRow.report_id == report.id).first() is None:
        raise HTTPException(status_code=422, detail="claim_row_id does not belong to this report.")
    ob = Obligation(tenant_id=ctx.tenant_id, report_id=report.id, created_by=ctx.actor, **body.model_dump())
    db.add(ob)
    db.flush()
    audit_service.log_action(db, ctx.tenant_id, report.id, "OBLIGATION_STATUS_CHANGED", "OBLIGATION", ob.id,
                             after=_snapshot(ob), actor=ctx.actor, actor_user_id=ctx.user_id)
    db.commit()
    return _out(ob)


@router.get("/obligations", response_model=Page[ObligationOut])
def list_obligations(report_id: str | None = Query(default=None, max_length=36),
                     status: str | None = Query(default=None, pattern="^(OPEN|IN_PROGRESS|RESOLVED|OVERDUE)$"),
                     paging: Paging = Depends(), ctx: Context = Depends(get_context),
                     db: Session = Depends(get_db)) -> Page[ObligationOut]:
    q = db.query(Obligation).filter(Obligation.tenant_id == ctx.tenant_id)
    if report_id:
        q = q.filter(Obligation.report_id == report_id)
    today = datetime.now(timezone.utc).date()
    if status == "OVERDUE":
        q = q.filter(Obligation.status != "RESOLVED", Obligation.deadline < today)
    elif status in ("OPEN", "IN_PROGRESS"):
        q = q.filter(Obligation.status == status, (Obligation.deadline.is_(None)) | (Obligation.deadline >= today))
    elif status == "RESOLVED":
        q = q.filter(Obligation.status == "RESOLVED")
    total = q.count()
    rows = (q.order_by(Obligation.deadline.is_(None), Obligation.deadline, Obligation.created_at)
            .limit(paging.limit).offset(paging.offset).all())
    return Page(items=[_out(o) for o in rows], total=total, limit=paging.limit, offset=paging.offset)


@router.patch("/obligations/{obligation_id}", response_model=ObligationOut)
def update_obligation(obligation_id: str, body: ObligationUpdateRequest, ctx: Context = Depends(require_writer),
                      db: Session = Depends(get_db)) -> ObligationOut:
    ob = db.query(Obligation).filter(Obligation.id == obligation_id, Obligation.tenant_id == ctx.tenant_id).first()
    if ob is None:
        raise HTTPException(status_code=404, detail="Obligation not found.")
    before = _snapshot(ob)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(ob, key, value)
    ob.resolved_at = datetime.now(timezone.utc) if ob.status == "RESOLVED" else None
    audit_service.log_action(db, ctx.tenant_id, ob.report_id, "OBLIGATION_STATUS_CHANGED", "OBLIGATION", ob.id,
                             before=before, after=_snapshot(ob), actor=ctx.actor, actor_user_id=ctx.user_id)
    db.commit()
    return _out(ob)
