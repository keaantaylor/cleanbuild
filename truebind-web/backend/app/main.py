from __future__ import annotations

import logging
import traceback
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_cors_origins
from .database import get_session_factory
from .models.exception_summary import ExceptionSummary
from .models.reports import Report
from .routes import (
    alerts, audit, duplicates, exception_summary, exceptions, mapping, obligations, reports, templates, upload,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("truebind")


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

_cors_origins = get_cors_origins()

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _cors_headers_for(request: Request) -> dict[str, str]:
    """TB-004(c): CORSMiddleware only ever touches a *successful* ASGI
    response cycle. An exception that reaches this handler has already
    unwound past that middleware, so without repeating its header logic
    here the browser reports a same-origin-policy/CORS failure for what
    is actually a server crash -- exactly the misdiagnosis this defect
    described ("net::ERR_FAILED ... No Access-Control-Allow-Origin
    header", when the real fault was an unhandled exception with no
    response body at all). "*" in allow_origins matches everything, same
    as CORSMiddleware's own convention."""
    origin = request.headers.get("origin")
    if not origin:
        return {}
    if "*" in _cors_origins or origin in _cors_origins:
        return {"Access-Control-Allow-Origin": origin, "Access-Control-Allow-Credentials": "true"}
    return {}


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """TB-004: no exception raised anywhere in a request -- ingestion or
    otherwise -- may present to the client as a dropped connection. Every
    route already has its own try/except for the failure modes it knows
    about (a bad upload, a pipeline crash on a background thread); this
    is the backstop for everything else, so a defect nobody anticipated
    still comes back as a readable, correlatable 500 instead of the
    CORS-shaped red herring this defect is named for."""
    correlation_id = uuid.uuid4().hex
    logger.error(
        "unhandled exception [%s] on %s %s:\n%s",
        correlation_id, request.method, request.url.path, "".join(traceback.format_exception(exc)),
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "correlation_id": correlation_id,
                "reason_code": "internal_error",
                "message": "An unexpected error occurred. Reference the correlation ID when reporting this.",
            }
        },
        headers=_cors_headers_for(request),
    )


for router_module in (
    upload, mapping, reports, exceptions, exception_summary, duplicates, obligations, alerts, audit, templates,
):
    app.include_router(router_module.router)


@app.get("/health")
def health_check() -> dict:
    return {"status": "ok"}
