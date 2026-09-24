"""Sign-up, sign-in, sign-out, current identity.

- Passwords: scrypt; minimum 12 characters; never logged or returned.
- Login: rate-limited per IP and per account; 5 consecutive failures lock
  the account for 15 minutes; the response is identical for "no such user"
  and "wrong password", and both paths run a full scrypt verification so
  timing does not reveal which accounts exist.
- Session: HttpOnly cookie; CSRF token returned in the body for the SPA to
  echo in X-CSRF-Token."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from ..config import ALLOW_SIGNUP
from ..database import get_db, set_tenant
from ..models._util import utcnow
from ..models.identity import AuthSession, Membership, Tenant, User
from ..schemas.reports import LoginRequest, MeOut, SignupRequest, TenantOut, UserOut
from ..security import passwords
from ..security.auth import Context, _aware, clear_cookie, create_session, get_context
from ..security.ratelimit import client_ip, limiter
from ..services import audit_service

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

LOCKOUT_THRESHOLD = 5
LOCKOUT_MINUTES = 15
_BAD_LOGIN = "Email or password is incorrect."


def _me(db: Session, user: User, tenant_id: str, role: str, csrf: str) -> MeOut:
    t = db.get(Tenant, tenant_id)
    return MeOut(user=UserOut(id=user.id, email=user.email, display_name=user.display_name),
                 tenant=TenantOut(id=t.id, name=t.name, retention_days=t.retention_days),
                 role=role, can_write=role in ("OWNER", "ADMIN", "REVIEWER"), csrf_token=csrf)


@router.post("/signup", response_model=MeOut, status_code=201)
def signup(body: SignupRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> MeOut:
    if not ALLOW_SIGNUP:
        raise HTTPException(status_code=403, detail="Self-service sign-up is disabled. Ask your administrator.")
    limiter.check("signup", client_ip(request), limit=5, window_s=3600)
    problems = passwords.password_problems(body.password)
    if problems:
        raise HTTPException(status_code=422, detail=" ".join(problems))
    email = body.email.lower()
    if db.query(User).filter_by(email=email).first() is not None:
        # Do not confirm which emails are registered.
        raise HTTPException(status_code=409, detail="An account could not be created with these details.")
    tenant = Tenant(name=body.organisation)
    user = User(email=email, password_hash=passwords.hash_password(body.password), display_name=body.display_name)
    db.add_all([tenant, user])
    db.flush()
    set_tenant(db, tenant.id)
    db.add(Membership(user_id=user.id, tenant_id=tenant.id, role="OWNER"))
    s = create_session(db, response, user, tenant.id, request)
    audit_service.log_action(db, tenant.id, None, "ACCOUNT_CREATED", "USER", user.id, after={"role": "OWNER"},
                             actor=email, actor_user_id=user.id)
    db.commit()
    return _me(db, user, tenant.id, "OWNER", s.csrf_token)


@router.post("/login", response_model=MeOut)
def login(body: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> MeOut:
    email = body.email.lower()
    limiter.check("login-ip", client_ip(request), limit=20, window_s=300)
    limiter.check("login-account", email, limit=10, window_s=300)
    user = db.query(User).filter_by(email=email).first()
    if user is None:
        passwords.verify_password(body.password, passwords.DUMMY_HASH)
        raise HTTPException(status_code=401, detail=_BAD_LOGIN)
    now = utcnow()
    if user.locked_until is not None and _aware(user.locked_until) > now:
        passwords.verify_password(body.password, passwords.DUMMY_HASH)
        raise HTTPException(status_code=423, detail="Too many failed attempts. Try again later.")
    membership = db.query(Membership).filter_by(user_id=user.id).order_by(Membership.created_at).first()
    ok = passwords.verify_password(body.password, user.password_hash)
    if membership is not None:
        set_tenant(db, membership.tenant_id)
    if not ok or not user.is_active or membership is None:
        user.failed_logins = (user.failed_logins or 0) + 1
        if user.failed_logins >= LOCKOUT_THRESHOLD:
            user.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
            user.failed_logins = 0
        if membership is not None:
            audit_service.log_action(db, membership.tenant_id, None, "LOGIN_FAILED", "USER", user.id,
                                     after={"ip": client_ip(request)}, actor=email, actor_user_id=user.id)
        db.commit()
        raise HTTPException(status_code=401, detail=_BAD_LOGIN)
    user.failed_logins, user.locked_until = 0, None
    s = create_session(db, response, user, membership.tenant_id, request)
    audit_service.log_action(db, membership.tenant_id, None, "LOGIN_SUCCEEDED", "SESSION", s.id,
                             after={"ip": client_ip(request)}, actor=email, actor_user_id=user.id)
    db.commit()
    return _me(db, user, membership.tenant_id, membership.role, s.csrf_token)


@router.post("/logout", status_code=204)
def logout(response: Response, ctx: Context = Depends(get_context), db: Session = Depends(get_db)) -> Response:
    s = db.get(AuthSession, ctx.session_id)
    if s is not None:
        s.revoked_at = utcnow()
    audit_service.log_action(db, ctx.tenant_id, None, "LOGOUT", "SESSION", ctx.session_id,
                             actor=ctx.actor, actor_user_id=ctx.user_id)
    db.commit()
    response.status_code = 204
    clear_cookie(response)
    return response


@router.get("/me", response_model=MeOut)
def me(ctx: Context = Depends(get_context), db: Session = Depends(get_db)) -> MeOut:
    return _me(db, db.get(User, ctx.user_id), ctx.tenant_id, ctx.role, ctx.csrf_token)
