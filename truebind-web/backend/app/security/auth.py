"""Session authentication, CSRF and authorization dependencies.

- Session token: 256-bit random, sent only as an HttpOnly cookie
  (Secure in production, SameSite=Lax); the DB stores SHA-256(token) only.
- CSRF: double-submit token bound to the session. Every unsafe request must
  send X-CSRF-Token equal to the session's csrf_token (returned by /auth/me
  and /auth/login). A cross-site form cannot read it.
- Tenant and role come from the server-side session + membership, never
  from the request body or URL."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from ..config import COOKIE_SECURE, SESSION_TTL_HOURS
from ..database import get_db, set_identity, set_tenant
from ..models.identity import AuthSession, Membership, Tenant, User
from .permissions import Permission, has_permission, permissions_for

COOKIE_NAME = "tb_session"
# While an organisation requires 2FA and the session was established with a
# password alone, only these endpoints answer (so the user can set it up).
MFA_SETUP_PATHS = frozenset({"/api/v1/auth/me", "/api/v1/auth/logout", "/api/v1/auth/2fa",
                             "/api/v1/auth/2fa/setup", "/api/v1/auth/2fa/enable"})
CSRF_HEADER = "X-CSRF-Token"
_UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)  # SQLite returns naive datetimes
    return dt


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class Context:
    user_id: str
    tenant_id: str
    role: str
    session_id: str
    actor: str  # display label for audit entries, derived from the identity
    csrf_token: str
    auth_method: str = "password"

    @property
    def can_write(self) -> bool:
        return has_permission(self.role, Permission.DATA_WRITE)

    @property
    def permissions(self) -> list[str]:
        return sorted(p.value for p in permissions_for(self.role))

    def has(self, permission: Permission) -> bool:
        return has_permission(self.role, permission)


def create_session(db: Session, response: Response, user: User, tenant_id: str, request: Request,
                   auth_method: str = "password") -> AuthSession:
    token = secrets.token_urlsafe(32)
    s = AuthSession(token_hash=token_hash(token), csrf_token=secrets.token_urlsafe(24), user_id=user.id,
                    tenant_id=tenant_id, expires_at=_now() + timedelta(hours=SESSION_TTL_HOURS),
                    user_agent=(request.headers.get("user-agent") or "")[:300], auth_method=auth_method)
    db.add(s)
    db.flush()
    response.set_cookie(COOKIE_NAME, token, httponly=True, secure=COOKIE_SECURE, samesite="lax",
                        max_age=SESSION_TTL_HOURS * 3600, path="/")
    return s


def clear_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/", secure=COOKIE_SECURE, httponly=True, samesite="lax")


def _unauthorized() -> HTTPException:
    return HTTPException(status_code=401, detail="Not signed in or your session has expired.")


def get_context(request: Request, db: Session = Depends(get_db)) -> Context:
    token = request.cookies.get(COOKIE_NAME)
    if not token or len(token) > 200:
        raise _unauthorized()
    h = token_hash(token)
    set_identity(db, session_token_hash=h)
    s = db.query(AuthSession).filter_by(token_hash=h).first()
    expires_at = _aware(s.expires_at) if s is not None else None
    if s is None or s.revoked_at is not None or expires_at is None or expires_at <= _now():
        raise _unauthorized()
    user = db.get(User, s.user_id)
    if user is None or not user.is_active:
        raise _unauthorized()
    set_identity(db, user_id=user.id)
    set_tenant(db, s.tenant_id)
    m = db.query(Membership).filter_by(user_id=user.id, tenant_id=s.tenant_id).first()
    if m is None:
        raise _unauthorized()
    if request.method in _UNSAFE:
        sent = request.headers.get(CSRF_HEADER, "")
        if not sent or not hmac.compare_digest(sent, s.csrf_token):
            raise HTTPException(status_code=403, detail="Missing or invalid CSRF token.")
    set_tenant(db, s.tenant_id)
    if s.auth_method == "password" and request.url.path not in MFA_SETUP_PATHS:
        tenant = db.get(Tenant, s.tenant_id)
        if tenant is not None and tenant.require_2fa:
            raise HTTPException(status_code=403, headers={"X-TrueBind-Reason": "mfa_setup_required"},
                                detail="Your organisation requires two-factor authentication. Set it up to continue.")
    return Context(user_id=user.id, tenant_id=s.tenant_id, role=m.role, session_id=s.id,
                   actor=user.email, csrf_token=s.csrf_token, auth_method=s.auth_method)


def require(permission: Permission):
    """Dependency factory: the signed-in member must hold `permission`."""

    def _dep(ctx: Context = Depends(get_context)) -> Context:
        if not ctx.has(permission):
            raise HTTPException(status_code=403, detail="Your role does not allow this action.")
        return ctx

    _dep.__name__ = f"require_{permission.name.lower()}"
    return _dep


# Organisation data (reports, findings, audit...): OWNER/ADMIN/ANALYST/VIEWER.
require_reader = require(Permission.DATA_READ)
require_writer = require(Permission.DATA_WRITE)
