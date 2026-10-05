"""Counterparty memory and information requests."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.memory import InfoRequest
from ..models.reports import Report
from ..security.auth import Context, require_reader, require_writer
from ..services import email_loop, memory_service
from .deps import get_report_or_404

router = APIRouter(prefix="/api/v1", tags=["memory"])


class RuleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field_code: str | None = Field(default=None, max_length=32)
    rule: str | None = Field(default=None, max_length=64)
    match_value: str | None = Field(default=None, max_length=32000)
    replace_value: str | None = Field(default=None, max_length=32000)


@router.get("/counterparties")
def list_counterparties(ctx: Context = Depends(require_reader), db: Session = Depends(get_db)) -> dict:
    rows = (db.query(func.lower(Report.sender), func.count(Report.id), func.max(Report.created_at))
            .filter(Report.tenant_id == ctx.tenant_id, Report.sender.isnot(None))
            .group_by(func.lower(Report.sender)).order_by(func.max(Report.created_at).desc()).limit(500).all())
    return {"items": [{"sender": s, "submissions": n, "last_received_at": last.isoformat() if last else None}
                      for s, n, last in rows if s]}


@router.get("/counterparties/profile")
def counterparty_profile(sender: str = Query(default="", max_length=200), ctx: Context = Depends(require_reader),
                         db: Session = Depends(get_db)) -> dict:
    """What TrueBind knows about one sender: submissions, layouts, periods,
    recurring errors, known exceptions, approved corrections and rules, contacts."""
    return memory_service.profile(db, ctx.tenant_id, sender)


@router.get("/memory/rule-suggestions")
def rule_suggestions(ctx: Context = Depends(require_reader), db: Session = Depends(get_db)) -> dict:
    return {"items": memory_service.rule_suggestions(db, ctx.tenant_id)}


@router.post("/memory/rules", status_code=201)
def approve_rule(body: RuleRequest, ctx: Context = Depends(require_writer), db: Session = Depends(get_db)) -> dict:
    """A person approves a suggested reusable rule. Only a correction observed
    and approved repeatedly can become one."""
    try:
        r = memory_service.approve_rule(db, ctx.tenant_id, body.model_dump(), ctx.actor, ctx.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return {"id": r.id, "field_code": r.field_code, "rule": r.rule, "match_value": r.match_value,
            "replace_value": r.replace_value, "observed": r.observed, "sender": r.sender, "status": r.status}


@router.get("/reports/{report_id}/requests")
def report_requests(report_id: str, ctx: Context = Depends(require_reader), db: Session = Depends(get_db)) -> dict:
    report = get_report_or_404(db, ctx, report_id)
    reqs = (db.query(InfoRequest).filter(InfoRequest.tenant_id == ctx.tenant_id, InfoRequest.report_id == report.id)
            .order_by(InfoRequest.number).all())
    return {"items": [email_loop.out(r) for r in reqs]}
