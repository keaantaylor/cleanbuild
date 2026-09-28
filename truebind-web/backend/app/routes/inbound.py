"""E-mail intake endpoints.

Provider webhooks (no user session):
- POST /api/v1/inbound/email/postmark -- HTTP Basic auth, password =
  INBOUND_WEBHOOK_SECRET (Postmark sends credentials embedded in the URL).
- POST /api/v1/inbound/email/ses -- an SNS message, verified against the
  AWS signing certificate and the SES_SNS_TOPIC_ARNS allow-list.
Both answer 200 once the message is handled (including "no such address",
so providers do not retry); 401 for bad credentials; 503 when not set up.

Organisation settings (signed in):
- GET  /api/v1/org/inbound         -- the inbound address (org:read)
- POST /api/v1/org/inbound/rotate  -- a new address; the old one stops working (org:manage)
"""

from __future__ import annotations

import base64
import binascii
import json
import secrets
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import config
from ..database import get_db
from ..models.identity import Tenant
from ..security import sns
from ..security.auth import Context, require
from ..security.permissions import Permission
from ..services import audit_service, inbound_email

provider_router = APIRouter(prefix="/api/v1/inbound/email", tags=["inbound"])
router = APIRouter(prefix="/api/v1/org/inbound", tags=["organisation"])

MAX_WEBHOOK_BYTES = 40 * 1024 * 1024
_org_read = require(Permission.ORG_READ)
_org_manage = require(Permission.ORG_MANAGE)


class InboundAddressOut(BaseModel):
    address: str | None
    configured: bool


class IntakeOut(BaseModel):
    accepted: int
    rejected: int
    duplicates: int


def _check_basic_auth(request: Request) -> None:
    secret = config.INBOUND_WEBHOOK_SECRET
    if not secret:
        raise HTTPException(status_code=503, detail="E-mail intake is not configured on this server.")
    header = request.headers.get("authorization", "")
    scheme, _, value = header.partition(" ")
    try:
        _user, _, password = base64.b64decode(value, validate=True).decode().partition(":")
    except (binascii.Error, ValueError, UnicodeDecodeError):
        password = ""
    if scheme.lower() != "basic" or not secrets.compare_digest(password.encode(), secret.encode()):
        raise HTTPException(status_code=401, detail="Unauthorised.", headers={"WWW-Authenticate": "Basic"})


async def _json_body(request: Request) -> dict[str, Any]:
    body = await request.body()
    if len(body) > MAX_WEBHOOK_BYTES:
        raise HTTPException(status_code=413, detail="Message too large.")
    try:
        parsed = json.loads(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Body must be JSON.") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object.")
    return parsed


def _out(result: inbound_email.IntakeResult) -> IntakeOut:
    return IntakeOut(accepted=len(result.accepted), rejected=len(result.rejected), duplicates=result.duplicates)


@provider_router.post("/postmark", response_model=IntakeOut)
async def postmark_inbound(request: Request, db: Session = Depends(get_db)) -> IntakeOut:
    _check_basic_auth(request)
    payload = await _json_body(request)
    return _out(inbound_email.ingest(db, inbound_email.from_postmark(payload), "postmark"))


@provider_router.post("/ses", response_model=IntakeOut)
async def ses_inbound(request: Request, db: Session = Depends(get_db)) -> IntakeOut:
    if not config.SES_SNS_TOPIC_ARNS or not config.INBOUND_EMAIL_DOMAIN:
        raise HTTPException(status_code=503, detail="E-mail intake is not configured on this server.")
    message = await _json_body(request)
    try:
        sns.verify({k: str(v) for k, v in message.items() if v is not None}, config.SES_SNS_TOPIC_ARNS)
    except sns.SnsVerificationError as exc:
        raise HTTPException(status_code=401, detail="Unauthorised.") from exc
    kind = message.get("Type")
    if kind == "SubscriptionConfirmation":
        url = str(message.get("SubscribeURL", ""))
        if url.startswith("https://sns.") and ".amazonaws.com/" in url:
            httpx.get(url, timeout=10)
        return IntakeOut(accepted=0, rejected=0, duplicates=0)
    if kind != "Notification":
        return IntakeOut(accepted=0, rejected=0, duplicates=0)
    try:
        notification = json.loads(str(message.get("Message", "")))
        mail = notification.get("mail") or {}
        raw = base64.b64decode(str(notification.get("content", "")), validate=True)
    except (ValueError, binascii.Error, AttributeError) as exc:
        raise HTTPException(status_code=400, detail="Unreadable SES notification.") from exc
    msg = inbound_email.from_mime(raw, [str(d) for d in mail.get("destination") or []], str(mail.get("messageId", "")))
    return _out(inbound_email.ingest(db, msg, "ses"))


@router.get("", response_model=InboundAddressOut)
def get_inbound(ctx: Context = Depends(_org_read), db: Session = Depends(get_db)) -> InboundAddressOut:
    tenant = db.get(Tenant, ctx.tenant_id)
    token = tenant.inbound_token if tenant else None
    return InboundAddressOut(address=inbound_email.address_for(token), configured=bool(config.INBOUND_EMAIL_DOMAIN))


@router.post("/rotate", response_model=InboundAddressOut)
def rotate_inbound(ctx: Context = Depends(_org_manage), db: Session = Depends(get_db)) -> InboundAddressOut:
    tenant = db.get(Tenant, ctx.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Not found.")
    had = tenant.inbound_token is not None
    tenant.inbound_token = inbound_email.new_token()
    audit_service.log_action(
        db,
        ctx.tenant_id,
        None,
        "INBOUND_ADDRESS_ROTATED" if had else "INBOUND_ADDRESS_CREATED",
        "ORGANISATION",
        ctx.tenant_id,
        actor=ctx.actor,
        actor_user_id=ctx.user_id,
    )
    db.commit()
    return InboundAddressOut(
        address=inbound_email.address_for(tenant.inbound_token), configured=bool(config.INBOUND_EMAIL_DOMAIN)
    )
