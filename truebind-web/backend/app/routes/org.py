"""Organisation settings, members and invitations.

- Owners and admins manage members; admins can never create, change or
  remove an owner; the last owner can never be demoted or removed.
- Invitations carry a one-time token (only its SHA-256 is stored), expire
  after INVITE_TTL, and are accepted without being signed in: a new user sets
  a password, an existing user proves theirs.
- Every change writes a hash-chained audit entry.
- IDs from another organisation are indistinguishable from missing ones (404).
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..database import get_db, set_tenant
from ..models._util import utcnow
from ..models.identity import AuthSession, Invitation, Membership, Tenant, User
from ..schemas.reports import MeOut, TenantOut, UserOut
from ..security import passwords
from ..security.auth import Context, _aware, create_session, require, token_hash
from ..security.permissions import (
    ASSIGNABLE_BY_ADMIN,
    ROLES,
    Permission,
    has_permission,
    permissions_for,
)
from ..security.ratelimit import client_ip, limiter
from ..services import audit_service

router = APIRouter(prefix="/api/v1/org", tags=["organisation"])
public_router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

INVITE_TTL = timedelta(days=7)
_org_read = require(Permission.ORG_READ)
_org_manage = require(Permission.ORG_MANAGE)
_member_read = require(Permission.MEMBER_READ)
_member_manage = require(Permission.MEMBER_MANAGE)

Role = Literal["OWNER", "ADMIN", "ANALYST", "VIEWER", "SENDER"]
OrgType = Literal["capacity_provider", "mga", "tpa"]


class OrgOut(BaseModel):
    id: str
    name: str
    org_type: str
    require_2fa: bool
    retention_days: int


class OrgPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    org_type: OrgType | None = None
    require_2fa: bool | None = None


class MemberOut(BaseModel):
    membership_id: str
    user_id: str
    email: str
    display_name: str
    role: str
    created_at: datetime


class RolePatch(BaseModel):
    role: Role


class InvitationIn(BaseModel):
    email: EmailStr
    role: Role


class InvitationOut(BaseModel):
    id: str
    email: str
    role: str
    created_at: datetime
    expires_at: datetime


class InvitationCreated(InvitationOut):
    # Returned exactly once; only its hash is stored.
    accept_token: str


class AcceptIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    display_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=1024)


def _org_out(t: Tenant) -> OrgOut:
    return OrgOut(
        id=t.id, name=t.name, org_type=t.org_type, require_2fa=bool(t.require_2fa), retention_days=t.retention_days
    )


def _tenant(db: Session, ctx: Context) -> Tenant:
    t = db.get(Tenant, ctx.tenant_id)
    if t is None:  # membership rows cascade with the tenant; cannot happen for a live session
        raise HTTPException(status_code=404, detail="Not found.")
    return t


def _membership_or_404(db: Session, ctx: Context, membership_id: str) -> Membership:
    m = db.query(Membership).filter_by(id=membership_id, tenant_id=ctx.tenant_id).first()
    if m is None:
        raise HTTPException(status_code=404, detail="Not found.")
    return m


def _member_out(m: Membership, u: User) -> MemberOut:
    return MemberOut(
        membership_id=m.id,
        user_id=u.id,
        email=u.email,
        display_name=u.display_name,
        role=m.role,
        created_at=m.created_at,
    )


def _check_can_assign(ctx: Context, role: str) -> None:
    if ctx.role != "OWNER" and role not in ASSIGNABLE_BY_ADMIN:
        raise HTTPException(status_code=403, detail="Only an owner can grant the owner role.")


def _owner_count(db: Session, tenant_id: str) -> int:
    return db.query(Membership).filter_by(tenant_id=tenant_id, role="OWNER").count()


def _guard_owner_change(db: Session, ctx: Context, target: Membership, new_role: str | None) -> None:
    """new_role None = removal."""
    if target.role == "OWNER":
        if ctx.role != "OWNER":
            raise HTTPException(status_code=403, detail="Only an owner can change another owner.")
        if new_role != "OWNER" and _owner_count(db, ctx.tenant_id) <= 1:
            raise HTTPException(status_code=409, detail="The organisation must keep at least one owner.")


# ---------------------------------------------------------------- organisation


@router.get("", response_model=OrgOut)
def get_org(ctx: Context = Depends(_org_read), db: Session = Depends(get_db)) -> OrgOut:
    return _org_out(_tenant(db, ctx))


@router.patch("", response_model=OrgOut)
def patch_org(body: OrgPatch, ctx: Context = Depends(_org_manage), db: Session = Depends(get_db)) -> OrgOut:
    t = _tenant(db, ctx)
    before: dict[str, object] = {}
    after: dict[str, object] = {}
    for field in ("name", "org_type", "require_2fa"):
        new = getattr(body, field)
        old = getattr(t, field)
        if new is not None and new != old:
            before[field], after[field] = old, new
            setattr(t, field, new)
    if after:
        audit_service.log_action(
            db, t.id, None, "SETTINGS_CHANGED", "ORGANISATION", t.id, before=before, after=after,
            actor=ctx.actor, actor_user_id=ctx.user_id,
        )  # fmt: skip
    db.commit()
    return _org_out(t)


# ---------------------------------------------------------------- members


@router.get("/members", response_model=list[MemberOut])
def list_members(ctx: Context = Depends(_member_read), db: Session = Depends(get_db)) -> list[MemberOut]:
    rows = (
        db.query(Membership, User)
        .join(User, User.id == Membership.user_id)
        .filter(Membership.tenant_id == ctx.tenant_id)
        .order_by(Membership.created_at)
        .all()
    )
    return [_member_out(m, u) for m, u in rows]


@router.patch("/members/{membership_id}", response_model=MemberOut)
def change_role(
    membership_id: str,
    body: RolePatch,
    ctx: Context = Depends(_member_manage),
    db: Session = Depends(get_db),
) -> MemberOut:
    m = _membership_or_404(db, ctx, membership_id)
    _guard_owner_change(db, ctx, m, body.role)
    _check_can_assign(ctx, body.role)
    user = db.get(User, m.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Not found.")
    if body.role != m.role:
        before = {"role": m.role, "email": user.email}
        m.role = body.role
        audit_service.log_action(
            db, ctx.tenant_id, None, "ROLE_CHANGED", "MEMBERSHIP", m.id, before=before,
            after={"role": m.role, "email": user.email}, actor=ctx.actor, actor_user_id=ctx.user_id,
        )  # fmt: skip
    db.commit()
    return _member_out(m, user)


@router.delete("/members/{membership_id}", status_code=204)
def remove_member(
    membership_id: str,
    ctx: Context = Depends(_member_manage),
    db: Session = Depends(get_db),
) -> Response:
    m = _membership_or_404(db, ctx, membership_id)
    _guard_owner_change(db, ctx, m, None)
    user = db.get(User, m.user_id)
    email = user.email if user else None
    now = utcnow()
    db.query(AuthSession).filter(
        AuthSession.user_id == m.user_id, AuthSession.tenant_id == ctx.tenant_id, AuthSession.revoked_at.is_(None)
    ).update({"revoked_at": now}, synchronize_session=False)
    audit_service.log_action(
        db, ctx.tenant_id, None, "MEMBER_REMOVED", "MEMBERSHIP", m.id, before={"role": m.role, "email": email},
        actor=ctx.actor, actor_user_id=ctx.user_id,
    )  # fmt: skip
    db.delete(m)
    db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------- invitations


@router.get("/invitations", response_model=list[InvitationOut])
def list_invitations(ctx: Context = Depends(_member_manage), db: Session = Depends(get_db)) -> list[InvitationOut]:
    rows = (
        db.query(Invitation)
        .filter(
            Invitation.tenant_id == ctx.tenant_id, Invitation.accepted_at.is_(None), Invitation.revoked_at.is_(None)
        )
        .order_by(Invitation.created_at.desc())
        .all()
    )
    return [InvitationOut.model_validate(i, from_attributes=True) for i in rows]


@router.post("/invitations", response_model=InvitationCreated, status_code=201)
def create_invitation(
    body: InvitationIn,
    ctx: Context = Depends(_member_manage),
    db: Session = Depends(get_db),
) -> InvitationCreated:
    _check_can_assign(ctx, body.role)
    email = str(body.email).lower()
    existing = (
        db.query(Membership)
        .join(User, User.id == Membership.user_id)
        .filter(Membership.tenant_id == ctx.tenant_id, User.email == email)
        .first()
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="That person is already a member.")
    token = secrets.token_urlsafe(32)
    inv = Invitation(
        tenant_id=ctx.tenant_id,
        email=email,
        role=body.role,
        token_hash=token_hash(token),
        invited_by_user_id=ctx.user_id,
        expires_at=utcnow() + INVITE_TTL,
    )
    db.add(inv)
    db.flush()
    audit_service.log_action(
        db, ctx.tenant_id, None, "INVITATION_CREATED", "INVITATION", inv.id,
        after={"email": email, "role": body.role, "expires_at": inv.expires_at.isoformat()},
        actor=ctx.actor, actor_user_id=ctx.user_id,
    )  # fmt: skip
    db.commit()
    out = InvitationOut.model_validate(inv, from_attributes=True)
    return InvitationCreated(**out.model_dump(), accept_token=token)


@router.delete("/invitations/{invitation_id}", status_code=204)
def revoke_invitation(
    invitation_id: str,
    ctx: Context = Depends(_member_manage),
    db: Session = Depends(get_db),
) -> Response:
    inv = db.query(Invitation).filter_by(id=invitation_id, tenant_id=ctx.tenant_id).first()
    if inv is None or inv.accepted_at is not None or inv.revoked_at is not None:
        raise HTTPException(status_code=404, detail="Not found.")
    inv.revoked_at = utcnow()
    audit_service.log_action(
        db, ctx.tenant_id, None, "INVITATION_REVOKED", "INVITATION", inv.id, before={"email": inv.email},
        actor=ctx.actor, actor_user_id=ctx.user_id,
    )  # fmt: skip
    db.commit()
    return Response(status_code=204)


def _find_invitation(db: Session, token: str) -> Invitation | None:
    h = token_hash(token)
    if db.get_bind().dialect.name == "postgresql":
        # RLS: only the row matching this token hash becomes visible.
        db.execute(text("SELECT set_config('app.invite_token_hash', :h, true)"), {"h": h})
    return db.query(Invitation).filter_by(token_hash=h).first()


@public_router.post("/invitations/accept", response_model=MeOut)
def accept_invitation(body: AcceptIn, request: Request, response: Response, db: Session = Depends(get_db)) -> MeOut:
    limiter.check("invite-accept", client_ip(request), limit=20, window_s=300)
    inv = _find_invitation(db, body.token)
    if inv is None or inv.accepted_at is not None or inv.revoked_at is not None:
        raise HTTPException(status_code=404, detail="This invitation is not valid.")
    expires_at = _aware(inv.expires_at)
    if expires_at is None or expires_at <= utcnow():
        raise HTTPException(status_code=410, detail="This invitation has expired. Ask for a new one.")
    set_tenant(db, inv.tenant_id)
    user = db.query(User).filter_by(email=inv.email).first()
    if user is not None:
        if not user.is_active or not passwords.verify_password(body.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Email or password is incorrect.")
        if db.query(Membership).filter_by(user_id=user.id, tenant_id=inv.tenant_id).first() is not None:
            raise HTTPException(status_code=409, detail="You are already a member.")
    else:
        problems = passwords.password_problems(body.password)
        if problems:
            raise HTTPException(status_code=422, detail=" ".join(problems))
        user = User(
            email=inv.email, password_hash=passwords.hash_password(body.password), display_name=body.display_name
        )
        db.add(user)
        db.flush()
    membership = Membership(user_id=user.id, tenant_id=inv.tenant_id, role=inv.role)
    db.add(membership)
    inv.accepted_at = utcnow()
    db.flush()
    session = create_session(db, response, user, inv.tenant_id, request)
    audit_service.log_action(
        db, inv.tenant_id, None, "INVITATION_ACCEPTED", "MEMBERSHIP", membership.id,
        after={"email": user.email, "role": inv.role}, actor=user.email, actor_user_id=user.id,
    )  # fmt: skip
    db.commit()
    tenant = db.get(Tenant, inv.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="This invitation is not valid.")
    return MeOut(
        user=UserOut(id=user.id, email=user.email, display_name=user.display_name),
        tenant=TenantOut(
            id=tenant.id,
            name=tenant.name,
            retention_days=tenant.retention_days,
            org_type=tenant.org_type,
            require_2fa=bool(tenant.require_2fa),
        ),
        role=inv.role,
        can_write=has_permission(inv.role, Permission.DATA_WRITE),
        permissions=sorted(p.value for p in permissions_for(inv.role)),
        csrf_token=session.csrf_token,
    )


__all__ = ["ROLES", "public_router", "router"]
