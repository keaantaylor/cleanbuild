"""Webhook endpoints and their deliveries (Settings -> Channels).

GET    /api/v1/org/webhooks                           list (org:read)
POST   /api/v1/org/webhooks                           create; the signing secret is returned once (org:manage)
DELETE /api/v1/org/webhooks/{id}                      remove (org:manage)
POST   /api/v1/org/webhooks/{id}/test                 queue a "ping" delivery (org:manage)
GET    /api/v1/org/webhooks/{id}/deliveries           recent deliveries (org:read)
POST   /api/v1/org/webhooks/deliveries/{id}/replay    send again (org:manage)
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.channels import WebhookDelivery, WebhookEndpoint
from ..security.auth import Context, require
from ..security.permissions import Permission
from ..services import audit_service, webhooks

router = APIRouter(prefix="/api/v1/org/webhooks", tags=["channels"])
_org_read = require(Permission.ORG_READ)
_org_manage = require(Permission.ORG_MANAGE)

Event = Literal["report.completed", "report.failed", "report.waiting_for_review"]


class EndpointIn(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    events: list[Event] = Field(min_length=1)
    description: str | None = Field(default=None, max_length=200)


class EndpointOut(BaseModel):
    id: str
    url: str
    events: list[str]
    description: str | None
    enabled: bool
    created_at: datetime


class EndpointCreated(EndpointOut):
    # Returned exactly once; only the encrypted value is stored.
    secret: str


class DeliveryOut(BaseModel):
    id: str
    event_type: str
    message_id: str
    status: str
    attempts: int
    last_status_code: int | None
    last_error: str | None
    next_attempt_at: datetime | None
    created_at: datetime
    delivered_at: datetime | None


def _out(ep: WebhookEndpoint) -> EndpointOut:
    return EndpointOut(
        id=ep.id,
        url=ep.url,
        events=list(ep.events or []),
        description=ep.description,
        enabled=ep.enabled,
        created_at=ep.created_at,
    )


def _endpoint_or_404(db: Session, ctx: Context, endpoint_id: str) -> WebhookEndpoint:
    ep = db.get(WebhookEndpoint, endpoint_id)
    if ep is None or ep.tenant_id != ctx.tenant_id:
        raise HTTPException(status_code=404, detail="Not found.")
    return ep


@router.get("", response_model=list[EndpointOut])
def list_endpoints(ctx: Context = Depends(_org_read), db: Session = Depends(get_db)) -> list[EndpointOut]:
    q = select(WebhookEndpoint).where(WebhookEndpoint.tenant_id == ctx.tenant_id).order_by(WebhookEndpoint.created_at)
    return [_out(ep) for ep in db.execute(q).scalars()]


@router.post("", response_model=EndpointCreated, status_code=201)
def create_endpoint(
    body: EndpointIn, ctx: Context = Depends(_org_manage), db: Session = Depends(get_db)
) -> EndpointCreated:
    try:
        ep, secret = webhooks.create_endpoint(db, ctx.tenant_id, body.url, list(body.events), body.description)
    except webhooks.WebhookTargetError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    audit_service.log_action(
        db,
        ctx.tenant_id,
        None,
        "WEBHOOK_ENDPOINT_CREATED",
        "WEBHOOK_ENDPOINT",
        ep.id,
        after={"url": ep.url, "events": ep.events},
        actor=ctx.actor,
        actor_user_id=ctx.user_id,
    )
    db.commit()
    return EndpointCreated(**_out(ep).model_dump(), secret=secret)


@router.delete("/{endpoint_id}", status_code=204)
def delete_endpoint(endpoint_id: str, ctx: Context = Depends(_org_manage), db: Session = Depends(get_db)) -> Response:
    ep = _endpoint_or_404(db, ctx, endpoint_id)
    audit_service.log_action(
        db,
        ctx.tenant_id,
        None,
        "WEBHOOK_ENDPOINT_DELETED",
        "WEBHOOK_ENDPOINT",
        ep.id,
        before={"url": ep.url, "events": ep.events},
        actor=ctx.actor,
        actor_user_id=ctx.user_id,
    )
    db.delete(ep)
    db.commit()
    return Response(status_code=204)


@router.post("/{endpoint_id}/test", response_model=DeliveryOut, status_code=202)
def test_endpoint(endpoint_id: str, ctx: Context = Depends(_org_manage), db: Session = Depends(get_db)) -> DeliveryOut:
    ep = _endpoint_or_404(db, ctx, endpoint_id)
    deliveries = [d for d in webhooks.emit(db, ctx.tenant_id, "ping", {"endpoint_id": ep.id}) if d.endpoint_id == ep.id]
    audit_service.log_action(
        db,
        ctx.tenant_id,
        None,
        "WEBHOOK_TEST_QUEUED",
        "WEBHOOK_ENDPOINT",
        ep.id,
        actor=ctx.actor,
        actor_user_id=ctx.user_id,
    )
    db.commit()
    return DeliveryOut.model_validate(deliveries[0], from_attributes=True)


@router.get("/{endpoint_id}/deliveries", response_model=list[DeliveryOut])
def list_deliveries(
    endpoint_id: str, ctx: Context = Depends(_org_read), db: Session = Depends(get_db)
) -> list[DeliveryOut]:
    ep = _endpoint_or_404(db, ctx, endpoint_id)
    q = (
        select(WebhookDelivery)
        .where(WebhookDelivery.endpoint_id == ep.id, WebhookDelivery.tenant_id == ctx.tenant_id)
        .order_by(WebhookDelivery.created_at.desc())
        .limit(100)
    )
    return [DeliveryOut.model_validate(d, from_attributes=True) for d in db.execute(q).scalars()]


@router.post("/deliveries/{delivery_id}/replay", response_model=DeliveryOut, status_code=202)
def replay_delivery(
    delivery_id: str, ctx: Context = Depends(_org_manage), db: Session = Depends(get_db)
) -> DeliveryOut:
    d = db.get(WebhookDelivery, delivery_id)
    if d is None or d.tenant_id != ctx.tenant_id:
        raise HTTPException(status_code=404, detail="Not found.")
    webhooks.replay(db, d)
    audit_service.log_action(
        db,
        ctx.tenant_id,
        None,
        "WEBHOOK_DELIVERY_REPLAYED",
        "WEBHOOK_DELIVERY",
        d.id,
        after={"message_id": d.message_id, "event": d.event_type},
        actor=ctx.actor,
        actor_user_id=ctx.user_id,
    )
    db.commit()
    return DeliveryOut.model_validate(d, from_attributes=True)
