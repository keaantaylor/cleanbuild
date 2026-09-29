"""P9 -- the Stripe REST calls against stripe-mock (TRUEBIND_IT=1).

stripe-mock validates every request against Stripe's published OpenAPI
specification, so a malformed customer, Checkout Session or portal session
request fails here even though no real Stripe account is used."""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest
from app.models.identity import Tenant
from app.services import billing_service
from app.settings import get_settings
from integration_env import IT, service_url

pytestmark = pytest.mark.skipif(not IT, reason="integration: needs docker-compose.test.yml (TRUEBIND_IT=1)")


@pytest.fixture
def stripe_mock(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("BILLING_ENABLED", "true")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_it_only")
    monkeypatch.setenv("STRIPE_API_BASE", service_url("STRIPE_API"))
    monkeypatch.setenv("BILLING_PLANS", json.dumps({"pro": {"price_id": "price_1", "modules": ["binder"]}}))
    get_settings.cache_clear()
    yield
    monkeypatch.undo()
    get_settings.cache_clear()


def test_customer_checkout_and_portal_requests_are_valid_stripe_calls(stripe_mock: None) -> None:
    tenant = Tenant(id="t-it", name="IT Org")
    url = billing_service.checkout_url(tenant, "pro", "owner@it.example")
    assert url.startswith("https://") and tenant.stripe_customer_id
    assert billing_service.portal_url(tenant).startswith("https://")
