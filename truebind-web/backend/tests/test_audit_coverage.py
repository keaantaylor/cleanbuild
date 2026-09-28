"""P1.9 -- every state change writes a hash-chained audit event, and
tampering with the stored trail is detected.

Acceptance:
- a scenario calls every state-changing API operation (POST / PATCH /
  DELETE in the OpenAPI document) successfully and each call adds at least
  one entry to the organisation's audit trail; an operation added later
  without an audited scenario step fails this test;
- after all of it, GET /audit/verify reports the chain intact;
- editing any stored field of an entry, deleting an entry or reordering
  entries is reported as broken at the first affected entry. On PostgreSQL
  the append-only trigger must be removed first (only the table owner can),
  proving the database refuses the edit before the chain has to catch it.
"""

from __future__ import annotations

import base64
import datetime as dt
import time
from collections.abc import Callable
from typing import Any

import pyotp
import pytest
from app.database import get_session_factory, set_tenant
from app.main import app
from app.models.audit import AuditLogEntry
from app.services import audit_service
from conftest import IS_PG, PASSWORD, Api, run_jobs, simple_rows, xlsx_bytes
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

SSO = {
    "issuer": "https://idp.example/tenant-a",
    "client_id": "truebind-a",
    "client_secret": "super-secret-client-value",
    "domains": ["corp-a.example"],
    "jit_provisioning": False,
    "default_role": "VIEWER",
    "enabled": True,
}


def _self_signed(key: rsa.RSAPrivateKey) -> bytes:
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "sns.amazonaws.com")])
    now = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM)


def _mutating_operations() -> set[tuple[str, str]]:
    ops = set()
    for path, methods in app.openapi()["paths"].items():
        if path.startswith("/__"):
            continue
        for method in methods:
            if method in ("post", "patch", "put", "delete"):
                ops.add((method.upper(), path))
    return ops


class Trail:
    def __init__(self, tenant_id: str) -> None:
        self.tenant_id = tenant_id
        self.covered: set[tuple[str, str]] = set()

    def count(self) -> int:
        db = get_session_factory()()
        try:
            set_tenant(db, self.tenant_id)
            return int(db.query(AuditLogEntry).count())
        finally:
            db.close()

    def step(self, method: str, template: str, call: Callable[[], Any]) -> Any:
        before = self.count()
        r = call()
        assert r.status_code < 400, (method, template, r.status_code, r.text)
        assert self.count() > before, f"{method} {template} changed state without an audit entry"
        self.covered.add((method, template))
        return r


