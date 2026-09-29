"""Billing and entitlements (P9).

GET  /api/v1/billing            plan, subscription status, entitlements and usage (billing:manage)
POST /api/v1/billing/checkout   a Stripe Checkout link for a plan (billing:manage, audited)
POST /api/v1/billing/portal     a Stripe customer-portal link (billing:manage, audited)
POST /api/v1/billing/webhook    Stripe events, signature-verified, applied once per event id (public)
With BILLING_ENABLED off nothing is limited and the response says billing is not enforced.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db, set_tenant
from ..models._util import utcnow
from ..models.billing import BillingEvent
from ..models.identity import Tenant
from ..security.auth import Context, require
from ..security.permissions import Permission
from ..services import audit_service, billing_service
from ..settings import get_settings

log = logging.getLogger("truebind.billing")
router = APIRouter(prefix="/api/v1/billing", tags=["billing"])
_billing = require(Permission.BILLING_MANAGE)


class PlanOut(BaseModel):
    name: str
    label: str
    modules: list[str]
    monthly_rows: int | None
    seats: int | None
    purchasable: bool


class BillingOut(BaseModel):
    enforced: bool
    plan: str | None
    status: str | None
    period_end: datetime | None
    modules: list[str] | None
    monthly_rows: int | None
    seats: int | None
    rows_this_month: int
    seats_used: int
    plans: list[PlanOut]
    customer: bool


class CheckoutIn(BaseModel):
    plan: str = Field(min_length=1, max_length=64)


class LinkOut(BaseModel):
    url: str


def _tenant(db: Session, ctx: Context) -> Tenant:
    t = db.get(Tenant, ctx.tenant_id)
    if t is None:  # pragma: no cover -- a signed-in member always has a tenant
        raise HTTPException(status_code=404, detail="Organisation not found.")
    return t


@router.get("", response_model=BillingOut)
def billing(ctx: Context = Depends(_billing), db: Session = Depends(get_db)) -> BillingOut:
    t = _tenant(db, ctx)
    ent = billing_service.entitlements(t)
    return BillingOut(
        enforced=ent.enforced,
        plan=ent.plan,
        status=t.billing_status,
        period_end=t.billing_period_end,
        modules=sorted(ent.modules) if ent.modules is not None else None,
        monthly_rows=ent.monthly_rows,
        seats=ent.seats,
        rows_this_month=billing_service.rows_this_month(db, t.id),
        seats_used=billing_service.seats_used(db, t.id),
        customer=bool(t.stripe_customer_id),
        plans=[
            PlanOut(
                name=n,
                label=str(p.get("label") or n),
                modules=list(p.get("modules") or []),
                monthly_rows=p.get("monthly_rows"),
                seats=p.get("seats"),
                purchasable=bool(p.get("price_id")),
            )
            for n, p in billing_service.plans().items()
        ],
    )


@router.post("/checkout", response_model=LinkOut)
def checkout(body: CheckoutIn, ctx: Context = Depends(_billing), db: Session = Depends(get_db)) -> LinkOut:
    if not get_settings().billing_enabled:
        raise HTTPException(status_code=409, detail="Billing is not enabled on this server.")
    t = _tenant(db, ctx)
    try:
        url = billing_service.checkout_url(t, body.plan, ctx.actor)
    except billing_service.BillingError as exc:
        raise HTTPException(status_code=502 if "provider" in str(exc) else 409, detail=str(exc)) from exc
    audit_service.log_action(
        db,
        ctx.tenant_id,
        None,
        "BILLING_CHECKOUT_STARTED",
        "TENANT",
        t.id,
        after={"plan": body.plan},
        actor=ctx.actor,
        actor_user_id=ctx.user_id,
    )
    db.commit()
    return LinkOut(url=url)


@router.post("/portal", response_model=LinkOut)
def portal(ctx: Context = Depends(_billing), db: Session = Depends(get_db)) -> LinkOut:
    t = _tenant(db, ctx)
    try:
        url = billing_service.portal_url(t)
    except billing_service.BillingError as exc:
        raise HTTPException(status_code=502 if "provider" in str(exc) else 409, detail=str(exc)) from exc
    audit_service.log_action(
        db, ctx.tenant_id, None, "BILLING_PORTAL_OPENED", "TENANT", t.id, actor=ctx.actor, actor_user_id=ctx.user_id
    )
    db.commit()
    return LinkOut(url=url)


def _apply(db: Session, event: dict[str, Any]) -> str | None:
    """Apply one Stripe event; returns the tenant id it changed, if any."""
    kind = str(event.get("type") or "")
    obj: dict[str, Any] = (event.get("data") or {}).get("object") or {}
    tenant: Tenant | None = None
    if kind == "checkout.session.completed":
        tid = obj.get("client_reference_id") or (obj.get("metadata") or {}).get("tenant_id")
        tenant = db.get(Tenant, str(tid)) if tid else None
        if tenant is not None:
            tenant.stripe_customer_id = obj.get("customer") or tenant.stripe_customer_id
            tenant.stripe_subscription_id = obj.get("subscription") or tenant.stripe_subscription_id
            plan = (obj.get("metadata") or {}).get("plan")
            if plan in billing_service.plans():
                tenant.billing_plan = plan
    elif kind.startswith("customer.subscription."):
        customer = obj.get("customer")
        tenant = db.query(Tenant).filter(Tenant.stripe_customer_id == customer).first() if customer else None
        if tenant is not None:
            items = (obj.get("items") or {}).get("data") or [{}]
            price = ((items[0] or {}).get("price") or {}).get("id")
            tenant.stripe_subscription_id = obj.get("id") or tenant.stripe_subscription_id
            tenant.billing_status = "canceled" if kind.endswith(".deleted") else str(obj.get("status") or "")
            tenant.billing_plan = billing_service.plan_for_price(price) or tenant.billing_plan
            end = obj.get("current_period_end") or ((items[0] or {}).get("current_period_end"))
            tenant.billing_period_end = datetime.fromtimestamp(int(end), UTC) if end else tenant.billing_period_end
    if tenant is None:
        return None
    set_tenant(db, tenant.id)
    audit_service.log_action(
        db,
        tenant.id,
        None,
        "BILLING_SUBSCRIPTION_UPDATED",
        "TENANT",
        tenant.id,
        after={"event": kind, "plan": tenant.billing_plan, "status": tenant.billing_status},
        actor="stripe",
    )
    return tenant.id


@router.post("/webhook", include_in_schema=True)
async def webhook(request: Request, db: Session = Depends(get_db)) -> dict[str, str]:
    payload = await request.body()
    secret = get_settings().stripe_webhook_secret.get_secret_value()
    try:
        billing_service.verify(payload, request.headers.get("stripe-signature"), secret)
        event = json.loads(payload)
    except (billing_service.SignatureError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid signature or payload.") from exc
    event_id = str(event.get("id") or "")
    if not event_id:
        raise HTTPException(status_code=400, detail="Invalid signature or payload.")
    if db.get(BillingEvent, event_id) is not None:
        return {"status": "duplicate"}
    db.add(BillingEvent(id=event_id, type=str(event.get("type") or "")[:100], received_at=utcnow()))
    changed = _apply(db, event)
    db.commit()
    log.info("stripe event %s %s applied to %s", event_id, event.get("type"), changed or "no tenant")
    return {"status": "applied" if changed else "ignored"}
