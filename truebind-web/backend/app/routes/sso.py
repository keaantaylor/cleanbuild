"""Single sign-on: organisation configuration (/api/v1/org/sso) and the
browser flow (/api/v1/auth/sso/start -> IdP -> /api/v1/auth/sso/callback).

Provisioning rules on callback, in order:
1. the ID token must validate (security/oidc.py);
2. the asserted e-mail must be verified (an explicit ``email_verified: false``
   is refused) and its domain must be one of the connection's domains;
3. an existing account signs in only if it is already a member of this
   organisation -- an IdP can never pull an account that exists elsewhere
   into its organisation;
4. an unknown address is created as a member with the default role only when
   JIT provisioning is on.
Failures redirect to the login page with a short ``sso_error`` code; the
detail goes to the audit log, never to the browser.
"""

from __future__ import annotations

import json
import re
import secrets
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db, set_identity, set_tenant
from ..models._util import utcnow
from ..models.identity import Membership, SsoConnection, SsoDomain, User
from ..security import crypto, oidc, passwords
from ..security.auth import Context, create_session, require
from ..security.permissions import Permission
from ..security.ratelimit import client_ip, limiter
from ..services import audit_service
from ..settings import get_settings

admin_router = APIRouter(prefix="/api/v1/org/sso", tags=["organisation"])
public_router = APIRouter(prefix="/api/v1/auth/sso", tags=["auth"])

STATE_COOKIE = "tb_sso"
STATE_TTL_S = 600
_SECRET_PURPOSE = "sso-client-secret"  # noqa: S105 -- an encryption purpose label, not a secret
_STATE_PURPOSE = "sso-state"
_DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
_org_read = require(Permission.ORG_READ)
_org_manage = require(Permission.ORG_MANAGE)


class SsoConfigIn(BaseModel):
    issuer: str = Field(min_length=8, max_length=500)
    client_id: str = Field(min_length=1, max_length=300)
    client_secret: str | None = Field(default=None, max_length=2000)
    token_auth_method: Literal["client_secret_post", "client_secret_basic"] = "client_secret_post"  # noqa: S105
    domains: list[str] = Field(min_length=1, max_length=20)
    jit_provisioning: bool = False
    default_role: Literal["ADMIN", "ANALYST", "VIEWER", "SENDER"] = "VIEWER"
    enabled: bool = True

    @field_validator("issuer")
    @classmethod
    def _issuer(cls, v: str) -> str:
        v = v.rstrip("/")
        if not v.startswith("https://") and (get_settings().is_production or not v.startswith("http://")):
            raise ValueError("the issuer must be an https:// URL")
        return v

    @field_validator("domains")
    @classmethod
    def _domains(cls, v: list[str]) -> list[str]:
        cleaned = sorted({d.strip().lower().lstrip("@") for d in v})
        bad = [d for d in cleaned if not _DOMAIN_RE.match(d)]
        if bad:
            raise ValueError(f"not a valid e-mail domain: {', '.join(bad)}")
        return cleaned


class SsoConfigOut(BaseModel):
    configured: bool
    issuer: str | None = None
    client_id: str | None = None
    has_client_secret: bool = False
    token_auth_method: str | None = None
    domains: list[str] = []
    jit_provisioning: bool = False
    default_role: str | None = None
    enabled: bool = False
    callback_url: str


def callback_url() -> str:
    return get_settings().public_api_url.rstrip("/") + "/api/v1/auth/sso/callback"


def _out(db: Session, conn: SsoConnection | None) -> SsoConfigOut:
    if conn is None:
        return SsoConfigOut(configured=False, callback_url=callback_url())
    domains = sorted(d.domain for d in db.query(SsoDomain).filter_by(connection_id=conn.id))
    return SsoConfigOut(
        configured=True,
        issuer=conn.issuer,
        client_id=conn.client_id,
        has_client_secret=bool(conn.client_secret_enc),
        token_auth_method=conn.token_auth_method,
        domains=domains,
        jit_provisioning=conn.jit_provisioning,
        default_role=conn.default_role,
        enabled=conn.enabled,
        callback_url=callback_url(),
    )


# ---------------------------------------------------------------- configuration


