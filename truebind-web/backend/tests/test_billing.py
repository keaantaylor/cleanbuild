"""P9 -- billing and entitlements (Stripe).

Acceptance:
- with BILLING_ENABLED off, nothing is limited and the API says billing is
  not enforced; online checkout is refused;
- enabling billing requires the Stripe keys and at least one valid plan
  (modules, monthly rows, seats); plans come from configuration, prices from
  Stripe -- no amount is invented;
- checkout creates the Stripe customer once and returns a Checkout link for
  the plan's price; the customer portal needs an existing customer;
- webhooks are refused unless correctly signed within 5 minutes, are applied
  once per event id, and move the organisation's plan and status;
- entitlements are enforced: modules outside the plan are NOT_ASSESSED with
  the reason, processing beyond the monthly rows is refused with 402 and a
  plain message, invitations beyond the seats are refused with 402;
- only owners (billing:manage) see or change billing; every change is audited.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from app.services import billing_service
from app.settings import Settings, get_settings
from conftest import Api, run_jobs, simple_rows, xlsx_bytes
from pydantic import ValidationError

WHSEC = "whsec_test_only_billing"
PLANS = {
    "essentials": {"label": "Essentials", "price_id": "price_ess", "modules": ["binder"], "monthly_rows": 5,
                   "seats": 2},
    "professional": {"label": "Professional", "price_id": "price_pro",
                     "modules": ["binder", "leakage", "sanctions"], "monthly_rows": None, "seats": None},
}  # fmt: skip


@pytest.fixture
def billing_on(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[httpx.Request]]:
    monkeypatch.setenv("BILLING_ENABLED", "true")
    monkeypatch.setenv("BILLING_PLANS", json.dumps(PLANS))
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_only")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", WHSEC)
    get_settings.cache_clear()
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/v1/customers":
            return httpx.Response(200, json={"id": "cus_123"})
        if request.url.path == "/v1/checkout/sessions":
            return httpx.Response(200, json={"id": "cs_1", "url": "https://checkout.stripe.test/cs_1"})
        if request.url.path == "/v1/billing_portal/sessions":
            return httpx.Response(200, json={"id": "bps_1", "url": "https://billing.stripe.test/p/1"})
        return httpx.Response(404, json={"error": {"message": "secret detail"}})

    real = httpx.Client
    monkeypatch.setattr(
        "app.services.billing_service.httpx.Client", lambda **kw: real(transport=httpx.MockTransport(handler), **kw)
    )
    yield seen
    monkeypatch.undo()
    get_settings.cache_clear()


def _event(api: Api, body: dict[str, Any], ts: int | None = None, secret: str = WHSEC) -> Any:
    raw = json.dumps(body).encode()
    sig = billing_service.sign(raw, secret, ts)
    return api.client.post(
        "/api/v1/billing/webhook", content=raw, headers={"Stripe-Signature": sig, "Content-Type": "application/json"}
    )


def test_billing_off_means_unlimited(api: Api) -> None:
    out = api.get("/api/v1/billing").json()
    assert out["enforced"] is False and out["modules"] is None and out["monthly_rows"] is None
    assert api.post("/api/v1/billing/checkout", json={"plan": "essentials"}).status_code == 409


@pytest.mark.parametrize(
    ("env", "fragment"),
    [
        ({"BILLING_ENABLED": "true"}, "STRIPE_SECRET_KEY"),
        ({"BILLING_ENABLED": "true", "STRIPE_SECRET_KEY": "sk", "STRIPE_WEBHOOK_SECRET": "w",
          "BILLING_PLANS": json.dumps({"x": {"modules": ["nope"]}})}, "unknown module"),
        ({"BILLING_ENABLED": "true", "STRIPE_SECRET_KEY": "sk", "STRIPE_WEBHOOK_SECRET": "w",
          "BILLING_PLANS": json.dumps(PLANS), "BILLING_DEFAULT_PLAN": "gold"}, "BILLING_DEFAULT_PLAN"),
    ],
)  # fmt: skip
def test_billing_configuration_is_validated(
    monkeypatch: pytest.MonkeyPatch, env: dict[str, str], fragment: str
) -> None:
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    with pytest.raises(ValidationError, match=fragment):
        Settings()


def test_checkout_portal_and_webhooks(api: Api, billing_on: list[httpx.Request]) -> None:
    out = api.get("/api/v1/billing").json()
    assert out["enforced"] is True and out["plan"] is None and out["modules"] == []
    assert {p["name"] for p in out["plans"]} == {"essentials", "professional"}
    assert api.post("/api/v1/billing/portal").status_code == 409  # no customer yet
    link = api.post("/api/v1/billing/checkout", json={"plan": "essentials"})
    assert link.json() == {"url": "https://checkout.stripe.test/cs_1"}
    api.post("/api/v1/billing/checkout", json={"plan": "essentials"})
    assert [r.url.path for r in billing_on].count("/v1/customers") == 1, "the customer is created once"
    form = billing_on[1].content.decode()
    assert "line_items%5B0%5D%5Bprice%5D=price_ess" in form and "mode=subscription" in form
    assert billing_on[1].headers["authorization"].startswith("Basic ")
    assert api.post("/api/v1/billing/checkout", json={"plan": "platinum"}).status_code == 409
    tid = api.me["tenant"]["id"]

    completed = {"id": "evt_1", "type": "checkout.session.completed",
                 "data": {"object": {"client_reference_id": tid, "customer": "cus_123", "subscription": "sub_1",
                                     "metadata": {"plan": "essentials"}}}}  # fmt: skip
    assert _event(api, completed, secret="whsec_wrong").status_code == 400
    assert _event(api, completed, ts=int(time.time()) - 3600).status_code == 400
    assert _event(api, completed).json() == {"status": "applied"}
    assert _event(api, completed).json() == {"status": "duplicate"}
    updated = {"id": "evt_2", "type": "customer.subscription.updated",
               "data": {"object": {"id": "sub_1", "customer": "cus_123", "status": "active",
                                   "current_period_end": 1893456000,
                                   "items": {"data": [{"price": {"id": "price_ess"}}]}}}}  # fmt: skip
    assert _event(api, updated).json() == {"status": "applied"}
    out = api.get("/api/v1/billing").json()
    assert out["plan"] == "essentials" and out["status"] == "active" and out["modules"] == ["binder"]
    assert out["period_end"].startswith("2030-01-01")
    assert api.post("/api/v1/billing/portal").json() == {"url": "https://billing.stripe.test/p/1"}
    actions = {e["action_type"] for e in api.get("/api/v1/audit").json()["items"]}
    assert {"BILLING_CHECKOUT_STARTED", "BILLING_SUBSCRIPTION_UPDATED", "BILLING_PORTAL_OPENED"} <= actions
    deleted = {**updated, "id": "evt_3", "type": "customer.subscription.deleted"}
    _event(api, deleted)
    assert api.get("/api/v1/billing").json()["modules"] == [], "a cancelled subscription entitles nothing"


def test_entitlements_are_enforced(api: Api, billing_on: list[httpx.Request]) -> None:
    tid = api.me["tenant"]["id"]
    done = {"client_reference_id": tid, "customer": "cus_9", "metadata": {"plan": "essentials"}}
    _event(api, {"id": "evt_a", "type": "checkout.session.completed", "data": {"object": done}})
    _event(api, {"id": "evt_b", "type": "customer.subscription.created",
                 "data": {"object": {"id": "sub_9", "customer": "cus_9", "status": "trialing",
                                     "items": {"data": [{"price": {"id": "price_ess"}}]}}}})  # fmt: skip
    rid, _ = api.full_run("e.xlsx", xlsx_bytes(simple_rows(3)))
    runs = {r["module"]: r for r in api.get(f"/api/v1/reports/{rid}/checks").json()}
    assert runs["leakage"]["state"] == "NOT_ASSESSED" and "not included in your plan" in runs["leakage"]["reason"]
    assert runs["binder"]["reason"] != runs["leakage"]["reason"]
    rid2 = api.ingest("f.xlsx", xlsx_bytes(simple_rows(3)))  # 3 + 3 rows > 5 a month
    api.confirm_all(rid2)
    r = api.post(f"/api/v1/reports/{rid2}/process")
    assert r.status_code == 402 and "5 rows a month" in r.json()["detail"]
    run_jobs()
    api.post("/api/v1/org/invitations", json={"email": "a@a.example", "role": "VIEWER"})
    r = api.post("/api/v1/org/invitations", json={"email": "b@a.example", "role": "VIEWER"})
    assert r.status_code == 402 and "2 seats" in r.json()["detail"]
