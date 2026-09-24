from __future__ import annotations

import logging
import traceback
import uuid
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import EMBEDDED_WORKER, ENV, IS_PRODUCTION, MAX_UPLOAD_BYTES, get_cors_origins
from .database import get_session_factory, set_tenant
from .models._util import utcnow
from .models.exception_summary import ExceptionSummary
from .models.identity import Tenant
from .routes import alerts, audit, auth, exception_summary, findings, mapping, obligations, reports, system, templates

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("truebind")


def _fail_stale_summaries() -> None:
    """AI narratives run as in-process background tasks; any still marked
    GENERATING after a restart will never finish -- mark them FAILED so the
    UI offers "regenerate" instead of polling forever. (Processing jobs do
    not need this: the worker's lease/reaper recovers them.)"""
    db = get_session_factory()()
    try:
        cutoff = utcnow() - timedelta(minutes=5)
        for (tid,) in db.query(Tenant.id).all():
            set_tenant(db, tid)
            n = (db.query(ExceptionSummary)
                 .filter(ExceptionSummary.narrative_status == "GENERATING", ExceptionSummary.created_at < cutoff)
                 .update({"narrative_status": "FAILED",
                          "narrative_error": "Generation was interrupted by a restart. Regenerate to try again."},
                         synchronize_session=False))
            db.commit()
            if n:
                logger.warning("marked %d interrupted AI summary run(s) FAILED for tenant %s", n, tid)
    except Exception:  # noqa: BLE001 -- e.g. tables not migrated yet; never block startup
        logger.exception("startup summary sweep skipped")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_: FastAPI):
    _fail_stale_summaries()
    from .config import describe_database_url
    logger.info("TrueBind API starting: env=%s database=%s embedded_worker=%s", ENV, describe_database_url(),
                EMBEDDED_WORKER)
    if not EMBEDDED_WORKER:
        logger.warning("Embedded worker is OFF: uploads will stay queued unless `python -m app.worker` is running "
                       "against the same database.")
    if EMBEDDED_WORKER:
        from .worker import start_embedded, stop_embedded
        start_embedded()
        yield
        stop_embedded()
    else:
        yield


app = FastAPI(title="TrueBind API", version="0.2.0", lifespan=lifespan,
              docs_url=None if IS_PRODUCTION else "/docs", redoc_url=None,
              openapi_url=None if IS_PRODUCTION else "/openapi.json")

_cors_origins = get_cors_origins()
app.add_middleware(CORSMiddleware, allow_origins=_cors_origins, allow_credentials=True,
                   allow_methods=["GET", "POST", "PATCH", "DELETE"],
                   allow_headers=["Content-Type", "X-CSRF-Token"], max_age=600)

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cache-Control": "no-store",
}
_UPLOAD_OVERHEAD = 1024 * 1024  # multipart framing


@app.middleware("http")
async def security_and_size(request: Request, call_next):
    if request.method == "POST" and request.url.path.endswith("/reports/upload"):
        length = request.headers.get("content-length")
        if length is None:
            return JSONResponse(status_code=411, content={"detail": "Uploads must declare Content-Length."},
                                headers=_cors_headers_for(request))
        if not length.isdigit() or int(length) > MAX_UPLOAD_BYTES + _UPLOAD_OVERHEAD:
            return JSONResponse(status_code=413, content={
                "detail": f"The file is larger than the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit."},
                headers=_cors_headers_for(request))
    response = await call_next(request)
    for k, v in _SECURITY_HEADERS.items():
        response.headers.setdefault(k, v)
    if IS_PRODUCTION:
        response.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
    return response


def _cors_headers_for(request: Request) -> dict[str, str]:
    origin = request.headers.get("origin")
    if origin and origin in _cors_origins:
        return {"Access-Control-Allow-Origin": origin, "Access-Control-Allow-Credentials": "true", "Vary": "Origin"}
    return {}


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """422 without echoing the submitted values back (output minimisation)."""
    errors = [{"loc": [str(p) for p in e.get("loc", ())][:6], "msg": str(e.get("msg", ""))[:200]}
              for e in exc.errors()[:20]]
    return JSONResponse(status_code=422, content={"detail": "The request is invalid.", "errors": errors},
                        headers=_cors_headers_for(request))


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Backstop: a readable, correlatable 500 with no internal detail; the
    traceback goes to the server log only."""
    correlation_id = uuid.uuid4().hex
    logger.error("unhandled exception [%s] on %s %s:\n%s", correlation_id, request.method, request.url.path,
                 "".join(traceback.format_exception(exc)))
    return JSONResponse(status_code=500, content={
        "detail": "An unexpected error occurred.", "correlation_id": correlation_id}, headers=_cors_headers_for(request))


for router_module in (auth, reports, mapping, findings, exception_summary, obligations, alerts, audit, templates,
                      system):
    app.include_router(router_module.router)


@app.get("/health")
def health_check() -> dict:
    return {"status": "ok"}


@app.get("/health/ready")
def readiness() -> JSONResponse:
    from sqlalchemy import text
    db = get_session_factory()()
    try:
        db.execute(text("SELECT 1"))
        return JSONResponse({"status": "ready"})
    except Exception:  # noqa: BLE001
        return JSONResponse(status_code=503, content={"status": "database unavailable"})
    finally:
        db.close()