def test_every_state_change_is_audited_and_the_chain_holds(monkeypatch: pytest.MonkeyPatch) -> None:
    before_signup = time.monotonic()
    owner = Api()
    tid = owner.me["tenant"]["id"]
    trail = Trail(tid)
    assert trail.count() >= 1, "sign-up is audited"
    trail.covered.add(("POST", "/api/v1/auth/signup"))
    assert time.monotonic() >= before_signup

    # --- session
    c = TestClient(app)
    login = trail.step("POST", "/api/v1/auth/login", lambda: c.post(
        "/api/v1/auth/login", json={"email": "owner@a.example", "password": PASSWORD}))  # fmt: skip
    csrf = {"X-CSRF-Token": login.json()["csrf_token"]}
    trail.step("POST", "/api/v1/auth/logout", lambda: c.post("/api/v1/auth/logout", headers=csrf))

    # --- reports, mapping, processing, findings
    dup_rows = simple_rows(3) + [["DUP-1", "Same Insured", "2024-01-15", "Open", "GBP", 1, 1, 2]] * 2
    dup_rows.append(["ARI-1", "Arith Ltd", "2024-01-15", "Open", "GBP", 100, 50, 999])  # does not reconcile
    up = trail.step("POST", "/api/v1/reports/upload", lambda: owner.upload("a.xlsx", xlsx_bytes(dup_rows)))
    rid = up.json()["id"]
    run_jobs()
    for s in owner.get(f"/api/v1/reports/{rid}/sheets").json():
        m = owner.get(f"/api/v1/reports/{rid}/sheets/{s['id']}/mapping").json()
        choices = {f["field_code"]: f["source_column"] for f in m["fields"]}
        url = f"/api/v1/reports/{rid}/sheets/{s['id']}/mapping"

        def confirm(url: str = url, ch: dict[str, Any] = choices) -> Any:
            return owner.post(url, json={"mappings": ch})

        trail.step("POST", "/api/v1/reports/{report_id}/sheets/{sheet_id}/mapping", confirm)
    trail.step("POST", "/api/v1/reports/{report_id}/process", lambda: owner.post(f"/api/v1/reports/{rid}/process"))
    run_jobs()
    pair = owner.get(f"/api/v1/reports/{rid}/duplicates").json()["items"][0]
    trail.step("PATCH", "/api/v1/reports/{report_id}/duplicates/{validation_result_id}/review", lambda: owner.patch(
        f"/api/v1/reports/{rid}/duplicates/{pair['validation_result_id']}/review",
        json={"review_status": "confirmed_duplicate"}))  # fmt: skip
    vr = owner.get(f"/api/v1/reports/{rid}/exceptions").json()["items"][0]["validation_result_id"]
    trail.step("PATCH", "/api/v1/reports/{report_id}/exceptions/{validation_result_id}", lambda: owner.patch(
        f"/api/v1/reports/{rid}/exceptions/{vr}", json={"review_status": "in_review", "assignee": "Sam"}))  # fmt: skip
    trail.step("POST", "/api/v1/reports/{report_id}/exceptions/summary",
               lambda: owner.post(f"/api/v1/reports/{rid}/exceptions/summary"))  # fmt: skip
    ob = trail.step("POST", "/api/v1/reports/{report_id}/obligations", lambda: owner.post(
        f"/api/v1/reports/{rid}/obligations", json={"owner": "ops", "note": "chase"})).json()  # fmt: skip
    trail.step("PATCH", "/api/v1/obligations/{obligation_id}", lambda: owner.patch(
        f"/api/v1/obligations/{ob['id']}", json={"status": "RESOLVED"}))  # fmt: skip
    alert = owner.get("/api/v1/alerts").json()["items"][0]["id"]
    trail.step("POST", "/api/v1/alerts/{alert_id}/acknowledge",
               lambda: owner.post(f"/api/v1/alerts/{alert}/acknowledge"))  # fmt: skip
    trail.step("POST", "/api/v1/templates", lambda: owner.post(
        "/api/v1/templates", json={"name": "T", "field_mappings": {"Ref": "CR0104M"}}))  # fmt: skip
    trail.step("POST", "/api/v1/reports/{report_id}/deliveries", lambda: owner.post(
        f"/api/v1/reports/{rid}/deliveries",
        json={"kind": "claims_csv", "channel": "email", "recipient": "ops@a.example"}))  # fmt: skip

    # cancel needs a queued job, retry a failed one; delete ends a report's life
    rid2 = owner.upload("b.xlsx", xlsx_bytes(simple_rows())).json()["id"]
    trail.step("POST", "/api/v1/reports/{report_id}/cancel", lambda: owner.post(f"/api/v1/reports/{rid2}/cancel"))
    rid3 = owner.upload("empty.xlsx", xlsx_bytes([["nothing", "useful"]])).json()["id"]
    run_jobs()  # no header row with data below it: the ingest fails (not retryable)
    assert owner.get(f"/api/v1/reports/{rid3}").json()["status"] == "FAILED"
    trail.step("POST", "/api/v1/reports/{report_id}/retry", lambda: owner.post(f"/api/v1/reports/{rid3}/retry"))
    run_jobs()
    trail.step("DELETE", "/api/v1/reports/{report_id}", lambda: owner.delete(f"/api/v1/reports/{rid2}"))

    # --- organisation, members, invitations
    trail.step("PATCH", "/api/v1/org", lambda: owner.patch("/api/v1/org", json={"name": "Org A renamed"}))
    inv = trail.step("POST", "/api/v1/org/invitations", lambda: owner.post(
        "/api/v1/org/invitations", json={"email": "m@a.example", "role": "ANALYST"})).json()  # fmt: skip
    member = TestClient(app)
    trail.step("POST", "/api/v1/auth/invitations/accept", lambda: member.post(
        "/api/v1/auth/invitations/accept",
        json={"token": inv["accept_token"], "display_name": "M", "password": PASSWORD}))  # fmt: skip
    inv2 = owner.post("/api/v1/org/invitations", json={"email": "x@a.example", "role": "VIEWER"}).json()
    trail.step("DELETE", "/api/v1/org/invitations/{invitation_id}",
               lambda: owner.delete(f"/api/v1/org/invitations/{inv2['id']}"))  # fmt: skip
    mid = next(m["membership_id"] for m in owner.get("/api/v1/org/members").json() if m["email"] == "m@a.example")
    trail.step("PATCH", "/api/v1/org/members/{membership_id}",
               lambda: owner.patch(f"/api/v1/org/members/{mid}", json={"role": "VIEWER"}))  # fmt: skip
    trail.step("DELETE", "/api/v1/org/members/{membership_id}", lambda: owner.delete(f"/api/v1/org/members/{mid}"))

    # --- single sign-on configuration
    trail.step("PATCH", "/api/v1/org/sso", lambda: owner.patch("/api/v1/org/sso", json=SSO))
    trail.step("DELETE", "/api/v1/org/sso", lambda: owner.delete("/api/v1/org/sso"))

    # --- two-step verification: setup, enable, second sign-in step, disable
    setup = trail.step("POST", "/api/v1/auth/2fa/setup", lambda: owner.post("/api/v1/auth/2fa/setup")).json()
    totp = pyotp.TOTP(setup["secret"])
    enabled = trail.step("POST", "/api/v1/auth/2fa/enable",
                         lambda: owner.post("/api/v1/auth/2fa/enable", json={"code": totp.now()})).json()  # fmt: skip
    c2 = TestClient(app)
    challenge = c2.post("/api/v1/auth/login", json={"email": "owner@a.example", "password": PASSWORD}).json()
    signed_in = trail.step("POST", "/api/v1/auth/2fa/verify", lambda: c2.post(
        "/api/v1/auth/2fa/verify",
        json={"mfa_token": challenge["mfa_token"], "recovery_code": enabled["recovery_codes"][0]}))  # fmt: skip
    csrf2 = {"X-CSRF-Token": signed_in.json()["csrf_token"]}
    trail.step("POST", "/api/v1/auth/2fa/disable", lambda: c2.post(
        "/api/v1/auth/2fa/disable", headers=csrf2, json={"code": totp.at(int(time.time()) + 30)}))  # fmt: skip

    # --- inbound e-mail (P2): address rotation, Postmark and SES intake
    from app import config
    from app.security import sns
    from test_inbound_email import CERT_URL, DOMAIN, SECRET, TOPIC, _postmark, _ses_message

    monkeypatch.setattr(config, "INBOUND_EMAIL_DOMAIN", DOMAIN)
    monkeypatch.setattr(config, "INBOUND_WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr(config, "SES_SNS_TOPIC_ARNS", (TOPIC,))
    address = trail.step("POST", "/api/v1/org/inbound/rotate", lambda: owner.post("/api/v1/org/inbound/rotate")).json()[
        "address"
    ]
    basic = {"Authorization": "Basic " + base64.b64encode(f"pm:{SECRET}".encode()).decode()}
    trail.step("POST", "/api/v1/inbound/email/postmark", lambda: TestClient(app).post(
        "/api/v1/inbound/email/postmark", headers=basic,
        json=_postmark(address, [("m.xlsx", xlsx_bytes(simple_rows()))])))  # fmt: skip
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = _self_signed(key)
    monkeypatch.setattr(sns, "_fetch_cert", lambda url: pem)
    assert CERT_URL
    trail.step("POST", "/api/v1/inbound/email/ses",
               lambda: TestClient(app).post("/api/v1/inbound/email/ses", json=_ses_message(key, address)))  # fmt: skip

    # --- outbound webhooks (P2.3)
    public = [(2, 1, 6, "", ("93.184.216.34", 443))]
    monkeypatch.setattr("app.services.webhooks.socket.getaddrinfo", lambda *a, **k: public)
    hook_in = {"url": "https://hooks.partner.example/x", "events": ["report.completed"]}
    ep = trail.step("POST", "/api/v1/org/webhooks", lambda: owner.post("/api/v1/org/webhooks", json=hook_in)).json()
    d = trail.step(
        "POST", "/api/v1/org/webhooks/{endpoint_id}/test", lambda: owner.post(f"/api/v1/org/webhooks/{ep['id']}/test")
    ).json()
    trail.step(
        "POST",
        "/api/v1/org/webhooks/deliveries/{delivery_id}/replay",
        lambda: owner.post(f"/api/v1/org/webhooks/deliveries/{d['id']}/replay"),
    )
    trail.step("DELETE", "/api/v1/org/webhooks/{endpoint_id}", lambda: owner.delete(f"/api/v1/org/webhooks/{ep['id']}"))

    # --- SFTP destination (P2.4); the test fails to connect (nothing listening) but is still audited
    sftp_in = {
        "host": "127.0.0.1",
        "port": 1,
        "username": "u",
        "password": "p-value",
        "host_key_fingerprint": "SHA256:" + "A" * 43,
        "remote_dir": "/",
    }
    csrf_a = {"X-CSRF-Token": owner.csrf}
    trail.step("PUT", "/api/v1/org/sftp", lambda: owner.client.put("/api/v1/org/sftp", json=sftp_in, headers=csrf_a))
    trail.step("POST", "/api/v1/org/sftp/test", lambda: owner.post("/api/v1/org/sftp/test"))
    trail.step("DELETE", "/api/v1/org/sftp", lambda: owner.delete("/api/v1/org/sftp"))

    missing = _mutating_operations() - trail.covered
    assert not missing, f"state-changing operations without an audited scenario step: {sorted(missing)}"
    verdict = owner.get("/api/v1/audit/verify").json()
    assert verdict["intact"] is True, verdict


# ------------------------------------------------------------------ tampering


def _seed(api: Api) -> str:
    api.full_run("a.xlsx", xlsx_bytes(simple_rows()))
    return str(api.me["tenant"]["id"])


def _owner_session(tenant_id: str) -> Session:
    db: Session = get_session_factory()()
    set_tenant(db, tenant_id)
    if IS_PG:  # the append-only trigger is the first line of defence; only the table owner may lift it
        db.execute(text("ALTER TABLE audit_log DISABLE TRIGGER USER"))
    return db


def _close(db: Session) -> None:
    if IS_PG:
        db.execute(text("ALTER TABLE audit_log ENABLE TRIGGER USER"))
    db.commit()
    db.close()


@pytest.mark.skipif(not IS_PG, reason="the append-only trigger exists on PostgreSQL only")
def test_database_refuses_to_edit_or_delete_audit_rows(api: Api) -> None:
    tid = _seed(api)
    for stmt in ("UPDATE audit_log SET actor = 'mallory' WHERE seq = 2", "DELETE FROM audit_log WHERE seq = 2"):
        db = get_session_factory()()
        set_tenant(db, tid)
        with pytest.raises(DBAPIError):
            db.execute(text(stmt))
            db.flush()
        db.rollback()
        db.close()


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("actor", "'mallory'"),
        ("action_type", "'REPORT_DELETED'"),
        ("after_value", "NULL"),
        ("created_at", "created_at"),  # replaced below with a shifted timestamp
        ("entry_hash", "'" + "f" * 64 + "'"),
    ],
)
def test_editing_any_field_breaks_the_chain_at_that_entry(api: Api, column: str, value: str) -> None:
    tid = _seed(api)
    if column == "created_at":
        value = "created_at + INTERVAL '1 second'" if IS_PG else "datetime(created_at, '+1 second')"
    db = _owner_session(tid)
    try:
        db.execute(text(f"UPDATE audit_log SET {column} = {value} WHERE tenant_id = :t AND seq = 3"), {"t": tid})  # noqa: S608 -- test-only constants
    finally:
        _close(db)
    verdict = api.get("/api/v1/audit/verify").json()
    assert verdict["intact"] is False
    assert verdict["first_bad_seq"] == 3, verdict  # every stored field, the hash included, is recomputed


def test_deleting_an_entry_breaks_the_chain(api: Api) -> None:
    tid = _seed(api)
    db = _owner_session(tid)
    try:
        db.execute(text("DELETE FROM audit_log WHERE tenant_id = :t AND seq = 2"), {"t": tid})
    finally:
        _close(db)
    verdict = api.get("/api/v1/audit/verify").json()
    assert verdict["intact"] is False and verdict["first_bad_seq"] == 3


def test_verify_detects_tampering_directly(api: Api) -> None:
    tid = _seed(api)
    db = get_session_factory()()
    set_tenant(db, tid)
    assert audit_service.verify_chain(db, tid) == (True, None)
    db.close()
    db = _owner_session(tid)
    try:
        db.execute(text("UPDATE audit_log SET seq = seq + 1000 WHERE tenant_id = :t AND seq = 1"), {"t": tid})
    finally:
        _close(db)
    db = get_session_factory()()
    set_tenant(db, tid)
    ok, bad = audit_service.verify_chain(db, tid)
    db.close()
    assert ok is False and bad == 2
