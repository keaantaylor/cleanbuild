from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.alerts import Alert
from ..schemas.reports import AlertOut
from ..services import audit_service

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertOut])
def list_alerts(
    report_id: str | None = Query(default=None),
    acknowledged: bool | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[AlertOut]:
    q = db.query(Alert)
    if report_id:
        q = q.filter_by(report_id=report_id)
    if acknowledged is not None:
        q = q.filter_by(acknowledged=acknowledged)
    return [AlertOut.model_validate(a) for a in q.order_by(Alert.created_at.desc()).all()]


@router.patch("/{alert_id}", response_model=AlertOut)
def acknowledge_alert(alert_id: str, db: Session = Depends(get_db)) -> AlertOut:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    alert.acknowledged = True
    audit_service.log_action(db, alert.report_id, "ALERT_ACKNOWLEDGED", "ALERT", alert.id, after={"acknowledged": True})
    db.commit()
    db.refresh(alert)
    return AlertOut.model_validate(alert)
