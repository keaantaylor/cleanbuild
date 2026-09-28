"""P1.4b -- OIDC single sign-on: configuration and ID-token validation (no network).

Acceptance (unit level; the end-to-end flow against mock-oauth2-server is in
tests/integration/test_sso_mock_idp.py):
- owners/admins configure one OIDC connection per organisation (issuer,
  client id, write-only client secret, email domains, JIT provisioning,
  default role); the secret is encrypted at rest and never returned;
- an email domain can be claimed by one organisation only;
- sign-in starts from the user's e-mail domain and redirects to the IdP with
  state, nonce and PKCE (S256); unknown domains are refused;
- ID tokens are accepted only with a trusted signature (asymmetric algs),
  the configured issuer and audience, the nonce of this attempt and an
  unexpired lifetime.
"""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from app.main import app
from app.models.identity import SsoConnection
from app.security import crypto, oidc
from conftest import Api
from fastapi.testclient import TestClient
from joserfc import jwt
from joserfc.jwk import OctKey, RSAKey
from sqlalchemy.orm import Session

ISSUER = "https://idp.example/tenant-a"
DISCOVERY: dict[str, Any] = {
    "issuer": ISSUER,
    "authorization_endpoint": f"{ISSUER}/authorize",
    "token_endpoint": f"{ISSUER}/token",
    "jwks_uri": f"{ISSUER}/jwks",
}
CONFIG = {
    "issuer": ISSUER,
    "client_id": "truebind-a",
    "client_secret": "super-secret-client-value",
    "domains": ["corp-a.example"],
    "jit_provisioning": True,
    "default_role": "VIEWER",
    "enabled": True,
}


@pytest.fixture
def offline_idp(monkeypatch: pytest.MonkeyPatch) -> RSAKey:
    key = RSAKey.generate_key(2048, parameters={"kid": "k1"})
    monkeypatch.setattr(oidc, "discover", lambda issuer: DISCOVERY)
    monkeypatch.setattr(oidc, "fetch_jwks", lambda uri: {"keys": [key.as_dict(private=False)]})
    return key


def _token(key: Any, alg: str = "RS256", **overrides: Any) -> str:
    now = int(time.time())
    claims = {"iss": ISSUER, "aud": "truebind-a", "sub": "u1", "nonce": "n-1", "iat": now, "exp": now + 300}
    claims.update(overrides)
    return jwt.encode({"alg": alg, "kid": "k1"}, claims, key)


# ---------------------------------------------------------------- configuration


def test_owner_configures_sso_and_secret_is_write_only(api: Api, db: Session) -> None:
    r = api.patch("/api/v1/org/sso", json=CONFIG)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["has_client_secret"] is True and "client_secret" not in body
    assert body["domains"] == ["corp-a.example"] and body["callback_url"].endswith("/api/v1/auth/sso/callback")
    got = api.get("/api/v1/org/sso").json()
    assert "super-secret-client-value" not in str(got)
    row = db.query(SsoConnection).filter_by(tenant_id=api.me["tenant"]["id"]).one()
    assert row.client_secret_enc is not None and row.client_secret_enc != CONFIG["client_secret"]
    assert crypto.decrypt("sso-client-secret", row.client_secret_enc) == CONFIG["client_secret"]
    # update without re-sending the secret keeps it
    assert api.patch("/api/v1/org/sso", json={**CONFIG, "client_secret": None}).json()["has_client_secret"] is True
    audit = api.get("/api/v1/audit").json()["items"]
    assert any(e["action_type"] == "SSO_CONFIG_CHANGED" for e in audit)
    assert "super-secret-client-value" not in str(audit)


def test_domains_are_claimed_once_and_config_needs_org_manage(api: Api, api_b: Api) -> None:
    assert api.patch("/api/v1/org/sso", json=CONFIG).status_code == 200
    clash = api_b.patch("/api/v1/org/sso", json={**CONFIG, "issuer": "https://other.example"})
    assert clash.status_code == 409
    assert api.patch("/api/v1/org/sso", json={**CONFIG, "default_role": "OWNER"}).status_code == 422
    token = api.post("/api/v1/org/invitations", json={"email": "an@a.example", "role": "ANALYST"}).json()[
        "accept_token"
    ]
    c = TestClient(app)
    me = c.post("/api/v1/auth/invitations/accept", json={"token": token, "display_name": "A", "password": "x" * 14})
    c.headers["X-CSRF-Token"] = me.json()["csrf_token"]
    assert c.patch("/api/v1/org/sso", json=CONFIG).status_code == 403
    assert api.delete("/api/v1/org/sso").status_code == 204
    assert api_b.patch("/api/v1/org/sso", json={**CONFIG, "issuer": "https://other.example"}).status_code == 200


def test_start_redirects_with_state_nonce_and_pkce(api: Api, offline_idp: RSAKey) -> None:
    api.patch("/api/v1/org/sso", json=CONFIG)
    c = TestClient(app)
    r = c.get("/api/v1/auth/sso/start", params={"email": "alice@CORP-A.example"}, follow_redirects=False)
    assert r.status_code == 302, r.text
    loc = urlparse(r.headers["location"])
    q = parse_qs(loc.query)
    assert f"{loc.scheme}://{loc.netloc}{loc.path}" == DISCOVERY["authorization_endpoint"]
    assert q["client_id"] == ["truebind-a"] and q["response_type"] == ["code"]
    assert {"state", "nonce", "code_challenge"} <= set(q) and q["code_challenge_method"] == ["S256"]
    assert "openid" in q["scope"][0].split()
    assert "tb_sso" in c.cookies
    unknown = c.get("/api/v1/auth/sso/start", params={"email": "x@unknown.example"}, follow_redirects=False)
    assert unknown.status_code == 404
    api.patch("/api/v1/org/sso", json={**CONFIG, "enabled": False})
    assert (
        c.get("/api/v1/auth/sso/start", params={"email": "a@corp-a.example"}, follow_redirects=False).status_code == 404
    )


# ---------------------------------------------------------------- ID token validation


def _conn() -> oidc.Connection:
    return oidc.Connection(issuer=ISSUER, client_id="truebind-a")


def test_valid_id_token_is_accepted(offline_idp: RSAKey) -> None:
    claims = oidc.validate_id_token(_token(offline_idp, email="a@corp-a.example"), _conn(), nonce="n-1")
    assert claims["sub"] == "u1" and claims["email"] == "a@corp-a.example"


@pytest.mark.parametrize(
    "overrides",
    [
        {"iss": "https://evil.example"},
        {"aud": "someone-else"},
        {"nonce": "replayed-nonce"},
        {"exp": int(time.time()) - 60},
    ],
)
def test_id_token_claims_are_enforced(offline_idp: RSAKey, overrides: dict[str, Any]) -> None:
    with pytest.raises(oidc.OidcError):
        oidc.validate_id_token(_token(offline_idp, **overrides), _conn(), nonce="n-1")


def test_id_token_signature_and_algorithm_are_enforced(offline_idp: RSAKey) -> None:
    other = RSAKey.generate_key(2048, parameters={"kid": "k1"})
    with pytest.raises(oidc.OidcError):
        oidc.validate_id_token(_token(other), _conn(), nonce="n-1")
    hmac_key = OctKey.generate_key(256)
    with pytest.raises(oidc.OidcError):
        oidc.validate_id_token(_token(hmac_key, alg="HS256"), _conn(), nonce="n-1")
    unsigned = _token(offline_idp).rsplit(".", 1)[0] + "."
    with pytest.raises(oidc.OidcError):
        oidc.validate_id_token(unsigned, _conn(), nonce="n-1")
