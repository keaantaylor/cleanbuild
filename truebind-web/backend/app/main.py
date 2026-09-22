from __future__ import annotations

import logging
import traceback
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_cors_origins
from .routes import alerts, audit, duplicates, exceptions, mapping, obligations, reports, templates, upload

logger = logging.getLogger("truebind")

app = FastAPI(title="Truebind API", version="0.1.0")

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


for router_module in (upload, mapping, reports, exceptions, duplicates, obligations, alerts, audit, templates):
    app.include_router(router_module.router)


@app.get("/health")
def health_check() -> dict:
    return {"status": "ok"}
