"""Two-factor authentication endpoints (/api/v1/auth/2fa).

setup -> enable (returns recovery codes once) -> sign-ins need a code;
verify completes a password sign-in that returned a challenge;
disable needs a valid code and is refused while the organisation requires 2FA.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from ..database import get_db, set_identity, set_tenant
from ..models._util import utcnow
from ..models.identity import AuthSession, Membership, Tenant, User
from ..schemas.reports import MeOut
from ..security import mfa
from ..security.auth import Context, _aware, create_session, get_context
from ..security.ratelimit import client_ip, limiter
from ..services import audit_service
from ..settings import get_settings

router = APIRouter(prefix="/api/v1/auth/2fa", tags=["auth"])
_BAD_CODE = "The code is not valid."


class MfaStatusOut(BaseModel):
    enabled: bool
    required: bool
    setup_required: bool


class SetupOut(BaseModel):
    secret: str
    otpauth_uri: str


class CodeIn(BaseModel):
    code: str = Field(min_length=6, max_length=32)


class EnabledOut(BaseModel):
    recovery_codes: list[str]


class VerifyIn(BaseModel):
    mfa_token: str = Field(min_length=10, max_length=2000)
    code: str | None = Field(default=None, max_length=12)
    recovery_code: str | None = Field(default=None, max_length=32)

    @model_validator(mode="after")
    def _one_factor(self) -> VerifyIn:
        if (self.code is None) == (self.recovery_code is None):
            raise ValueError("send exactly one of code or recovery_code")
        return self


def status_for(db: Session, ctx: Context) -> MfaStatusOut:
    tenant = db.get(Tenant, ctx.tenant_id)
    required = bool(tenant.require_2fa) if tenant else False
    return MfaStatusOut(
        enabled=mfa.is_enabled(db, ctx.user_id),
        required=required,
        setup_required=required and ctx.auth_method == "password",
    )


def _audit(db: Session, tenant_id: str, action: str, user: User, after: dict[str, object] | None = None) -> None:
    audit_service.log_action(
        db, tenant_id, None, action, "USER", user.id, after=after, actor=user.email, actor_user_id=user.id
    )


@router.get("", response_model=MfaStatusOut)
def mfa_status(ctx: Context = Depends(get_context), db: Session = Depends(get_db)) -> MfaStatusOut:
    return status_for(db, ctx)


@router.post("/setup", response_model=SetupOut)
def setup(request: Request, ctx: Context = Depends(get_context), db: Session = Depends(get_db)) -> SetupOut:
    limiter.check("mfa-setup", ctx.user_id, limit=10, window_s=3600)
    user = db.get(User, ctx.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Not signed in or your session has expired.")
    if mfa.is_enabled(db, user.id):
        raise HTTPException(status_code=409, detail="Two-factor authentication is already on.")
    secret, uri = mfa.begin_setup(db, user.id, user.email)
    _audit(db, ctx.tenant_id, "MFA_SETUP_STARTED", user, {"ip": client_ip(request)})
    db.commit()
    return SetupOut(secret=secret, otpauth_uri=uri)


@router.post("/enable", response_model=EnabledOut)
def enable(body: CodeIn, ctx: Context = Depends(get_context), db: Session = Depends(get_db)) -> EnabledOut:
    limiter.check("mfa-enable", ctx.user_id, limit=10, window_s=300)
    user = db.get(User, ctx.user_id)
    row = mfa.get(db, ctx.user_id)
    if user is None or row is None:
        raise HTTPException(status_code=400, detail="Start setup first.")
    if row.confirmed_at is not None:
        raise HTTPException(status_code=409, detail="Two-factor authentication is already on.")
    codes = mfa.confirm(row, body.code)
    if codes is None:
        raise HTTPException(status_code=401, detail=_BAD_CODE)
    now = utcnow()
    db.query(AuthSession).filter(
        AuthSession.user_id == user.id, AuthSession.id != ctx.session_id, AuthSession.revoked_at.is_(None)
    ).update({"revoked_at": now}, synchronize_session=False)
    current = db.get(AuthSession, ctx.session_id)
    if current is not None:
        current.auth_method = "password+totp"
    _audit(db, ctx.tenant_id, "MFA_ENABLED", user, {"other_sessions_revoked": True})
    db.commit()
    return EnabledOut(recovery_codes=codes)


@router.post("/disable", status_code=204)
def disable(body: CodeIn, ctx: Context = Depends(get_context), db: Session = Depends(get_db)) -> Response:
    limiter.check("mfa-disable", ctx.user_id, limit=10, window_s=300)
    user = db.get(User, ctx.user_id)
    row = mfa.get(db, ctx.user_id)
    if user is None or row is None or row.confirmed_at is None:
        raise HTTPException(status_code=409, detail="Two-factor authentication is not on.")
    if status_for(db, ctx).required:
        raise HTTPException(status_code=409, detail="Your organisation requires two-factor authentication.")
    if not (mfa.verify_totp(row, body.code) or mfa.consume_recovery_code(row, body.code)):
        raise HTTPException(status_code=401, detail=_BAD_CODE)
    mfa.disable(db, row)
    _audit(db, ctx.tenant_id, "MFA_DISABLED", user)
    db.commit()
    return Response(status_code=204)


@router.post("/verify", response_model=MeOut)
def verify(body: VerifyIn, request: Request, response: Response, db: Session = Depends(get_db)) -> MeOut:
    from .auth import me_out  # local import: auth.py imports this module's status helper

    limiter.check("mfa-verify-ip", client_ip(request), limit=30, window_s=300)
    challenge = mfa.read_challenge(body.mfa_token)
    if challenge is None:
        raise HTTPException(status_code=401, detail="The sign-in attempt has expired. Sign in again.")
    user = db.get(User, challenge.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="The sign-in attempt has expired. Sign in again.")
    locked_until = _aware(user.locked_until)
    if locked_until is not None and locked_until > utcnow():
        raise HTTPException(status_code=423, detail="Too many failed attempts. Try again later.")
    set_identity(db, user_id=user.id)
    set_tenant(db, challenge.tenant_id)
    membership = db.query(Membership).filter_by(user_id=user.id, tenant_id=challenge.tenant_id).first()
    row = mfa.get(db, user.id)
    if membership is None or row is None or row.confirmed_at is None:
        raise HTTPException(status_code=401, detail="The sign-in attempt has expired. Sign in again.")
    used_recovery = body.recovery_code is not None
    ok = (
        mfa.consume_recovery_code(row, body.recovery_code or "")
        if used_recovery
        else mfa.verify_totp(row, body.code or "")
    )
    settings = get_settings()
    if not ok:
        user.failed_logins = (user.failed_logins or 0) + 1
        if user.failed_logins >= settings.login_lockout_threshold:
            from datetime import timedelta

            user.locked_until = utcnow() + timedelta(minutes=settings.login_lockout_minutes)
            user.failed_logins = 0
        _audit(db, challenge.tenant_id, "MFA_FAILED", user, {"ip": client_ip(request)})
        db.commit()
        raise HTTPException(status_code=401, detail=_BAD_CODE)
    user.failed_logins, user.locked_until = 0, None
    session = create_session(db, response, user, challenge.tenant_id, request, auth_method="password+totp")
    method = "recovery_code" if used_recovery else "totp"
    audit_service.log_action(
        db, challenge.tenant_id, None, "LOGIN_SUCCEEDED", "SESSION", session.id,
        after={"ip": client_ip(request), "method": method}, actor=user.email, actor_user_id=user.id,
    )  # fmt: skip
    if used_recovery:
        _audit(db, challenge.tenant_id, "MFA_RECOVERY_CODE_USED", user, {"remaining": len(row.recovery_code_hashes)})
    db.commit()
    return me_out(db, user, challenge.tenant_id, membership.role, session.csrf_token, auth_method="password+totp")
