"""P1.4a -- TOTP two-factor authentication, enforceable per organisation.

Acceptance:
- a user sets up TOTP (secret + otpauth URI), confirms it with a code and
  receives 10 one-time recovery codes; the secret is stored encrypted;
- once enabled, the password alone no longer creates a session: login
  returns a short-lived challenge that a TOTP code or recovery code completes;
- wrong codes are rejected and count towards account lockout; a code cannot
  be replayed; a recovery code works once;
- an organisation that requires 2FA confines members without it to
  setting it up (403 elsewhere) until they have;
- disabling needs a valid code and is refused while the organisation
  requires 2FA; enabling signs the user out of their other sessions;
- every MFA event is audited.
"""

from __future__ import annotations

import time
from typing import Any

import pyotp
import pytest
from app.main import app
from app.models.identity import UserMfa
from app.security import crypto
from conftest import PASSWORD, Api
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def _enable(api: Api) -> tuple[str, list[str]]:
    r = api.post("/api/v1/auth/2fa/setup")
    assert r.status_code == 200, r.text
    secret = r.json()["secret"]
    assert r.json()["otpauth_uri"].startswith("otpauth://totp/")
    r = api.post("/api/v1/auth/2fa/enable", json={"code": pyotp.TOTP(secret).now()})
    assert r.status_code == 200, r.text
    codes = r.json()["recovery_codes"]
    return secret, codes


def _login(email: str = "owner@a.example", password: str = PASSWORD) -> tuple[TestClient, Any]:
    c = TestClient(app)
    r = c.post("/api/v1/auth/login", json={"email": email, "password": password})
    return c, r


def _next_step_code(secret: str) -> str:
    """A code for the NEXT 30 s step: valid (window 1) and not yet used."""
    return pyotp.TOTP(secret).at(int(time.time()) + 30)


def test_setup_enable_and_login_with_totp(api: Api, db: Session) -> None:
    secret, codes = _enable(api)
    assert len(codes) == 10 and len(set(codes)) == 10
    me = api.get("/api/v1/auth/me").json()
    assert me["mfa"] == {"enabled": True, "required": False, "setup_required": False}

    row = db.get(UserMfa, api.me["user"]["id"])
    assert row is not None and secret not in row.secret_enc and crypto.decrypt("totp", row.secret_enc) == secret
    assert all(code not in str(row.recovery_code_hashes) for code in codes)

    c, r = _login()
    assert r.status_code == 200 and r.json()["mfa_required"] is True
    assert "tb_session" not in c.cookies, "the password alone must not create a session"
    token = r.json()["mfa_token"]
    bad = c.post("/api/v1/auth/2fa/verify", json={"mfa_token": token, "code": "000000"})
    assert bad.status_code == 401
    ok = c.post("/api/v1/auth/2fa/verify", json={"mfa_token": token, "code": _next_step_code(secret)})
    assert ok.status_code == 200, ok.text
    assert ok.json()["user"]["email"] == "owner@a.example"
    assert c.get("/api/v1/reports").status_code == 200


def test_codes_cannot_be_replayed(api: Api) -> None:
    secret, _ = _enable(api)
    code = _next_step_code(secret)
    c1, r1 = _login()
    assert (
        c1.post("/api/v1/auth/2fa/verify", json={"mfa_token": r1.json()["mfa_token"], "code": code}).status_code == 200
    )
    c2, r2 = _login()
    assert (
        c2.post("/api/v1/auth/2fa/verify", json={"mfa_token": r2.json()["mfa_token"], "code": code}).status_code == 401
    )


def test_recovery_code_works_once(api: Api) -> None:
    _, codes = _enable(api)
    c1, r1 = _login()
    ok = c1.post("/api/v1/auth/2fa/verify", json={"mfa_token": r1.json()["mfa_token"], "recovery_code": codes[0]})
    assert ok.status_code == 200
    c2, r2 = _login()
    again = c2.post("/api/v1/auth/2fa/verify", json={"mfa_token": r2.json()["mfa_token"], "recovery_code": codes[0]})
    assert again.status_code == 401
    actions = [e["action_type"] for e in api.get("/api/v1/audit").json()["items"]]
    assert "MFA_RECOVERY_CODE_USED" in actions


def test_challenge_tokens_expire_and_are_bound(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    secret, _ = _enable(api)
    c, r = _login()
    token = r.json()["mfa_token"]
    assert c.post("/api/v1/auth/2fa/verify", json={"mfa_token": token + "x", "code": "123456"}).status_code == 401
    real_time = time.time
    monkeypatch.setattr(time, "time", lambda: real_time() + 600)
    expired = c.post("/api/v1/auth/2fa/verify", json={"mfa_token": token, "code": pyotp.TOTP(secret).now()})
    assert expired.status_code == 401


def test_wrong_codes_lock_the_account(api: Api) -> None:
    _enable(api)
    for _ in range(5):
        c, r = _login()
        assert (
            c.post("/api/v1/auth/2fa/verify", json={"mfa_token": r.json()["mfa_token"], "code": "000000"}).status_code
            == 401
        )
    c, r = _login()
    assert r.status_code == 423, "locked after repeated wrong codes, even with the right password"


def test_org_enforcement_confines_members_until_set_up(api: Api) -> None:
    token = api.post("/api/v1/org/invitations", json={"email": "m@a.example", "role": "ANALYST"}).json()["accept_token"]
    member = TestClient(app)
    r = member.post("/api/v1/auth/invitations/accept", json={"token": token, "display_name": "M", "password": PASSWORD})
    member.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    _enable(api)  # the owner must use 2FA before requiring it
    assert api.patch("/api/v1/org", json={"require_2fa": True}).status_code == 200

    blocked = member.get("/api/v1/reports")
    assert blocked.status_code == 403 and blocked.headers.get("X-TrueBind-Reason") == "mfa_setup_required"
    assert member.get("/api/v1/auth/me").json()["mfa"]["setup_required"] is True
    setup = member.post("/api/v1/auth/2fa/setup").json()
    enabled = member.post("/api/v1/auth/2fa/enable", json={"code": pyotp.TOTP(setup["secret"]).now()})
    assert enabled.status_code == 200
    assert member.get("/api/v1/reports").status_code == 200, "the session that completed setup may continue"
    # disabling is refused while the organisation requires it
    off = member.post("/api/v1/auth/2fa/disable", json={"code": _next_step_code(setup["secret"])})
    assert off.status_code == 409


def test_disable_needs_a_code_and_enable_revokes_other_sessions(api: Api) -> None:
    other, _ = _login()
    assert other.get("/api/v1/reports").status_code == 200
    secret, _ = _enable(api)
    assert other.get("/api/v1/reports").status_code == 401, "other sessions are signed out on enable"
    assert api.post("/api/v1/auth/2fa/disable", json={"code": "000000"}).status_code == 401
    assert api.post("/api/v1/auth/2fa/disable", json={"code": _next_step_code(secret)}).status_code == 204
    assert api.get("/api/v1/auth/me").json()["mfa"]["enabled"] is False
    _, r = _login()
    assert "mfa_required" not in r.json() and r.json()["user"]["email"] == "owner@a.example"
    actions = [e["action_type"] for e in api.get("/api/v1/audit").json()["items"]]
    for expected in ("MFA_SETUP_STARTED", "MFA_ENABLED", "MFA_DISABLED"):
        assert expected in actions


def test_setup_is_refused_when_already_enabled(api: Api) -> None:
    _enable(api)
    assert api.post("/api/v1/auth/2fa/setup").status_code == 409
