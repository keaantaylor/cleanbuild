"""Observability: structured logs, request IDs, PII scrubbing, error
tracking and health endpoints.

- Every request carries a request ID (a well-formed incoming X-Request-ID is
  kept, anything else replaced), echoed as X-Request-ID and stamped on every
  log line written while handling it. An unhandled error's correlation_id
  is that request ID.
- Log lines are JSON when LOG_JSON is on (default in production): ts, level,
  logger, message, request_id and, for errors, exc_info.
- scrub() masks personal data and secrets in every log line and in every
  event sent to the error tracker: e-mail addresses, bearer tokens,
  key=value secrets, IBANs and long digit runs (card, account and phone
  numbers). Messages never carry cell values from uploaded files.
- Sentry runs only when SENTRY_DSN is set, with send_default_pii off and a
  before_send hook that drops request cookies, headers and bodies, keeps
  only the user id and scrubs every string.
- /healthz is liveness (no dependencies); /readyz checks the database and
  that the schema is at the Alembic head (503 otherwise). /health and
  /health/ready keep their original responses for existing probes.
"""

from __future__ import annotations

import contextvars
import json
import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .database import get_session_factory

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")

# ------------------------------------------------------------------ scrubbing

_SCRUBBERS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[redacted-email]"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+"), "Bearer [redacted-token]"),
    (
        re.compile(
            r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|authorization|access[_-]?key|client[_-]?secret"
            r"|session|cookie)\b(\s*[:=]\s*)\"?[^\s\"',;&]+"
        ),
        r"\1\2[redacted-secret]",
    ),
    (re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"), "[redacted-iban]"),
    (re.compile(r"(?<![\w.])\+?\d(?:[ -]?\d){8,}(?![\w.])"), "[redacted-number]"),
]


def scrub(value: str) -> str:
    for pattern, replacement in _SCRUBBERS:
        value = pattern.sub(replacement, value)
    return value


