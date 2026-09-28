"""P2.3 -- webhooks over real HTTP to the compose receiver (TRUEBIND_IT=1).

A completed report is delivered, signed, to a live HTTP endpoint and the
receiver can verify the signature with the secret it was given; an endpoint
answering 500 is retried rather than marked delivered."""

from __future__ import annotations

import json

import httpx
import pytest
from app import config
from app.database import set_tenant
from app.models.channels import WebhookDelivery
from app.services import webhooks
from conftest import Api, simple_rows, xlsx_bytes
from integration_env import IT, service_url
from sqlalchemy.orm import Session

pytestmark = pytest.mark.skipif(not IT, reason="integration: needs docker-compose.test.yml (TRUEBIND_IT=1)")


def test_signed_delivery_reaches_a_live_receiver(api: Api, db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "WEBHOOK_ALLOW_PRIVATE_TARGETS", True)  # the receiver runs on localhost
    base = service_url("WEBHOOK_RECEIVER")
    httpx.delete(f"{base}/deliveries", timeout=10)
    secret = api.post("/api/v1/org/webhooks", json={"url": f"{base}/hooks/ok", "events": ["report.completed"]}).json()[
        "secret"
    ]
    api.post("/api/v1/org/webhooks", json={"url": f"{base}/hooks/down?status=500", "events": ["report.completed"]})
    api.full_run("a.xlsx", xlsx_bytes(simple_rows()))

    assert webhooks.dispatch_due(db) == 2
    received = httpx.get(f"{base}/deliveries", timeout=10).json()
    ok = [r for r in received if str(r["path"]).startswith("/hooks/ok")]
    assert len(ok) == 1
    body = str(ok[0]["body"]).encode()
    headers = {str(k): str(v) for k, v in dict(ok[0]["headers"]).items()}
    assert webhooks.verify_signature(secret, headers, body)
    assert json.loads(body)["type"] == "report.completed"

    db.expire_all()
    set_tenant(db, api.me["tenant"]["id"])
    states = sorted((d.status, d.last_status_code) for d in db.query(WebhookDelivery).all())
    assert states == [("DELIVERED", 200), ("FAILED", 500)]
