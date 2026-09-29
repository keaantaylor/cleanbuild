"""Outbound webhooks, signed the Standard Webhooks / Svix way.

Every delivery carries
  webhook-id:        the message id (stable across retries and replays)
  webhook-timestamp: unix seconds of this attempt
  webhook-signature: "v1,<base64 HMAC-SHA256(secret, id.timestamp.body)>"
where the secret is the endpoint's "whsec_<base64>" key, shown once at
creation and stored encrypted. Receivers verify with verify_signature().

- emit() queues one delivery per subscribed endpoint; nothing is sent in the
  request that caused the event.
- dispatch_due() (worker housekeeping) sends due deliveries: 2xx =
  DELIVERED; anything else is retried with backoff (30 s, 2 m, 10 m, 1 h,
  6 h ...) until WEBHOOK_MAX_ATTEMPTS, then EXHAUSTED with an alert.
- replay() re-queues any delivery on request (audited).
- SSRF: targets must be https and resolve only to public addresses (checked
  at creation and again before every send, against DNS rebinding); no
  redirects are followed. WEBHOOK_ALLOW_PRIVATE_TARGETS relaxes this for
  local testing only.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import logging
import secrets
import socket
import time
import uuid
from datetime import timedelta
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..database import set_tenant
from ..models._util import utcnow
from ..models.channels import WEBHOOK_EVENTS, WebhookDelivery, WebhookEndpoint
from ..security import crypto
from . import alert_service

log = logging.getLogger("truebind.webhooks")

SECRET_PURPOSE = "webhook-secret"  # noqa: S105 -- a key-derivation label, not a secret
BACKOFF_S = (30, 120, 600, 3600, 6 * 3600, 12 * 3600)
TOLERANCE_S = 300


class WebhookTargetError(ValueError):
    pass


# ------------------------------------------------------------------ signing


def new_secret() -> str:
    return "whsec_" + base64.b64encode(secrets.token_bytes(32)).decode()


def _key(secret: str) -> bytes:
    return base64.b64decode(secret.removeprefix("whsec_"))


def sign(secret: str, message_id: str, timestamp: int, body: bytes) -> str:
    mac = hmac.new(_key(secret), f"{message_id}.{timestamp}.".encode() + body, hashlib.sha256).digest()
    return "v1," + base64.b64encode(mac).decode()


def verify_signature(secret: str, headers: dict[str, str], body: bytes, now: float | None = None) -> bool:
    """What a receiver does: check the timestamp window and any v1 signature."""
    lower = {k.lower(): v for k, v in headers.items()}
    try:
        ts = int(lower["webhook-timestamp"])
        msg_id = lower["webhook-id"]
    except (KeyError, ValueError):
        return False
    if abs((now if now is not None else time.time()) - ts) > TOLERANCE_S:
        return False
    expected = sign(secret, msg_id, ts, body).split(",", 1)[1]
    for part in lower.get("webhook-signature", "").split():
        version, _, sig = part.partition(",")
        if version == "v1" and hmac.compare_digest(sig, expected):
            return True
    return False


# ------------------------------------------------------------------ SSRF guard


def check_target(url: str) -> None:
    parsed = urlparse(url)
    allow_private = config.WEBHOOK_ALLOW_PRIVATE_TARGETS
    if parsed.scheme != "https" and not (allow_private and parsed.scheme == "http"):
        raise WebhookTargetError("Webhook URLs must use https.")
    if not parsed.hostname or parsed.username or parsed.password:
        raise WebhookTargetError("Webhook URLs need a host and must not contain credentials.")
    if allow_private:
        return
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise WebhookTargetError("The webhook host does not resolve.") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip.is_multicast:
            raise WebhookTargetError("Webhook URLs must point to a public internet address.")


# ------------------------------------------------------------------ endpoints and events


def create_endpoint(
    db: Session, tenant_id: str, url: str, events: list[str], description: str | None
) -> tuple[WebhookEndpoint, str]:
    unknown = sorted(set(events) - set(WEBHOOK_EVENTS))
    if unknown or not events:
        raise WebhookTargetError(f"Choose events from: {', '.join(WEBHOOK_EVENTS)}.")
    check_target(url)
    secret = new_secret()
    ep = WebhookEndpoint(
        tenant_id=tenant_id,
        url=url,
        events=sorted(set(events)),
        description=description,
        secret_enc=crypto.encrypt(SECRET_PURPOSE, secret),
        enabled=True,
    )
    db.add(ep)
    db.flush()
    return ep, secret


def emit(db: Session, tenant_id: str, event_type: str, data: dict[str, Any]) -> list[WebhookDelivery]:
    endpoints = (
        db.execute(
            select(WebhookEndpoint).where(WebhookEndpoint.tenant_id == tenant_id, WebhookEndpoint.enabled.is_(True))
        )
        .scalars()
        .all()
    )
    out = []
    now = utcnow()
    for ep in endpoints:
        if event_type not in (ep.events or []) and event_type != "ping":
            continue
        msg_id = "msg_" + uuid.uuid4().hex
        payload = {"type": event_type, "timestamp": now.isoformat(), "data": data}
        d = WebhookDelivery(
            tenant_id=tenant_id,
            endpoint_id=ep.id,
            event_type=event_type,
            message_id=msg_id,
            payload=payload,
            status="PENDING",
            attempts=0,
            next_attempt_at=now,
        )
        db.add(d)
        out.append(d)
    db.flush()
    return out


def replay(db: Session, delivery: WebhookDelivery) -> None:
    delivery.status = "PENDING"
    delivery.next_attempt_at = utcnow()


# ------------------------------------------------------------------ dispatch


def _attempt(db: Session, d: WebhookDelivery, client: httpx.Client) -> None:
    ep = db.get(WebhookEndpoint, d.endpoint_id)
    now = utcnow()
    d.attempts += 1
    if ep is None or not ep.enabled:
        d.status, d.last_error, d.next_attempt_at = "EXHAUSTED", "Endpoint removed or disabled.", None
        return
    body = json.dumps(d.payload, separators=(",", ":"), sort_keys=True).encode()
    ts = int(time.time())
    headers = {
        "content-type": "application/json",
        "user-agent": "TrueBind-Webhooks/1",
        "webhook-id": d.message_id,
        "webhook-timestamp": str(ts),
        "webhook-signature": sign(crypto.decrypt(SECRET_PURPOSE, ep.secret_enc), d.message_id, ts, body),
    }
    try:
        check_target(ep.url)
        r = client.post(ep.url, content=body, headers=headers)
        d.last_status_code = r.status_code
        ok = 200 <= r.status_code < 300
        d.last_error = None if ok else f"Receiver answered HTTP {r.status_code}."
    except WebhookTargetError as exc:
        ok, d.last_status_code, d.last_error = False, None, str(exc)[:300]
    except httpx.HTTPError as exc:
        ok, d.last_status_code, d.last_error = False, None, f"Connection failed ({type(exc).__name__})."
    if ok:
        d.status, d.delivered_at, d.next_attempt_at = "DELIVERED", now, None
    elif d.attempts >= config.WEBHOOK_MAX_ATTEMPTS:
        d.status, d.next_attempt_at = "EXHAUSTED", None
        report_id = str((d.payload.get("data") or {}).get("report_id") or "")
        if report_id:  # a delivery without a report (a test ping) stays visible in Settings only
            alert_service.raise_alert(
                db,
                d.tenant_id,
                report_id,
                "MEDIUM",
                alert_service.EXPORT_FAILED,
                f"Webhook {d.event_type} to {urlparse(ep.url).hostname} failed {d.attempts} times and was given "
                "up. Fix the receiver, then replay it from Settings.",
            )
    else:
        d.status = "FAILED"
        d.next_attempt_at = now + timedelta(seconds=BACKOFF_S[min(d.attempts - 1, len(BACKOFF_S) - 1)])


def dispatch_due(db: Session, client: httpx.Client | None = None, limit: int = 50) -> int:
    """Send every due delivery (all organisations). Returns how many were attempted."""
    set_tenant(db, None, worker=True)
    due = [
        (d.id, d.tenant_id)
        for d in db.execute(
            select(WebhookDelivery)
            .where(WebhookDelivery.status.in_(("PENDING", "FAILED")), WebhookDelivery.next_attempt_at <= utcnow())
            .order_by(WebhookDelivery.next_attempt_at)
            .limit(limit)
        ).scalars()
    ]
    db.commit()
    own = client is None
    http = client or httpx.Client(timeout=10, follow_redirects=False)
    try:
        for delivery_id, tenant_id in due:
            set_tenant(db, tenant_id)
            d = db.get(WebhookDelivery, delivery_id)
            if d is None or d.status not in ("PENDING", "FAILED"):
                db.commit()
                continue
            _attempt(db, d, http)
            db.commit()
    finally:
        if own:
            http.close()
    return len(due)
