"""TB-004/WP-0: no unhandled exception may present to the client as a
dropped connection. A route that raises something nobody wrapped in a
try/except must still come back as a readable, correlatable 500 -- with
CORS headers attached, so a real crash never masquerades as the
"No 'Access-Control-Allow-Origin' header" red herring this defect is
named for -- and the server must still be alive and serving immediately
afterwards."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.main import app

_boom_router = APIRouter(prefix="/api/v1/_test", tags=["test"])


@_boom_router.get("/boom")
def boom() -> None:
    raise RuntimeError("deliberately unhandled, for TB-004 regression coverage")


app.include_router(_boom_router)


def test_unhandled_exception_returns_structured_500_with_correlation_id_and_cors() -> None:
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/v1/_test/boom", headers={"Origin": "http://localhost:3000"})

    assert resp.status_code == 500
    body = resp.json()
    assert "correlation_id" in body["error"] and len(body["error"]["correlation_id"]) > 0
    assert body["error"]["reason_code"] == "internal_error"
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"
    print(f"OK: unhandled exception returned 500 with correlation_id={body['error']['correlation_id']!r} and CORS header")


def test_server_still_serves_after_an_unhandled_exception() -> None:
    client = TestClient(app, raise_server_exceptions=False)
    client.get("/api/v1/_test/boom")  # crash one request
    health = client.get("/health")  # process must still be alive and serving
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    print("OK: process remains alive and serving after an unhandled exception")


if __name__ == "__main__":
    test_unhandled_exception_returns_structured_500_with_correlation_id_and_cors()
    test_server_still_serves_after_an_unhandled_exception()
    print("\nException-containment regression tests PASSED.")
