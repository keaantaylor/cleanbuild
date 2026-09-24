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
from ..database import get_db, set_tenant
from ..models.identity import WRITE_ROLES, AuthSession, Membership, User

COOKIE_NAME = "tb_session"
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

    @property
    def can_write(self) -> bool:
        return self.role in WRITE_ROLES


def create_session(db: Session, response: Response, user: User, tenant_id: str, request: Request) -> AuthSession:
    token = secrets.token_urlsafe(32)
    s = AuthSession(token_hash=token_hash(token), csrf_token=secrets.token_urlsafe(24), user_id=user.id,
                    tenant_id=tenant_id, expires_at=_now() + timedelta(hours=SESSION_TTL_HOURS),
                    user_agent=(request.headers.get("user-agent") or "")[:300])
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
    s = db.query(AuthSession).filter_by(token_hash=token_hash(token)).first()
    if s is None or s.revoked_at is not None or _aware(s.expires_at) <= _now():
        raise _unauthorized()
    user = db.get(User, s.user_id)
    if user is None or not user.is_active:
        raise _unauthorized()
    m = db.query(Membership).filter_by(user_id=user.id, tenant_id=s.tenant_id).first()
    if m is None:
        raise _unauthorized()
    if request.method in _UNSAFE:
        sent = request.headers.get(CSRF_HEADER, "")
        if not sent or not hmac.compare_digest(sent, s.csrf_token):
            raise HTTPException(status_code=403, detail="Missing or invalid CSRF token.")
    set_tenant(db, s.tenant_id)
    return Context(user_id=user.id, tenant_id=s.tenant_id, role=m.role, session_id=s.id,
                   actor=user.email, csrf_token=s.csrf_token)


def require_writer(ctx: Context = Depends(get_context)) -> Context:
    if not ctx.can_write:
        raise HTTPException(status_code=403, detail="Your role does not allow this action.")
    return ctx
