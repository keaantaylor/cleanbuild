"""P2.3 -- outbound webhooks (Standard Webhooks / Svix-style signing).

Acceptance:
- an admin registers an https endpoint for chosen events; the signing
  secret ("whsec_...") is returned once and never again; creation and
  removal are audited; viewers cannot manage endpoints;
- SSRF: plain http, credentials in the URL and hosts resolving to private,
  loopback or link-local addresses are refused;
- finishing a report queues report.waiting_for_review / report.completed /
  report.failed for subscribed endpoints only; nothing is sent in the request;
- the dispatcher signs each delivery (webhook-id, webhook-timestamp,
  webhook-signature "v1,<HMAC-SHA256>") so a receiver can verify it with the
  secret; a tampered body or stale timestamp does not verify;
- a non-2xx answer is retried with growing backoff and gives up after
  WEBHOOK_MAX_ATTEMPTS (EXHAUSTED, with an alert on the report); redirects
  are not followed;
- a delivery can be replayed (audited) and keeps its message id;
- deliveries of one organisation are invisible to another.
"""

from __future__ import annotations

import json
import time
from datetime import timedelta
from typing import Any

import httpx
import pytest
from app import config
from app.database import set_tenant
from app.models._util import utcnow
from app.models.alerts import Alert
from app.models.audit import AuditLogEntry
from app.models.channels import WebhookDelivery
from app.services import webhooks
from conftest import Api, run_jobs, simple_rows, xlsx_bytes
from sqlalchemy.orm import Session

URL = "https://hooks.partner.example/truebind"


