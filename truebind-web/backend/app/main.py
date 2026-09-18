from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_cors_origins
from .database import get_session_factory
from .models.exception_summary import ExceptionSummary
from .models.reports import Report
from .routes import (
    alerts, audit, duplicates, exception_summary, exceptions, mapping, obligations, reports, templates, upload,
)

logger = logging.getLogger(__name__)


def _fail_interrupted_processing_runs() -> None:
    """Fix spec Section 6.5: a report's background pipeline run (see
    routes/mapping.py) lives only in this process's memory. If the
    backend is killed or crashes mid-run (e.g. under memory pressure),
    that report is left stuck at status=PROCESSING forever with nothing
    to ever move it out of that state -- the frontend would show an
    indefinite spinner with no way to tell "still working" from "hung".
    On every startup (a clean restart included), any report still marked
    PROCESSING predates this process and its run is gone; mark it FAILED
    with a clear, specific reason so the UI shows a real failure state
    instead of spinning forever, and the user can re-run it."""
    db = get_session_factory()()
    try:
        stuck = db.query(Report).filter_by(status="PROCESSING").all()
        for report in stuck:
            report.status = "FAILED"
            report.processing_phase = None
            report.processing_error = (
                "Processing was interrupted (the server restarted or crashed while this "
                "report was being processed). Please re-run it."
            )
        if stuck:
            db.commit()
            logger.warning("Marked %d report(s) FAILED on startup (interrupted PROCESSING run): %s",
                            len(stuck), [r.id for r in stuck])
    finally:
        db.close()


def _fail_interrupted_summary_runs() -> None:
    """Same crash-resilience pattern as _fail_interrupted_processing_
    runs(), for the AI exception-summary background task (routes/
    exception_summary.py) -- a summary stuck at GENERATING from before a
    crash/restart would otherwise poll forever with the Exceptions page's
    "generating..." panel never resolving."""
    db = get_session_factory()()
    try:
        stuck = db.query(ExceptionSummary).filter_by(narrative_status="GENERATING").all()
        for summary in stuck:
            summary.narrative_status = "FAILED"
            summary.narrative_error = (
                "Narrative generation was interrupted (the server restarted or crashed). "
                "Click regenerate to try again."
            )
        if stuck:
            db.commit()
            logger.warning("Marked %d exception summary/summaries FAILED on startup (interrupted run): %s",
                            len(stuck), [s.id for s in stuck])
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_: FastAPI):
    _fail_interrupted_processing_runs()
    _fail_interrupted_summary_runs()
    yield


app = FastAPI(title="Truebind API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router_module in (
    upload, mapping, reports, exceptions, exception_summary, duplicates, obligations, alerts, audit, templates,
):
    app.include_router(router_module.router)


@app.get("/health")
def health_check() -> dict:
    return {"status": "ok"}