@admin_router.get("", response_model=SsoConfigOut)
def get_sso(ctx: Context = Depends(_org_read), db: Session = Depends(get_db)) -> SsoConfigOut:
    return _out(db, db.query(SsoConnection).filter_by(tenant_id=ctx.tenant_id).first())


@admin_router.patch("", response_model=SsoConfigOut)
def put_sso(body: SsoConfigIn, ctx: Context = Depends(_org_manage), db: Session = Depends(get_db)) -> SsoConfigOut:
    conn = db.query(SsoConnection).filter_by(tenant_id=ctx.tenant_id).first()
    if conn is None:
        conn = SsoConnection(tenant_id=ctx.tenant_id, issuer=body.issuer, client_id=body.client_id)
        db.add(conn)
    conn.issuer, conn.client_id = body.issuer, body.client_id
    conn.token_auth_method, conn.jit_provisioning = body.token_auth_method, body.jit_provisioning
    conn.default_role, conn.enabled, conn.updated_at = body.default_role, body.enabled, utcnow()
    secret_changed = body.client_secret is not None
    if body.client_secret is not None:
        conn.client_secret_enc = crypto.encrypt(_SECRET_PURPOSE, body.client_secret) if body.client_secret else None
    db.flush()
    db.query(SsoDomain).filter_by(tenant_id=ctx.tenant_id).delete(synchronize_session=False)
    db.flush()
    try:
        for domain in body.domains:
            db.add(SsoDomain(domain=domain, tenant_id=ctx.tenant_id, connection_id=conn.id))
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="One of these domains is already used by another organisation."
        ) from None
    audit_service.log_action(
        db, ctx.tenant_id, None, "SSO_CONFIG_CHANGED", "SSO_CONNECTION", conn.id,
        after={"issuer": conn.issuer, "client_id": conn.client_id, "domains": body.domains,
               "jit_provisioning": conn.jit_provisioning, "default_role": conn.default_role,
               "enabled": conn.enabled, "client_secret_changed": secret_changed},
        actor=ctx.actor, actor_user_id=ctx.user_id,
    )  # fmt: skip
    db.commit()
    return _out(db, conn)


@admin_router.delete("", status_code=204)
def delete_sso(ctx: Context = Depends(_org_manage), db: Session = Depends(get_db)) -> Response:
    conn = db.query(SsoConnection).filter_by(tenant_id=ctx.tenant_id).first()
    if conn is None:
        raise HTTPException(status_code=404, detail="Not found.")
    audit_service.log_action(
        db, ctx.tenant_id, None, "SSO_CONFIG_REMOVED", "SSO_CONNECTION", conn.id, before={"issuer": conn.issuer},
        actor=ctx.actor, actor_user_id=ctx.user_id,
    )  # fmt: skip
    db.query(SsoDomain).filter_by(connection_id=conn.id).delete(synchronize_session=False)
    db.delete(conn)
    db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------- browser flow


def _connection(conn: SsoConnection) -> oidc.Connection:
    secret = crypto.decrypt(_SECRET_PURPOSE, conn.client_secret_enc) if conn.client_secret_enc else ""
    return oidc.Connection(
        issuer=conn.issuer, client_id=conn.client_id, client_secret=secret, token_auth_method=conn.token_auth_method
    )


def _set_guc(db: Session, name: str, value: str) -> None:
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT set_config(:n, :v, true)"), {"n": name, "v": value})


@public_router.get("/start")
def sso_start(
    request: Request,
    email: str = Query(min_length=3, max_length=320),
    db: Session = Depends(get_db),
) -> Response:
    limiter.check("sso-start", client_ip(request), limit=30, window_s=300)
    domain = email.strip().lower().rsplit("@", 1)[-1]
    _set_guc(db, "app.sso_domain", domain)
    row = db.query(SsoDomain).filter_by(domain=domain).first()
    conn: SsoConnection | None = None
    if row is not None:
        set_tenant(db, row.tenant_id)
        conn = db.get(SsoConnection, row.connection_id)
    if conn is None or not conn.enabled:
        raise HTTPException(status_code=404, detail="Single sign-on is not set up for this e-mail domain.")
    try:
        auth = oidc.authorization_request(_connection(conn), callback_url())
    except oidc.OidcError:
        raise HTTPException(status_code=502, detail="The identity provider could not be reached.") from None
    state = json.dumps({"c": conn.id, "t": conn.tenant_id, "s": auth.state, "n": auth.nonce, "v": auth.code_verifier})
    response = RedirectResponse(auth.url, status_code=302)
    response.set_cookie(
        STATE_COOKIE, crypto.encrypt(_STATE_PURPOSE, state), max_age=STATE_TTL_S, httponly=True,
        secure=bool(get_settings().cookie_secure), samesite="lax", path="/api/v1/auth/sso",
    )  # fmt: skip
    return response


