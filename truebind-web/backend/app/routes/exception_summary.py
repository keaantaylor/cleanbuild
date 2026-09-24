"""AI exception-triage summary. POST computes the deterministic aggregate
synchronously (SQL aggregation) and generates the narrative in a background
task with its own tenant-bound session; GET returns the latest one.

Cost control: at most 10 narratives per tenant per hour. The AI never sees
row-level data -- only the aggregate (counts, per-currency totals, sheet
names) -- and its figures are checked against the aggregate afterwards."""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..database import get_db, get_session_factory, set_tenant
from ..models._util import utcnow
from ..models.exception_summary import ExceptionSummary
from ..schemas.reports import ExceptionSummaryOut
from ..security.auth import Context, get_context, require_writer
from ..security.ratelimit import limiter
from ..services import audit_service, exception_aggregation_service, exception_narrative_service
from .deps import get_report_or_404

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/reports", tags=["exception_summary"])


def _generate_narrative_in_background(summary_id: str, tenant_id: str) -> None:
    db = get_session_factory()()
    try:
        set_tenant(db, tenant_id)
        summary = db.query(ExceptionSummary).filter_by(id=summary_id, tenant_id=tenant_id).first()
        if summary is None:
            return
        result = exception_narrative_service.generate_narrative(summary.aggregate)
        summary.narrative_status = result.status
        summary.narrative = result.narrative
        summary.narrative_model = result.model
        summary.narrative_error = result.error
        summary.narrative_warning = result.warning
        summary.completed_at = utcnow()
        if result.status == "COMPLETE":
            audit_service.log_action(db, tenant_id, summary.report_id, "AI_SUMMARY_GENERATED", "EXCEPTION_SUMMARY",
                                     summary.id, after={"model": result.model, "warning": bool(result.warning)},
                                     actor="ai_triage_summariser")
        db.commit()
    except Exception:  # noqa: BLE001 -- never leave the row stuck at GENERATING
        logger.exception("exception-summary narrative failed for %s", summary_id)
        db.rollback()
        set_tenant(db, tenant_id)
        summary = db.query(ExceptionSummary).filter_by(id=summary_id, tenant_id=tenant_id).first()
        if summary is not None:
            summary.narrative_status = "FAILED"
            summary.narrative_error = "Internal error while generating the narrative."
            db.commit()
    finally:
        db.close()


@router.post("/{report_id}/exceptions/summary", response_model=ExceptionSummaryOut, status_code=202)
def create_exception_summary(report_id: str, background_tasks: BackgroundTasks,
                             ctx: Context = Depends(require_writer), db: Session = Depends(get_db)) -> ExceptionSummaryOut:
    report = get_report_or_404(db, ctx, report_id)
    if report.status != "COMPLETE":
        raise HTTPException(status_code=409, detail="The report must finish processing first.")
    available = exception_narrative_service.narrative_available()
    if available:
        limiter.check("ai-summary", ctx.tenant_id, limit=10, window_s=3600)
    summary = ExceptionSummary(tenant_id=ctx.tenant_id, report_id=report.id,
                               aggregate=exception_aggregation_service.build_aggregate(db, report),
                               narrative_status="GENERATING" if available else "UNAVAILABLE",
                               narrative_error=None if available else "AI summaries are not configured on this server.")
    db.add(summary)
    db.commit()
    if available:
        background_tasks.add_task(_generate_narrative_in_background, summary.id, ctx.tenant_id)
    return ExceptionSummaryOut.model_validate(summary)


@router.get("/{report_id}/exceptions/summary", response_model=ExceptionSummaryOut)
def get_latest_exception_summary(report_id: str, ctx: Context = Depends(get_context), db: Session = Depends(get_db)):
    report = get_report_or_404(db, ctx, report_id)
    summary = (db.query(ExceptionSummary).filter(ExceptionSummary.report_id == report.id)
               .order_by(ExceptionSummary.created_at.desc()).first())
    if summary is None:
        return Response(status_code=204)
    return ExceptionSummaryOut.model_validate(summary)
