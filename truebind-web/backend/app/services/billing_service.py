"""P9 Billing and entitlements (Stripe).

- Plans come from configuration (BILLING_PLANS): a name, the Stripe price,
  the check modules included, rows processed per calendar month and seats.
  Prices themselves live in Stripe; nothing here invents an amount.
- With BILLING_ENABLED off (development, tests, self-hosted) nothing is
  limited and every screen says billing is not enforced.
- With it on, an organisation's entitlements are those of its plan while the
  subscription is active or trialing; otherwise those of BILLING_DEFAULT_PLAN
  (if configured) or nothing chargeable.
- Stripe is called over its REST API (form-encoded, secret key as basic
  auth); webhooks are verified with the endpoint secret (Stripe-Signature:
  t=<ts>,v1=<HMAC-SHA256 hex of "<ts>.<body>">, 5-minute tolerance) and
  applied once per event id.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models.identity import Invitation, Membership, Tenant
from ..models.reports import Report
from ..settings import get_settings

ACTIVE = frozenset({"active", "trialing"})
TOLERANCE_S = 300


class BillingError(RuntimeError):
    """Customer-safe description (never Stripe's response text)."""


class SignatureError(ValueError):
    pass


class QuotaError(RuntimeError):
    """A plan limit was reached; the message says which and what to do."""


@dataclass(frozen=True)
class Entitlements:
    enforced: bool
    plan: str | None
    modules: frozenset[str] | None  # None = every module
    monthly_rows: int | None  # None = unlimited
    seats: int | None

    def allows_module(self, module: str) -> bool:
        return self.modules is None or module in self.modules


UNLIMITED = Entitlements(False, None, None, None, None)


def plans() -> dict[str, dict[str, Any]]:
    return get_settings().billing_plans


def entitlements(tenant: Tenant) -> Entitlements:
    s = get_settings()
    if not s.billing_enabled:
        return UNLIMITED
    name = tenant.billing_plan if (tenant.billing_status or "") in ACTIVE else None
    name = name if name in s.billing_plans else s.billing_default_plan
    plan = s.billing_plans.get(name or "")
    if plan is None:
        return Entitlements(True, None, frozenset(), 0, None)
    return Entitlements(True, name, frozenset(plan.get("modules") or []), plan.get("monthly_rows"), plan.get("seats"))


def month_start(now: datetime | None = None) -> datetime:
    n = now or datetime.now(UTC)
    return datetime(n.year, n.month, 1, tzinfo=UTC)


def require_rows(db: Session, tenant: Tenant, rows: int) -> None:
    """Refuse (402) processing that would take the organisation past its monthly rows."""
    ent = entitlements(tenant)
    if ent.monthly_rows is None:
        return
    used = rows_this_month(db, tenant.id)
    if used + rows > ent.monthly_rows:
        raise QuotaError(
            f"Your plan includes {ent.monthly_rows:,} rows a month; {used:,} are used and this file "
            f"has {rows:,}. Choose a larger plan under Settings -> Billing, or wait for next month."
        )


def require_seat(db: Session, tenant: Tenant) -> None:
    ent = entitlements(tenant)
    if ent.seats is not None and seats_used(db, tenant.id) >= ent.seats:
        raise QuotaError(
            f"Your plan includes {ent.seats} seats, counting pending invitations. Remove a member or "
            "invitation, or choose a larger plan under Settings -> Billing."
        )


def rows_this_month(db: Session, tenant_id: str) -> int:
    """Rows in reports processed (COMPLETE) since the start of this calendar month (UTC)."""
    q = db.query(func.coalesce(func.sum(Report.rows_processed), 0)).filter(
        Report.tenant_id == tenant_id, Report.status == "COMPLETE", Report.updated_at >= month_start()
    )
    return int(q.scalar() or 0)


def seats_used(db: Session, tenant_id: str) -> int:
    members = db.query(func.count(Membership.id)).filter(Membership.tenant_id == tenant_id).scalar() or 0
    pending = (
        db.query(func.count(Invitation.id))
        .filter(
            Invitation.tenant_id == tenant_id,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
            Invitation.expires_at > datetime.now(UTC),
        )
        .scalar()
        or 0
    )
    return int(members) + int(pending)


# ------------------------------------------------------------------ Stripe REST


def _flatten(data: dict[str, Any], prefix: str = "") -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for k, v in data.items():
        key = f"{prefix}[{k}]" if prefix else k
        if isinstance(v, dict):
            out.extend(_flatten(v, key))
        elif isinstance(v, list):
            for i, item in enumerate(v):
                if isinstance(item, dict):
                    out.extend(_flatten(item, f"{key}[{i}]"))
                else:
                    out.append((f"{key}[{i}]", str(item)))
        elif v is not None:
            out.append((key, str(v).lower() if isinstance(v, bool) else str(v)))
    return out


def stripe_post(path: str, data: dict[str, Any], client: httpx.Client | None = None) -> dict[str, Any]:
    s = get_settings()
    key = s.stripe_secret_key.get_secret_value()
    if not key:
        raise BillingError("Billing is not configured on this server.")
    own = client is None
    c = client or httpx.Client(timeout=20)
    try:
        r = c.post(f"{s.stripe_api_base.rstrip('/')}{path}", data=dict(_flatten(data)), auth=(key, ""))
    except httpx.HTTPError as exc:
        raise BillingError(f"The payment provider could not be reached ({type(exc).__name__}).") from exc
    finally:
        if own:
            c.close()
    if r.status_code >= 400:
        raise BillingError(f"The payment provider refused the request (HTTP {r.status_code}).")
    body: dict[str, Any] = r.json()
    return body


def checkout_url(tenant: Tenant, plan: str, email: str, client: httpx.Client | None = None) -> str:
    s = get_settings()
    cfg = s.billing_plans.get(plan)
    if cfg is None or not cfg.get("price_id"):
        raise BillingError("That plan cannot be bought online.")
    if not tenant.stripe_customer_id:
        customer = stripe_post(
            "/v1/customers", {"email": email, "name": tenant.name, "metadata": {"tenant_id": tenant.id}}, client
        )
        tenant.stripe_customer_id = str(customer["id"])
    session = stripe_post(
        "/v1/checkout/sessions",
        {
            "mode": "subscription",
            "customer": tenant.stripe_customer_id,
            "client_reference_id": tenant.id,
            "line_items": [{"price": cfg["price_id"], "quantity": 1}],
            "success_url": f"{s.public_app_url.rstrip('/')}/settings?tab=billing&checkout=done",
            "cancel_url": f"{s.public_app_url.rstrip('/')}/settings?tab=billing",
            "metadata": {"tenant_id": tenant.id, "plan": plan},
        },
        client,
    )
    return str(session["url"])


def portal_url(tenant: Tenant, client: httpx.Client | None = None) -> str:
    if not tenant.stripe_customer_id:
        raise BillingError("There is no subscription to manage yet.")
    s = get_settings()
    session = stripe_post(
        "/v1/billing_portal/sessions",
        {
            "customer": tenant.stripe_customer_id,
            "return_url": f"{s.public_app_url.rstrip('/')}/settings?tab=billing",
        },
        client,
    )
    return str(session["url"])


# ------------------------------------------------------------------ webhooks


def sign(payload: bytes, secret: str, ts: int | None = None) -> str:
    t = int(time.time()) if ts is None else ts
    mac = hmac.new(secret.encode(), f"{t}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={t},v1={mac}"


def verify(payload: bytes, header: str | None, secret: str, now: float | None = None) -> None:
    if not secret:
        raise SignatureError("webhook secret not configured")
    parts: dict[str, list[str]] = {}
    for item in (header or "").split(","):
        k, _, v = item.strip().partition("=")
        parts.setdefault(k, []).append(v)
    try:
        ts = int(parts["t"][0])
    except (KeyError, ValueError, IndexError) as exc:
        raise SignatureError("missing timestamp") from exc
    if abs((now or time.time()) - ts) > TOLERANCE_S:
        raise SignatureError("timestamp outside tolerance")
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, v) for v in parts.get("v1", [])):
        raise SignatureError("signature mismatch")


def plan_for_price(price_id: str | None) -> str | None:
    return next((name for name, cfg in plans().items() if price_id and cfg.get("price_id") == price_id), None)
