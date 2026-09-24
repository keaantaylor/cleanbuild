"""Authentication, sessions, CSRF, lockout, rate limits, roles."""

from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.models._util import utcnow
from app.models.identity import AuthSession, Membership, User
from app.security.auth import COOKIE_NAME, token_hash
from conftest import PASSWORD, Api, simple_rows, xlsx_bytes


def _login(client: TestClient, email: str, password: str):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def test_signup_sets_httponly_session_and_returns_csrf(api):
    r = api.get("/api/v1/auth/me")
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "OWNER" and body["csrf_token"] == api.csrf
    fresh = TestClient(app)
    r = fresh.post("/api/v1/auth/signup", json={"email": "x@c.example", "password": PASSWORD,
                                                "display_name": "X", "organisation": "C"})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and f"{COOKIE_NAME}=" in cookie


def test_passwords_and_session_tokens_are_never_stored_in_clear(api, db):
    user = db.query(User).filter_by(email="owner@a.example").one()
    assert PASSWORD not in user.password_hash and user.password_hash.startswith("scrypt$")
    token = api.client.cookies.get(COOKIE_NAME)
    assert db.query(AuthSession).filter_by(token_hash=token).first() is None
    assert db.query(AuthSession).filter_by(token_hash=token_hash(token)).first() is not None


def test_weak_password_and_unknown_fields_rejected():
    c = TestClient(app)
    r = c.post("/api/v1/auth/signup", json={"email": "a@x.example", "password": "short",
                                            "display_name": "A", "organisation": "X"})
    assert r.status_code == 422
    r = c.post("/api/v1/auth/signup", json={"email": "a@x.example", "password": PASSWORD, "display_name": "A",
                                            "organisation": "X", "role": "ADMIN", "tenant_id": "t"})
    assert r.status_code == 422, "privilege fields in the body must be rejected, not ignored"
    assert "ADMIN" not in r.text, "422 must not echo submitted values"


def test_duplicate_signup_does_not_reveal_details(api):
    r = TestClient(app).post("/api/v1/auth/signup", json={"email": "owner@a.example", "password": PASSWORD,
                                                          "display_name": "B", "organisation": "B"})
    assert r.status_code == 409
    assert "owner@a.example" not in r.text


def test_unauthenticated_requests_are_rejected():
    c = TestClient(app)
    for method, url in [("get", "/api/v1/reports"), ("get", "/api/v1/alerts"), ("get", "/api/v1/audit"),
                        ("get", "/api/v1/templates"), ("get", "/api/v1/obligations")]:
        assert getattr(c, method)(url).status_code == 401, url
    c.cookies.set(COOKIE_NAME, "forged-token-value")
    assert c.get("/api/v1/reports").status_code == 401


def test_csrf_required_on_unsafe_methods(api):
    content = xlsx_bytes(simple_rows())
    no_header = api.client.post("/api/v1/reports/upload", files={"file": ("a.xlsx", content)})
    assert no_header.status_code == 403
    wrong = api.client.post("/api/v1/reports/upload", files={"file": ("a.xlsx", content)},
                            headers={"X-CSRF-Token": "not-the-token"})
    assert wrong.status_code == 403
    assert api.upload("a.xlsx", content).status_code == 202


def test_login_errors_are_indistinguishable_and_lockout_applies(api):
    c = TestClient(app)
    unknown = _login(c, "nobody@a.example", PASSWORD)
    wrong = _login(c, "owner@a.example", "wrong password here")
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()
    for _ in range(4):
        _login(c, "owner@a.example", "wrong password here")
    locked = _login(c, "owner@a.example", PASSWORD)
    assert locked.status_code == 423, "the correct password is refused while locked"


def test_lock_expires(api, db):
    user = db.query(User).filter_by(email="owner@a.example").one()
    user.locked_until = utcnow() - timedelta(seconds=1)
    db.commit()
    assert _login(TestClient(app), "owner@a.example", PASSWORD).status_code == 200


def test_login_rate_limited_per_account():
    c = TestClient(app)
    codes = [_login(c, "target@a.example", "guess number x").status_code for _ in range(12)]
    assert 429 in codes


def test_logout_revokes_session(api):
    assert api.post("/api/v1/auth/logout").status_code == 204
    api.client.cookies.clear()
    assert api.get("/api/v1/auth/me").status_code == 401


def test_revoked_token_cannot_be_replayed(api):
    token = api.client.cookies.get(COOKIE_NAME)
    api.post("/api/v1/auth/logout")
    c = TestClient(app)
    c.cookies.set(COOKIE_NAME, token)
    assert c.get("/api/v1/auth/me").status_code == 401


def test_expired_session_rejected(api, db):
    s = db.query(AuthSession).one()
    s.expires_at = utcnow() - timedelta(minutes=1)
    db.commit()
    assert api.get("/api/v1/auth/me").status_code == 401


def test_viewer_role_is_read_only(api, db):
    m = db.query(Membership).one()
    m.role = "VIEWER"
    db.commit()
    assert api.get("/api/v1/reports").status_code == 200
    assert api.upload("a.xlsx", xlsx_bytes(simple_rows())).status_code == 403


def test_signup_can_be_disabled(monkeypatch):
    import app.routes.auth as auth_routes
    monkeypatch.setattr(auth_routes, "ALLOW_SIGNUP", False)
    r = TestClient(app).post("/api/v1/auth/signup", json={"email": "z@z.example", "password": PASSWORD,
                                                          "display_name": "Z", "organisation": "Z"})
    assert r.status_code == 403


def test_login_after_signup_returns_new_csrf():
    Api(email="u@d.example", org="D")
    c = TestClient(app)
    r = _login(c, "U@D.example", PASSWORD)  # emails are case-insensitive
    assert r.status_code == 200 and r.json()["csrf_token"]
