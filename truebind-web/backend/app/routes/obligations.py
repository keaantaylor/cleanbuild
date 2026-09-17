from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.obligations import OBLIGATION_STATUSES, Obligation
from ..schemas.reports import ObligationCreateRequest, ObligationOut, ObligationUpdateRequest
from ..services import audit_service
from .deps import get_report_or_404

router = APIRouter(prefix="/api/v1", tags=["obligations"])


def _computed_status(ob: Obligation) -> str:
    """OVERDUE is derived, never stored as a human choice -- see
    models/obligations.py's docstring."""
    if ob.status == "RESOLVED":
        return "RESOLVED"
    if ob.deadline and ob.deadline < datetime.now(timezone.utc).date():
        return "OVERDUE"
    return ob.status if ob.status in ("OPEN", "IN_PROGRESS") else "OPEN"


@router.post("/reports/{report_id}/obligations", response_model=ObligationOut)
def create_obligation(report_id: str, body: ObligationCreateRequest, db: Session = Depends(get_db)) -> ObligationOut:
    report = get_report_or_404(db, report_id)
    ob = Obligation(report_id=report.id, **body.model_dump())
    db.add(ob)
    db.flush()
    audit_service.log_action(db, report.id, "OBLIGATION_STATUS_CHANGED", "OBLIGATION", ob.id,
                              after={"status": ob.status}, actor=body.created_by or "web_user")
    db.commit()
    db.refresh(ob)
    ob.status = _computed_status(ob)
    return ObligationOut.model_validate(ob)


@router.get("/obligations", response_model=list[ObligationOut])
def list_obligations(
    report_id: str | None = Query(default=None), status: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[ObligationOut]:
    q = db.query(Obligation)
    if report_id:
        q = q.filter_by(report_id=report_id)
    obligations = q.order_by(Obligation.deadline.is_(None), Obligation.deadline).all()
    out = []
    for ob in obligations:
        computed = _computed_status(ob)
        if status and computed != status:
            continue
        result = ObligationOut.model_validate(ob)
        result.status = computed
        out.append(result)
    return out


@router.patch("/obligations/{obligation_id}", response_model=ObligationOut)
def update_obligation(obligation_id: str, body: ObligationUpdateRequest, db: Session = Depends(get_db)) -> ObligationOut:
    ob = db.get(Obligation, obligation_id)
    if ob is None:
        raise HTTPException(status_code=404, detail=f"Obligation {obligation_id} not found")

    before = {"owner": ob.owner, "deadline": str(ob.deadline) if ob.deadline else None, "status": ob.status}

    updates = body.model_dump(exclude_unset=True)
    if "status" in updates and updates["status"] not in OBLIGATION_STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of {OBLIGATION_STATUSES}")
    for key, value in updates.items():
        setattr(ob, key, value)
    if updates.get("status") == "RESOLVED":
        ob.resolved_at = datetime.now(timezone.utc)

    after = {"owner": ob.owner, "deadline": str(ob.deadline) if ob.deadline else None, "status": ob.status}
    audit_service.log_action(db, ob.report_id, "OBLIGATION_STATUS_CHANGED", "OBLIGATION", ob.id,
                              before=before, after=after)
    db.commit()
    db.refresh(ob)
    ob.status = _computed_status(ob)
    return ObligationOut.model_validate(ob)