def _scrub_any(value: Any) -> Any:
    if isinstance(value, str):
        return scrub(value)
    if isinstance(value, dict):
        return {k: _scrub_any(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_scrub_any(v) for v in value]
    return value


# ------------------------------------------------------------------ logging


class ContextFilter(logging.Filter):
    """Stamps the request ID and scrubs the rendered message."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "request_id", None):
            record.request_id = request_id_var.get()
        record.msg = scrub(record.getMessage())
        record.args = None
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": scrub(record.getMessage()),
            "request_id": getattr(record, "request_id", None),
        }
        if record.exc_info:
            out["exc_info"] = scrub(self.formatException(record.exc_info))
        return json.dumps(out, default=str)


class TextFormatter(logging.Formatter):
    def __init__(self) -> None:
        super().__init__("%(asctime)s %(levelname)s %(name)s [%(request_id)s]: %(message)s")

    def formatException(self, ei: Any) -> str:  # noqa: N802 -- logging API name
        return scrub(super().formatException(ei))


def configure_logging(level: str = "INFO", json_lines: bool = False) -> None:
    """One handler on the root logger; safe to call more than once."""
    root = logging.getLogger()
    for h in list(root.handlers):
        if getattr(h, "_truebind", False):
            root.removeHandler(h)
    handler = logging.StreamHandler()
    handler._truebind = True  # type: ignore[attr-defined]
    handler.setFormatter(JsonFormatter() if json_lines else TextFormatter())
    handler.addFilter(ContextFilter())
    root.addHandler(handler)
    root.setLevel(level)
    for name in ("uvicorn.access",):  # replaced by truebind.access (request id, no query string)
        logging.getLogger(name).disabled = True


access_log = logging.getLogger("truebind.access")


def new_request_id(incoming: str | None) -> str:
    if incoming and _VALID_REQUEST_ID.fullmatch(incoming):
        return incoming
    return uuid.uuid4().hex


async def request_context(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    rid = new_request_id(request.headers.get(REQUEST_ID_HEADER))
    request.state.request_id = rid
    token = request_id_var.set(rid)
    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers[REQUEST_ID_HEADER] = rid
        return response
    finally:
        access_log.info(
            "%s %s %s %.1fms", request.method, request.url.path, status, (time.perf_counter() - started) * 1000
        )
        request_id_var.reset(token)


# ------------------------------------------------------------------ error tracking


def before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    request = event.get("request")
    if isinstance(request, dict):
        headers = request.get("headers") or {}
        event["request"] = {
            "method": request.get("method"),
            "url": scrub(str(request.get("url", ""))).split("?", 1)[0],
            "headers": {k: v for k, v in headers.items() if k.lower() in ("x-request-id", "content-type")},
        }
    user = event.get("user")
    if isinstance(user, dict):
        event["user"] = {"id": user["id"]} if "id" in user else {}
    for key in ("message", "exception", "extra", "breadcrumbs", "logentry", "tags", "contexts"):
        if key in event:
            event[key] = _scrub_any(event[key])
    return event


def init_sentry(
    dsn: str,
    environment: str,
    traces_sample_rate: float = 0.0,
    transport: Callable[[dict[str, Any]], None] | None = None,
) -> bool:
    """Start error tracking; False (and nothing started) without a DSN."""
    if not dsn:
        return False
    import sentry_sdk
    from sentry_sdk.envelope import Envelope
    from sentry_sdk.transport import Transport

    class _CallbackTransport(Transport):
        def __init__(self, callback: Callable[[dict[str, Any]], None]) -> None:
            super().__init__()
            self._callback = callback

        def capture_envelope(self, envelope: Envelope) -> None:
            event = envelope.get_event()
            if event is not None:
                self._callback(dict(event))

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        send_default_pii=False,
        traces_sample_rate=traces_sample_rate,
        before_send=before_send,  # type: ignore[arg-type]
        max_request_body_size="never",
        include_local_variables=False,
        transport=_CallbackTransport(transport) if transport is not None else None,
    )
    return True


def shutdown_sentry() -> None:
    import sentry_sdk

    client = sentry_sdk.get_client()
    client.close(timeout=2)
    sentry_sdk.get_global_scope().set_client(None)


# ------------------------------------------------------------------ health

router = APIRouter(tags=["health"])
_BACKEND = Path(__file__).resolve().parent.parent
_head_revision: str | None = None


def _alembic_head() -> str | None:
    global _head_revision
    if _head_revision is None:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        cfg = Config(str(_BACKEND / "alembic.ini"))
        cfg.set_main_option("script_location", str(_BACKEND / "migrations"))
        _head_revision = ScriptDirectory.from_config(cfg).get_current_head()
    return _head_revision


def readiness_checks() -> tuple[bool, dict[str, str]]:
    checks: dict[str, str] = {}
    try:
        db = get_session_factory()()
    except Exception:
        logging.getLogger("truebind").exception("readiness: database session unavailable")
        return False, {"database": "unavailable", "migrations": "unknown"}
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
        current = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
        checks["migrations"] = "ok" if current == _alembic_head() else "behind"
    except Exception:
        logging.getLogger("truebind").exception("readiness check failed")
        checks.setdefault("database", "unavailable")
        checks.setdefault("migrations", "unknown")
    finally:
        db.close()
    return all(v == "ok" for v in checks.values()), checks


@router.get("/healthz")
@router.get("/health")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
def readyz() -> JSONResponse:
    ok, checks = readiness_checks()
    return JSONResponse(
        status_code=200 if ok else 503, content={"status": "ready" if ok else "not ready", "checks": checks}
    )


@router.get("/health/ready")
def health_ready() -> JSONResponse:
    """Legacy probe: same checks as /readyz, original response shape."""
    ok, _checks = readiness_checks()
    if ok:
        return JSONResponse({"status": "ready"})
    return JSONResponse(status_code=503, content={"status": "database unavailable"})
