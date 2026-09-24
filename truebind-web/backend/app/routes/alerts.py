from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.alerts import Alert
from ..schemas.reports import AlertOut, Page
from ..security.auth import Context, get_context, require_writer
from ..services import audit_service
from .deps import Paging

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


@router.get("", response_model=Page[AlertOut])
def list_alerts(report_id: str | None = Query(default=None, max_length=36), acknowledged: bool | None = None,
                paging: Paging = Depends(), ctx: Context = Depends(get_context),
                db: Session = Depends(get_db)) -> Page[AlertOut]:
    q = db.query(Alert).filter(Alert.tenant_id == ctx.tenant_id)
    if report_id:
        q = q.filter(Alert.report_id == report_id)
    if acknowledged is not None:
        q = q.filter(Alert.acknowledged == acknowledged)
    total = q.count()
    rows = q.order_by(Alert.created_at.desc()).limit(paging.limit).offset(paging.offset).all()
    return Page(items=[AlertOut.model_validate(a) for a in rows], total=total, limit=paging.limit, offset=paging.offset)


@router.post("/{alert_id}/acknowledge", response_model=AlertOut)
def acknowledge_alert(alert_id: str, ctx: Context = Depends(require_writer), db: Session = Depends(get_db)) -> AlertOut:
    alert = db.query(Alert).filter(Alert.id == alert_id, Alert.tenant_id == ctx.tenant_id).first()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found.")
    if not alert.acknowledged:
        alert.acknowledged = True
        audit_service.log_action(db, ctx.tenant_id, alert.report_id, "ALERT_ACKNOWLEDGED", "ALERT", alert.id,
                                 after={"acknowledged": True}, actor=ctx.actor, actor_user_id=ctx.user_id)
        db.commit()
    return AlertOut.model_validate(alert)
