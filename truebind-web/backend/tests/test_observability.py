"""P1.8 -- observability: structured logs, request IDs, PII scrubbing,
error tracking, health endpoints.

Acceptance:
- every request gets a request ID (a valid incoming X-Request-ID is kept,
  anything else replaced) echoed in the response and present on every log
  line written while handling it;
- log lines are JSON when LOG_JSON is on, with timestamp, level, logger,
  message and request_id;
- personal data never reaches a log line or the error tracker: e-mail
  addresses, bearer tokens / secrets in key=value form, long digit runs
  (card, account, phone numbers) and IBANs are masked;
- an unhandled error returns a 500 whose correlation_id is the request ID,
  with no internal detail; the traceback goes to the log only;
- Sentry is off without SENTRY_DSN; with it, events go out with
  send_default_pii off, request cookies/headers/body dropped and every
  string scrubbed;
- /healthz answers without touching dependencies; /readyz checks the
  database and that migrations are at head, and returns 503 otherwise.
"""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator
from typing import Any

import pytest
from app import observability
from app.main import app
from conftest import Api
from fastapi import APIRouter
from fastapi.testclient import TestClient


@pytest.fixture
def json_log() -> Iterator[io.StringIO]:
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(observability.JsonFormatter())
    handler.addFilter(observability.ContextFilter())
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        yield buf
    finally:
        root.removeHandler(handler)


def _lines(buf: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(ln) for ln in buf.getvalue().splitlines() if ln.strip()]


@pytest.mark.parametrize(
    ("raw", "must_not_contain"),
    [
        ("user jane.doe@example.com signed in", "jane.doe@example.com"),
        ("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abc.def", "eyJhbGciOiJIUzI1NiJ9"),
        ("password=hunter2 token=abc123secret", "hunter2"),
        ("api_key: sk-live-1234567890", "sk-live-1234567890"),
        ("card 4111 1111 1111 1111 declined", "4111 1111 1111 1111"),
        ("call +44 20 7946 0958 now", "7946 0958"),
        ("IBAN IE29AIBK93115212345678 on file", "IE29AIBK93115212345678"),
    ],
)
def test_scrub_masks_personal_data(raw: str, must_not_contain: str) -> None:
    out = observability.scrub(raw)
    assert must_not_contain not in out
    assert "[redacted" in out


def test_scrub_keeps_ordinary_text() -> None:
    text = "report 7f3c processed 204 rows in 2.1 s (claim CLM-000123, 2024-03-15)"
    assert observability.scrub(text) == text


def test_request_id_is_echoed_and_on_every_log_line(json_log: io.StringIO) -> None:
    client = TestClient(app)
    r = client.get("/healthz", headers={"X-Request-ID": "abc-123.DEF_4"})
    assert r.headers["X-Request-ID"] == "abc-123.DEF_4"
    r2 = client.get("/healthz", headers={"X-Request-ID": "bad id with spaces\n"})
    rid = r2.headers["X-Request-ID"]
    assert rid != "bad id with spaces\n" and len(rid) == 32
    lines = [ln for ln in _lines(json_log) if ln.get("logger") == "truebind.access"]
    assert {ln["request_id"] for ln in lines} >= {"abc-123.DEF_4", rid}
    for ln in lines:
        assert {"ts", "level", "logger", "message", "request_id"} <= set(ln)


def test_log_lines_never_carry_an_email(api: Api, json_log: io.StringIO) -> None:
    api.post("/api/v1/auth/login", json={"email": "someone.private@example.org", "password": "wrong-password-x"})
    logging.getLogger("truebind.test").warning("lookup for %s failed", "someone.private@example.org")
    text = json_log.getvalue()
    assert "someone.private@example.org" not in text
    assert "[redacted-email]" in text


_boom = APIRouter()


@_boom.get("/__observability_boom")
def _explode() -> None:
    raise RuntimeError("secret detail for customer jane@example.com")


def test_unhandled_error_is_correlated_and_opaque(json_log: io.StringIO) -> None:
    if not any(getattr(r, "path", "") == "/__observability_boom" for r in app.routes):
        app.include_router(_boom)
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/__observability_boom", headers={"X-Request-ID": "req-boom-1"})
    assert r.status_code == 500
    body = r.json()
    assert body["correlation_id"] == "req-boom-1"
    assert "secret detail" not in r.text and "RuntimeError" not in r.text
    errors = [ln for ln in _lines(json_log) if ln["level"] == "ERROR" and ln.get("request_id") == "req-boom-1"]
    assert errors and "RuntimeError" in errors[0].get("exc_info", "")
    assert "jane@example.com" not in json_log.getvalue()


def test_sentry_is_off_without_a_dsn() -> None:
    assert observability.init_sentry(dsn="", environment="test") is False


def test_sentry_events_are_scrubbed_before_sending() -> None:
    event: dict[str, Any] = {
        "message": "failed for bob@example.com",
        "request": {
            "url": "https://api/x?email=bob@example.com",
            "cookies": {"tb_session": "s3cr3t"},
            "headers": {"Authorization": "Bearer abc.def.ghi", "X-Request-ID": "r1"},
            "data": {"password": "hunter2"},
        },
        "user": {"email": "bob@example.com", "ip_address": "10.0.0.1", "id": "u-1"},
        "exception": {"values": [{"type": "ValueError", "value": "IBAN IE29AIBK93115212345678 bad"}]},
        "extra": {"note": "token=abcdef123456"},
    }
    out = observability.before_send(event, {})
    assert out is not None
    dumped = json.dumps(out)
    for leaked in (
        "bob@example.com",
        "s3cr3t",
        "abc.def.ghi",
        "hunter2",
        "IE29AIBK93115212345678",
        "10.0.0.1",
        "abcdef123456",
    ):
        assert leaked not in dumped, leaked
    assert "cookies" not in out["request"] and "data" not in out["request"]
    assert out["user"] == {"id": "u-1"}


def test_sentry_sends_scrubbed_events_through_its_transport() -> None:
    sent: list[dict[str, Any]] = []
    assert observability.init_sentry(
        dsn="https://public@sentry.invalid/1", environment="test", transport=lambda e: sent.append(e)
    )
    try:
        import sentry_sdk

        try:
            raise ValueError("lookup failed for carol@example.com")
        except ValueError as exc:
            sentry_sdk.capture_exception(exc)
        sentry_sdk.flush(2)
    finally:
        observability.shutdown_sentry()
    assert sent, "the event reached the transport"
    assert "carol@example.com" not in json.dumps(sent, default=str)


def test_healthz_needs_no_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken() -> Any:
        raise RuntimeError("database down")

    monkeypatch.setattr(observability, "get_session_factory", broken)
    r = TestClient(app).get("/healthz")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_readyz_checks_database_and_migrations() -> None:
    r = TestClient(app).get("/readyz")
    assert r.status_code == 200, r.text
    checks = r.json()["checks"]
    assert checks["database"] == "ok"
    assert checks["migrations"] == "ok"


def test_readyz_is_503_when_the_database_is_down(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken() -> Any:
        raise RuntimeError("database down")

    monkeypatch.setattr(observability, "get_session_factory", broken)
    r = TestClient(app).get("/readyz")
    assert r.status_code == 503
    assert r.json()["checks"]["database"] == "unavailable"
    assert "database down" not in r.text