@pytest.fixture(autouse=True)
def public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve test hosts to a public address unless a test says otherwise."""

    def fake_getaddrinfo(host: str, *args: Any, **kwargs: Any) -> list[Any]:
        ip = {"internal.partner.example": "10.0.0.5", "localhost": "127.0.0.1"}.get(host, "93.184.216.34")
        return [(2, 1, 6, "", (ip, 443))]

    monkeypatch.setattr("app.services.webhooks.socket.getaddrinfo", fake_getaddrinfo)


class Receiver:
    def __init__(self, statuses: list[int] | None = None) -> None:
        self.statuses = list(statuses or [])
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        status = self.statuses.pop(0) if self.statuses else 200
        if status == 302:
            return httpx.Response(302, headers={"location": "https://elsewhere.example/"})
        return httpx.Response(status)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self), follow_redirects=False)


def _create(api: Api, events: list[str] | None = None, url: str = URL) -> Any:
    return api.post("/api/v1/org/webhooks", json={"url": url, "events": events or ["report.completed"]})


def _due_now(db: Session) -> None:
    db.expire_all()
    set_tenant(db, None, worker=True)
    for d in db.query(WebhookDelivery).all():
        if d.status in ("PENDING", "FAILED"):
            d.next_attempt_at = utcnow() - timedelta(seconds=1)
    db.commit()


def test_register_endpoint_secret_shown_once_and_audited(api: Api, db: Session) -> None:
    r = _create(api, ["report.completed", "report.failed"])
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["secret"].startswith("whsec_") and body["events"] == ["report.completed", "report.failed"]
    listed = api.get("/api/v1/org/webhooks").json()
    assert listed[0]["id"] == body["id"] and "secret" not in listed[0]
    assert db.query(AuditLogEntry).filter_by(action_type="WEBHOOK_ENDPOINT_CREATED").count() == 1
    assert api.delete(f"/api/v1/org/webhooks/{body['id']}").status_code == 204
    assert db.query(AuditLogEntry).filter_by(action_type="WEBHOOK_ENDPOINT_DELETED").count() == 1
    assert api.get("/api/v1/org/webhooks").json() == []


@pytest.mark.parametrize(
    "url",
    [
        "http://hooks.partner.example/x",
        "https://user:pw@hooks.partner.example/x",
        "https://internal.partner.example/x",
        "https://localhost/x",
        "ftp://hooks.partner.example/x",
    ],
)
def test_unsafe_targets_are_refused(api: Api, url: str) -> None:
    r = _create(api, url=url)
    assert r.status_code == 422, r.text


def test_unknown_events_are_refused(api: Api) -> None:
    assert _create(api, ["report.exploded"]).status_code == 422


def test_report_events_are_queued_for_subscribers_only(api: Api, db: Session) -> None:
    _create(api, ["report.completed"])
    _create(api, ["report.waiting_for_review"], url="https://other.partner.example/hook")
    rid, _ = api.full_run("a.xlsx", xlsx_bytes(simple_rows()))
    db.expire_all()
    set_tenant(db, api.me["tenant"]["id"])
    events = sorted(d.event_type for d in db.query(WebhookDelivery).all())
    assert events == ["report.completed", "report.waiting_for_review"]
    completed = db.query(WebhookDelivery).filter_by(event_type="report.completed").one()
    assert completed.payload["data"]["report_id"] == rid and completed.status == "PENDING"


def test_deliveries_are_signed_and_verifiable(api: Api, db: Session) -> None:
    secret = _create(api).json()["secret"]
    api.full_run("a.xlsx", xlsx_bytes(simple_rows()))
    receiver = Receiver()
    assert webhooks.dispatch_due(db, client=receiver.client()) == 1
    [req] = receiver.requests
    headers = dict(req.headers)
    assert headers["webhook-id"].startswith("msg_")
    assert headers["webhook-signature"].startswith("v1,")
    assert webhooks.verify_signature(secret, headers, req.content)
    assert json.loads(req.content)["type"] == "report.completed"
    assert not webhooks.verify_signature(secret, headers, req.content + b" ")
    assert not webhooks.verify_signature(secret, headers, req.content, now=time.time() + 3600)
    assert not webhooks.verify_signature(webhooks.new_secret(), headers, req.content)
    db.expire_all()
    set_tenant(db, api.me["tenant"]["id"])
    d = db.query(WebhookDelivery).one()
    assert d.status == "DELIVERED" and d.attempts == 1 and d.last_status_code == 200


def test_failures_back_off_then_give_up(api: Api, db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "WEBHOOK_MAX_ATTEMPTS", 3)
    _create(api)
    rid, _ = api.full_run("a.xlsx", xlsx_bytes(simple_rows()))
    receiver = Receiver([500, 302, 503])
    delays = []
    for _ in range(3):
        before = utcnow()
        webhooks.dispatch_due(db, client=receiver.client())
        db.expire_all()
        set_tenant(db, api.me["tenant"]["id"])
        d = db.query(WebhookDelivery).one()
        if d.next_attempt_at is not None:
            nxt = d.next_attempt_at if d.next_attempt_at.tzinfo else d.next_attempt_at.replace(tzinfo=before.tzinfo)
            delays.append((nxt - before).total_seconds())
        _due_now(db)
    assert len(receiver.requests) == 3, "a 302 is a failure, not followed"
    set_tenant(db, api.me["tenant"]["id"])
    d = db.query(WebhookDelivery).one()
    assert d.status == "EXHAUSTED" and d.attempts == 3 and d.last_status_code == 503
    assert delays[0] >= 25 and delays[1] > delays[0], delays
    assert db.query(Alert).filter(Alert.report_id == rid, Alert.message.like("Webhook%")).count() == 1
    webhooks.dispatch_due(db, client=receiver.client())
    assert len(receiver.requests) == 3, "an exhausted delivery is not retried on its own"


def test_replay_resends_with_the_same_message_id(api: Api, db: Session) -> None:
    ep = _create(api).json()
    api.full_run("a.xlsx", xlsx_bytes(simple_rows()))
    receiver = Receiver()
    webhooks.dispatch_due(db, client=receiver.client())
    [first] = api.get(f"/api/v1/org/webhooks/{ep['id']}/deliveries").json()
    r = api.post(f"/api/v1/org/webhooks/deliveries/{first['id']}/replay")
    assert r.status_code == 202 and r.json()["status"] == "PENDING"
    webhooks.dispatch_due(db, client=receiver.client())
    assert len(receiver.requests) == 2
    assert receiver.requests[0].headers["webhook-id"] == receiver.requests[1].headers["webhook-id"]
    assert db.query(AuditLogEntry).filter_by(action_type="WEBHOOK_DELIVERY_REPLAYED").count() == 1


def test_test_ping_is_delivered(api: Api, db: Session) -> None:
    ep = _create(api).json()
    assert api.post(f"/api/v1/org/webhooks/{ep['id']}/test").status_code == 202
    receiver = Receiver()
    webhooks.dispatch_due(db, client=receiver.client())
    assert json.loads(receiver.requests[0].content)["type"] == "ping"


def test_webhooks_are_isolated_between_organisations(api: Api, api_b: Api, db: Session) -> None:
    ep = _create(api).json()
    api.full_run("a.xlsx", xlsx_bytes(simple_rows()))
    [d] = api.get(f"/api/v1/org/webhooks/{ep['id']}/deliveries").json()
    assert api_b.get("/api/v1/org/webhooks").json() == []
    assert api_b.get(f"/api/v1/org/webhooks/{ep['id']}/deliveries").status_code == 404
    assert api_b.post(f"/api/v1/org/webhooks/deliveries/{d['id']}/replay").status_code == 404
    assert api_b.delete(f"/api/v1/org/webhooks/{ep['id']}").status_code == 404


def test_failed_report_emits_report_failed(api: Api, db: Session) -> None:
    _create(api, ["report.failed"])
    api.upload("empty.xlsx", xlsx_bytes([["nothing", "useful"]]))
    run_jobs()
    db.expire_all()
    set_tenant(db, api.me["tenant"]["id"])
    [d] = db.query(WebhookDelivery).all()
    assert d.event_type == "report.failed" and d.payload["data"]["error_code"] == "no_data"
