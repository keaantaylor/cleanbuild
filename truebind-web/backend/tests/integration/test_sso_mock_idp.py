"""P1.4b -- OIDC sign-in end to end against mock-oauth2-server (verify --full).

The mock IdP's login form lets the test choose the subject and the claims it
asserts, so each case controls exactly what the identity provider says.
"""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from app.main import app
from conftest import Api
from fastapi.testclient import TestClient
from integration_env import IT, service_url

pytestmark = [pytest.mark.integration, pytest.mark.skipif(not IT, reason="integration: run via verify.py --full")]


def _configure(api: Api, **overrides: object) -> None:
    body = {
        "issuer": service_url("OIDC_ISSUER"),
        "client_id": "truebind-a",
        "client_secret": "mock-secret",
        "domains": ["corp-a.example"],
        "jit_provisioning": True,
        "default_role": "VIEWER",
        "enabled": True,
        **overrides,
    }
    r = api.patch("/api/v1/org/sso", json=body)
    assert r.status_code == 200, r.text


def _sign_in(email: str, claims: dict[str, object]) -> tuple[TestClient, str]:
    """Run the browser side of the flow; returns the client and where the
    callback redirected it."""
    c = TestClient(app)
    start = c.get("/api/v1/auth/sso/start", params={"email": email}, follow_redirects=False)
    assert start.status_code == 302, start.text
    idp = httpx.post(
        start.headers["location"],
        data={"username": str(claims.get("sub", email)), "claims": json.dumps(claims)},
        follow_redirects=False,
        timeout=10,
    )
    assert idp.status_code == 302, idp.text
    back = urlparse(idp.headers["location"])
    assert back.path == "/api/v1/auth/sso/callback"
    cb = c.get("/api/v1/auth/sso/callback", params=parse_qs(back.query), follow_redirects=False)
    assert cb.status_code == 303, cb.text
    return c, cb.headers["location"]


def test_jit_sign_in_creates_member_with_default_role(api: Api) -> None:
    _configure(api)
    c, location = _sign_in("alice@corp-a.example", {"email": "alice@corp-a.example", "email_verified": True})
    assert location.endswith("/overview")
    me = c.get("/api/v1/auth/me").json()
    assert me["user"]["email"] == "alice@corp-a.example" and me["role"] == "VIEWER"
    assert me["tenant"]["id"] == api.me["tenant"]["id"]
    audit = api.get("/api/v1/audit").json()["items"]
    login = next(e for e in audit if e["action_type"] == "LOGIN_SUCCEEDED" and e["actor"] == "alice@corp-a.example")
    assert login["after_value"]["method"] == "sso"
    assert any(e["action_type"] == "SSO_USER_PROVISIONED" for e in audit)


def test_sso_session_satisfies_org_2fa_requirement(api: Api) -> None:
    _configure(api)
    import pyotp

    setup = api.post("/api/v1/auth/2fa/setup").json()
    api.post("/api/v1/auth/2fa/enable", json={"code": pyotp.TOTP(setup["secret"]).now()})
    assert api.patch("/api/v1/org", json={"require_2fa": True}).status_code == 200
    c, _ = _sign_in("bob@corp-a.example", {"email": "bob@corp-a.example", "email_verified": True})
    assert c.get("/api/v1/reports").status_code == 200, "the IdP is responsible for MFA on SSO sign-ins"


@pytest.mark.parametrize(
    ("email", "claims", "jit", "error"),
    [
        ("mallory@corp-a.example", {"email": "mallory@other.example", "email_verified": True}, True, "domain_mismatch"),
        ("carol@corp-a.example", {"email": "carol@corp-a.example", "email_verified": False}, True, "email_unverified"),
        ("dave@corp-a.example", {"email": "dave@corp-a.example", "email_verified": True}, False, "not_provisioned"),
    ],
)
def test_refused_sign_ins_create_no_session(
    api: Api, email: str, claims: dict[str, object], jit: bool, error: str
) -> None:
    _configure(api, jit_provisioning=jit)
    c, location = _sign_in(email, claims)
    assert f"sso_error={error}" in location
    assert c.get("/api/v1/auth/me").status_code == 401


def test_existing_account_elsewhere_is_not_captured_by_jit(api: Api, api_b: Api) -> None:
    """A user who already has an account (in org B) is not silently added to
    org A just because A's IdP asserts their address."""
    _configure(api, domains=["b.example"])
    c, location = _sign_in("owner@b.example", {"email": "owner@b.example", "email_verified": True})
    assert "sso_error=not_a_member" in location
    assert c.get("/api/v1/auth/me").status_code == 401


def test_callback_without_the_start_cookie_is_refused(api: Api) -> None:
    _configure(api)
    c = TestClient(app)
    start = c.get("/api/v1/auth/sso/start", params={"email": "e@corp-a.example"}, follow_redirects=False)
    idp = httpx.post(
        start.headers["location"],
        data={"username": "e", "claims": json.dumps({"email": "e@corp-a.example", "email_verified": True})},
        follow_redirects=False,
        timeout=10,
    )
    back = urlparse(idp.headers["location"])
    stranger = TestClient(app)  # a different browser: no tb_sso cookie
    cb = stranger.get("/api/v1/auth/sso/callback", params=parse_qs(back.query), follow_redirects=False)
    assert cb.status_code == 303 and "sso_error=invalid_state" in cb.headers["location"]
    tampered = dict(parse_qs(back.query))
    tampered["state"] = ["forged"]
    cb2 = c.get("/api/v1/auth/sso/callback", params=tampered, follow_redirects=False)
    assert "sso_error=invalid_state" in cb2.headers["location"]
