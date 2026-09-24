"""HTTP-level hardening: headers, error shapes, no internal leakage."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.main import app


def test_security_headers_present(api):
    r = api.get("/api/v1/auth/me")
    for h in ("X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy", "Content-Security-Policy",
              "Cache-Control"):
        assert h in r.headers, h
    assert r.headers["Cache-Control"] == "no-store"


def test_cors_rejects_unknown_origins(api):
    r = api.client.options("/api/v1/reports", headers={"Origin": "https://evil.example",
                                                       "Access-Control-Request-Method": "GET"})
    assert r.headers.get("access-control-allow-origin") != "https://evil.example"
    ok = api.client.options("/api/v1/reports", headers={"Origin": "http://localhost:3000",
                                                        "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_wildcard_cors_refused_at_startup(monkeypatch):
    import pytest
    from app.config import get_cors_origins
    monkeypatch.setenv("CORS_ORIGINS", "*")
    with pytest.raises(RuntimeError):
        get_cors_origins()


def test_unhandled_error_is_generic_with_correlation_id():
    router = APIRouter()

    @router.get("/__boom")
    def boom():
        raise RuntimeError("secret internal detail /srv/path")

    app.include_router(router)
    try:
        r = TestClient(app, raise_server_exceptions=False).get("/__boom")
        assert r.status_code == 500
        body = r.json()
        assert body["correlation_id"] and "secret" not in r.text and "Traceback" not in r.text
    finally:
        app.router.routes = [rt for rt in app.router.routes if getattr(rt, "path", "") != "/__boom"]


def test_validation_errors_do_not_echo_input(api):
    r = api.post("/api/v1/templates", json={"name": "x" * 300, "field_mappings": {"a": "CR0104M"},
                                            "secret_field": "hunter2-value"})
    assert r.status_code == 422
    assert "hunter2-value" not in r.text and "xxxxxxxxxx" not in r.text


def test_upload_without_content_length_is_refused(api):
    def gen():
        yield b"--x\r\n"
    r = api.client.post("/api/v1/reports/upload", content=gen(),
                        headers={"X-CSRF-Token": api.csrf, "Content-Type": "multipart/form-data; boundary=x"})
    assert r.status_code == 411


def test_no_secret_material_in_responses(api, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key-should-never-appear")
    for url in ["/api/v1/auth/me", "/api/v1/reports", "/api/v1/audit", "/health"]:
        r = api.get(url)
        assert "test-anthropic-key" not in r.text and "password_hash" not in r.text and "token_hash" not in r.text


def test_readiness_endpoint():
    assert TestClient(app).get("/health/ready").json() == {"status": "ready"}


def test_hosted_postgres_urls_get_the_psycopg_driver(monkeypatch):
    from app.config import get_database_url
    for given in ("postgres://u:p@db:5432/truebind", "postgresql://u:p@db:5432/truebind"):
        monkeypatch.setenv("DATABASE_URL", given)
        assert get_database_url() == "postgresql+psycopg://u:p@db:5432/truebind"
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db/x")
    assert get_database_url() == "postgresql+psycopg://u:p@db/x"
