"""OpenID Connect relying party (authorization code flow + PKCE).

Works with any standards-compliant issuer (Microsoft Entra ID, WorkOS,
Okta, Google Workspace...). Tested against mock-oauth2-server.

- Discovery document and JWKS are fetched over HTTPS (HTTP allowed outside
  production for local test IdPs) and cached.
- The authorization request carries state, nonce and an S256 PKCE challenge.
- ID tokens are accepted only when signed with an asymmetric algorithm by a
  key from the issuer's JWKS, with the configured issuer and audience, this
  attempt's nonce, a subject and an unexpired lifetime (60 s clock leeway).
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from typing import Any

import httpx
from authlib.integrations.httpx_client import OAuth2Client
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import KeySet
from joserfc.jwt import JWTClaimsRegistry

from ..settings import get_settings

ALGORITHMS = ["RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512"]
SCOPES = "openid email profile"
_CACHE_TTL_S = 600
_HTTP_TIMEOUT_S = 10
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


class OidcError(Exception):
    """Any failure talking to the IdP or validating what it returned."""


@dataclass(frozen=True)
class Connection:
    issuer: str
    client_id: str
    client_secret: str = ""
    token_auth_method: str = "client_secret_post"  # noqa: S105 -- method name, not a secret


@dataclass(frozen=True)
class AuthorizationRequest:
    url: str
    state: str
    nonce: str
    code_verifier: str


def _get_json(url: str) -> dict[str, Any]:
    if not url.startswith("https://") and get_settings().is_production:
        raise OidcError("identity provider URLs must use HTTPS")
    cached = _cache.get(url)
    if cached and cached[0] > time.monotonic():
        return cached[1]
    try:
        r = httpx.get(url, timeout=_HTTP_TIMEOUT_S, follow_redirects=False)
        r.raise_for_status()
        doc = r.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise OidcError(f"could not fetch {url}") from exc
    if not isinstance(doc, dict):
        raise OidcError(f"unexpected document at {url}")
    _cache[url] = (time.monotonic() + _CACHE_TTL_S, doc)
    return doc


def discover(issuer: str) -> dict[str, Any]:
    doc = _get_json(issuer.rstrip("/") + "/.well-known/openid-configuration")
    if str(doc.get("issuer", "")).rstrip("/") != issuer.rstrip("/"):
        raise OidcError("discovery document names a different issuer")
    for key in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
        if not isinstance(doc.get(key), str):
            raise OidcError(f"discovery document has no {key}")
    return doc


def fetch_jwks(uri: str) -> dict[str, Any]:
    return _get_json(uri)


def _client(conn: Connection, redirect_uri: str) -> OAuth2Client:
    return OAuth2Client(
        client_id=conn.client_id,
        client_secret=conn.client_secret or None,
        scope=SCOPES,
        redirect_uri=redirect_uri,
        code_challenge_method="S256",
        token_endpoint_auth_method=conn.token_auth_method,
        timeout=_HTTP_TIMEOUT_S,
    )


def authorization_request(conn: Connection, redirect_uri: str) -> AuthorizationRequest:
    doc = discover(conn.issuer)
    state, nonce, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(24), secrets.token_urlsafe(48)
    with _client(conn, redirect_uri) as client:
        url, _ = client.create_authorization_url(
            doc["authorization_endpoint"], state=state, nonce=nonce, code_verifier=verifier
        )
    return AuthorizationRequest(url=url, state=state, nonce=nonce, code_verifier=verifier)


def exchange_code(conn: Connection, redirect_uri: str, code: str, code_verifier: str) -> dict[str, Any]:
    doc = discover(conn.issuer)
    try:
        with _client(conn, redirect_uri) as client:
            token = client.fetch_token(doc["token_endpoint"], code=code, code_verifier=code_verifier)
    except Exception as exc:
        raise OidcError("token exchange failed") from exc
    if not isinstance(token, dict) or not isinstance(token.get("id_token"), str):
        raise OidcError("the identity provider returned no ID token")
    return dict(token)


def validate_id_token(id_token: str, conn: Connection, nonce: str) -> dict[str, Any]:
    doc = discover(conn.issuer)
    try:
        keys = KeySet.import_key_set(fetch_jwks(doc["jwks_uri"]))  # type: ignore[arg-type]
        token = jwt.decode(id_token, keys, algorithms=ALGORITHMS)
        registry = JWTClaimsRegistry(
            leeway=60,
            iss={"essential": True, "value": doc["issuer"]},
            aud={"essential": True, "value": conn.client_id},
            nonce={"essential": True, "value": nonce},
            sub={"essential": True},
            exp={"essential": True},
        )
        registry.validate(token.claims)
    except (JoseError, ValueError, KeyError, TypeError) as exc:
        raise OidcError("the ID token is not valid") from exc
    return dict(token.claims)
