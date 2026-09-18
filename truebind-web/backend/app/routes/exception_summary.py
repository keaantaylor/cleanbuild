"""AI exception-triage summary: POST computes the deterministic aggregate
synchronously (fast -- a handful of DB aggregation queries) and kicks the
LLM narrative off as a background task, mirroring routes/mapping.py's
/process pattern so report generation is never blocked or delayed by the
AI call (fix spec Section 1.3). GET polls for the latest one."""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..database import get_db, get_session_factory
from ..models.exception_summary import ExceptionSummary
from ..schemas.reports import ExceptionSummaryOut
from ..services import audit_service, exception_aggregation_service, exception_narrative_service
from .deps import get_report_or_404

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/reports", tags=["exception_summary"])


def _generate_narrative_in_background(summary_id: str) -> None:
    session_factory = get_session_factory()
    db = session_factory()
    try:
        summary = db.get(ExceptionSummary, summary_id)
        if summary is None:
            return

        result = exception_narrative_service.generate_narrative(summary.aggregate)
        summary.narrative_status = result.status
        summary.narrative = result.narrative
        summary.narrative_model = result.model
        summary.narrative_error = result.error
        summary.narrative_warning = result.warning
        from ..models._util import utcnow
        summary.completed_at = utcnow()
        db.commit()

        if result.status == "COMPLETE":
            # Fix spec Section 1.4: the fact that an AI-generated
            # narrative was produced, and when, must be traceable in the
            # same audit trail every other mutation goes through.
            audit_service.log_action(
                db, summary.report_id, "AI_SUMMARY_GENERATED", "EXCEPTION_SUMMARY", summary.id,
                after={"model": result.model, "narrative_status": result.status,
                       "narrative_warning": result.warning},
                actor="ai_triage_summariser",
            )
            db.commit()
    except Exception:  # noqa: BLE001 -- never let a background-task crash leave the row stuck GENERATING
        logger.exception("Exception-summary narrative generation failed for summary %s", summary_id)
        db.rollback()
        summary = db.get(ExceptionSummary, summary_id)
        if summary is not None:
            summary.narrative_status = "FAILED"
            summary.narrative_error = "Internal error while generating the narrative."
            db.commit()
    finally:
        db.close()


@router.post("/{report_id}/exceptions/summary", response_model=ExceptionSummaryOut, status_code=202)
def create_exception_summary(
    report_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db),
) -> ExceptionSummaryOut:
    report = get_report_or_404(db, report_id)

    aggregate = exception_aggregation_service.build_aggregate(db, report)
    summary = ExceptionSummary(report_id=report.id, narrative_status="GENERATING", aggregate=aggregate)
    db.add(summary)
    db.commit()
    db.refresh(summary)

    if exception_narrative_service.narrative_available():
        background_tasks.add_task(_generate_narrative_in_background, summary.id)
    else:
        summary.narrative_status = "UNAVAILABLE"
        summary.narrative_error = "ANTHROPIC_API_KEY is not set"
        db.commit()
        db.refresh(summary)

    return ExceptionSummaryOut.model_validate(summary)


@router.get("/{report_id}/exceptions/summary", response_model=ExceptionSummaryOut)
def get_latest_exception_summary(report_id: str, db: Session = Depends(get_db)) -> ExceptionSummaryOut | Response:
    get_report_or_404(db, report_id)
    summary = (
        db.query(ExceptionSummary)
        .filter_by(report_id=report_id)
        .order_by(ExceptionSummary.created_at.desc())
        .first()
    )
    if summary is None:
        return Response(status_code=204)
    return ExceptionSummaryOut.model_validate(summary)