def _fail(code: str) -> RedirectResponse:
    r = RedirectResponse(f"{get_settings().public_app_url.rstrip('/')}/login?sso_error={quote(code)}", 303)
    r.delete_cookie(STATE_COOKIE, path="/api/v1/auth/sso")
    return r


@public_router.get("/callback")
def sso_callback(
    request: Request,
    code: str = Query(default="", max_length=2000),
    state: str = Query(default="", max_length=500),
    db: Session = Depends(get_db),
) -> Response:
    limiter.check("sso-callback", client_ip(request), limit=30, window_s=300)
    try:
        saved = json.loads(crypto.decrypt(_STATE_PURPOSE, request.cookies.get(STATE_COOKIE, ""), ttl_s=STATE_TTL_S))
    except (crypto.DecryptionError, ValueError):
        return _fail("invalid_state")
    if not state or not code or not secrets.compare_digest(state, str(saved["s"])):
        return _fail("invalid_state")
    tenant_id = str(saved["t"])
    set_tenant(db, tenant_id)
    conn = db.get(SsoConnection, str(saved["c"]))
    if conn is None or not conn.enabled or conn.tenant_id != tenant_id:
        return _fail("not_configured")

    def refuse(reason: str, email: str | None = None) -> RedirectResponse:
        audit_service.log_action(
            db, tenant_id, None, "SSO_FAILED", "SSO_CONNECTION", conn.id,
            after={"reason": reason, "email": email, "ip": client_ip(request)},
        )  # fmt: skip
        db.commit()
        return _fail(reason)

    try:
        oc = _connection(conn)
        tokens = oidc.exchange_code(oc, callback_url(), code, str(saved["v"]))
        claims = oidc.validate_id_token(tokens["id_token"], oc, nonce=str(saved["n"]))
    except oidc.OidcError:
        return refuse("invalid_token")
    email = str(claims.get("email") or claims.get("preferred_username") or "").strip().lower()
    if "@" not in email:
        return refuse("no_email")
    if claims.get("email_verified") is False:
        return refuse("email_unverified", email)
    domains = {d.domain for d in db.query(SsoDomain).filter_by(connection_id=conn.id)}
    if email.rsplit("@", 1)[1] not in domains:
        return refuse("domain_mismatch", email)

    user = db.query(User).filter_by(email=email).first()
    if user is not None:
        set_identity(db, user_id=user.id)
        membership = db.query(Membership).filter_by(user_id=user.id, tenant_id=tenant_id).first()
        if membership is None or not user.is_active:
            return refuse("not_a_member", email)
    else:
        if not conn.jit_provisioning:
            return refuse("not_provisioned", email)
        name = str(claims.get("name") or email.split("@")[0])[:200]
        # SSO-only account: an unguessable password nobody knows.
        user = User(email=email, password_hash=passwords.hash_password(secrets.token_urlsafe(32)), display_name=name)
        db.add(user)
        db.flush()
        membership = Membership(user_id=user.id, tenant_id=tenant_id, role=conn.default_role)
        db.add(membership)
        db.flush()
        audit_service.log_action(
            db, tenant_id, None, "SSO_USER_PROVISIONED", "MEMBERSHIP", membership.id,
            after={"email": email, "role": conn.default_role}, actor=email, actor_user_id=user.id,
        )  # fmt: skip

    response = RedirectResponse(f"{get_settings().public_app_url.rstrip('/')}/overview", status_code=303)
    response.delete_cookie(STATE_COOKIE, path="/api/v1/auth/sso")
    session = create_session(db, response, user, tenant_id, request, auth_method="sso")
    audit_service.log_action(
        db, tenant_id, None, "LOGIN_SUCCEEDED", "SESSION", session.id,
        after={"ip": client_ip(request), "method": "sso", "issuer": conn.issuer}, actor=email, actor_user_id=user.id,
    )  # fmt: skip
    db.commit()
    return response
