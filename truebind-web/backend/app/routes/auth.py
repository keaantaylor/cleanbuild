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
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import ALLOW_SIGNUP
from ..database import get_db, set_identity, set_tenant
from ..models._util import utcnow
from ..models.identity import AuthSession, Membership, Tenant, User
from ..schemas.reports import LoginRequest, MeOut, SignupRequest, TenantOut, UserOut
from ..security import mfa, passwords
from ..security.auth import Context, _aware, clear_cookie, create_session, get_context
from ..security.permissions import Permission, has_permission, permissions_for
from ..security.ratelimit import client_ip, limiter
from ..services import audit_service

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

LOCKOUT_THRESHOLD = 5
LOCKOUT_MINUTES = 15
_BAD_LOGIN = "Email or password is incorrect."


def me_out(db: Session, user: User, tenant_id: str, role: str, csrf: str, auth_method: str = "password") -> MeOut:
    from .mfa import MfaStatusOut

    t = db.get(Tenant, tenant_id)
    if t is None:  # the session's tenant was deleted underneath it
        raise HTTPException(status_code=401, detail="Not signed in or your session has expired.")
    return MeOut(user=UserOut(id=user.id, email=user.email, display_name=user.display_name),
                 tenant=TenantOut(id=t.id, name=t.name, retention_days=t.retention_days, org_type=t.org_type,
                                  require_2fa=bool(t.require_2fa)),
                 role=role, can_write=has_permission(role, Permission.DATA_WRITE),
                 permissions=sorted(p.value for p in permissions_for(role)), csrf_token=csrf,
                 mfa=MfaStatusOut(enabled=mfa.is_enabled(db, user.id), required=bool(t.require_2fa),
                                  setup_required=bool(t.require_2fa) and auth_method == "password").model_dump())


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
    return me_out(db, user, tenant.id, "OWNER", s.csrf_token)


class MfaChallengeOut(BaseModel):
    mfa_required: bool = True
    mfa_token: str
    methods: list[str] = ["totp", "recovery_code"]


@router.post("/login", response_model=MeOut | MfaChallengeOut)
def login(body: LoginRequest, request: Request, response: Response,
          db: Session = Depends(get_db)) -> MeOut | MfaChallengeOut:
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
    set_identity(db, user_id=user.id)
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
    if mfa.is_enabled(db, user.id):
        # Password proven; the failure counter is NOT reset until the second
        # factor is too, so codes cannot be brute-forced by re-entering it.
        db.commit()
        return MfaChallengeOut(mfa_token=mfa.issue_challenge(user.id, membership.tenant_id))
    user.failed_logins, user.locked_until = 0, None
    s = create_session(db, response, user, membership.tenant_id, request)
    audit_service.log_action(db, membership.tenant_id, None, "LOGIN_SUCCEEDED", "SESSION", s.id,
                             after={"ip": client_ip(request)}, actor=email, actor_user_id=user.id)
    db.commit()
    return me_out(db, user, membership.tenant_id, membership.role, s.csrf_token)


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
    user = db.get(User, ctx.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Not signed in or your session has expired.")
    return me_out(db, user, ctx.tenant_id, ctx.role, ctx.csrf_token, auth_method=ctx.auth_method)
