"""P2 edge cases: the failure branches of the channel code, each a real
behaviour a customer or operator would hit.

- webhooks: missing signature headers never verify; an unresolvable host is
  refused; a connection error or an endpoint that turns unsafe is recorded
  as a failed attempt (retried), and a removed endpoint ends the delivery;
- e-mail: malformed attachments are skipped, extra recipients (ToFull) are
  honoured, a MIME message without explicit destinations uses its To header,
  and an attachment over the upload limit is rejected with a reason;
- ECB feed: malformed cubes (no date, bad code, non-numbers, non-positive
  rates) are ignored and a changed fixing is updated in place;
- SNS: unknown message types, bad signatures and non-RSA keys are refused;
  the signing certificate is fetched over https;
- SFTP: private-key sign-in reads PEM keys and refuses unreadable ones;
- AI: AI_PROVIDER selects the configured EU provider (or none).
"""

from __future__ import annotations

import base64
import io
import socket
from datetime import date
from decimal import Decimal
from email.message import EmailMessage
from typing import Any

import httpx
import paramiko
import pytest
from app import config
from app.ai import providers
from app.database import set_tenant
from app.models.channels import FxRate, WebhookDelivery, WebhookEndpoint
from app.security import sns
from app.services import fx_service, inbound_email, sftp_service, webhooks
from app.settings import get_settings
from conftest import Api
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy.orm import Session

PUBLIC = [(2, 1, 6, "", ("93.184.216.34", 443))]


# ------------------------------------------------------------------ webhooks


def test_missing_or_malformed_signature_headers_never_verify() -> None:
    secret = webhooks.new_secret()
    assert not webhooks.verify_signature(secret, {}, b"{}")
    assert not webhooks.verify_signature(secret, {"webhook-id": "m", "webhook-timestamp": "soon"}, b"{}")


def test_unresolvable_host_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    def nxdomain(*a: Any, **k: Any) -> Any:
        raise socket.gaierror("no such host")

    monkeypatch.setattr("app.services.webhooks.socket.getaddrinfo", nxdomain)
    with pytest.raises(webhooks.WebhookTargetError, match="does not resolve"):
        webhooks.check_target("https://nowhere.example/x")


def _queued_delivery(api: Api, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr("app.services.webhooks.socket.getaddrinfo", lambda *a, **k: PUBLIC)
    ep = api.post("/api/v1/org/webhooks", json={"url": "https://hooks.example/x", "events": ["report.completed"]})
    return str(api.post(f"/api/v1/org/webhooks/{ep.json()['id']}/test").json()["id"])


def _delivery(db: Session, api: Api, delivery_id: str) -> WebhookDelivery:
    db.expire_all()
    set_tenant(db, api.me["tenant"]["id"])
    d = db.get(WebhookDelivery, delivery_id)
    assert d is not None
    return d


def test_connection_errors_are_failed_attempts(api: Api, db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    did = _queued_delivery(api, monkeypatch)

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    webhooks.dispatch_due(db, client=httpx.Client(transport=httpx.MockTransport(refuse)))
    d = _delivery(db, api, did)
    assert d.status == "FAILED" and d.last_status_code is None and "ConnectError" in (d.last_error or "")


def test_endpoint_that_turns_unsafe_is_not_called(api: Api, db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    did = _queued_delivery(api, monkeypatch)
    monkeypatch.setattr("app.services.webhooks.socket.getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("10.1.2.3", 443))])
    called: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        called.append(request)
        return httpx.Response(200)

    webhooks.dispatch_due(db, client=httpx.Client(transport=httpx.MockTransport(record)))
    assert called == [], "DNS rebinding to a private address is caught before sending"
    d = _delivery(db, api, did)
    assert d.status == "FAILED" and "public internet" in (d.last_error or "")


def test_removed_or_disabled_endpoint_ends_the_delivery(api: Api, db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    did = _queued_delivery(api, monkeypatch)
    set_tenant(db, api.me["tenant"]["id"])
    for ep in db.query(WebhookEndpoint).all():
        ep.enabled = False
    db.commit()
    webhooks.dispatch_due(db, client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200))))
    d = _delivery(db, api, did)
    assert d.status == "EXHAUSTED" and "disabled" in (d.last_error or "")


# ------------------------------------------------------------------ e-mail


def test_postmark_parsing_skips_bad_attachments_and_reads_all_recipients() -> None:
    msg = inbound_email.from_postmark(
        {
            "MessageID": "m",
            "From": "a@b.example",
            "To": "x@in.example",
            "ToFull": [{"Email": "y@in.example"}, "junk"],
            "Attachments": [
                {"Name": "bad.csv", "Content": "!!not base64!!"},
                {"Content": base64.b64encode(b"a,b").decode()},
            ],
        }
    )
    assert "y@in.example" in msg.recipients
    assert [a.name for a in msg.attachments] == ["attachment"], "undecodable attachment skipped; unnamed one kept"


def test_mime_without_destinations_uses_its_to_header() -> None:
    mime = EmailMessage()
    mime["From"], mime["To"] = "a@b.example", "tok@in.example"
    mime.set_content("x")
    msg = inbound_email.from_mime(mime.as_bytes(), [], "")
    assert msg.recipients == ["tok@in.example"] and msg.attachments == []


def test_oversized_attachment_is_rejected_with_a_reason(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "INBOUND_EMAIL_DOMAIN", "in.example")
    token = api.post("/api/v1/org/inbound/rotate")
    assert token.status_code in (200, 503)
    address = str(token.json().get("address") or "")
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 10)
    msg = inbound_email.InboundMessage(
        "m1", "a@b.example", [address], [inbound_email.Attachment("big.xlsx", b"x" * 11)]
    )
    from app.database import get_session_factory

    db = get_session_factory()()
    try:
        result = inbound_email.ingest(db, msg, "postmark")
    finally:
        db.close()
    assert result.accepted == [] and result.rejected == [
        {"file_name": "big.xlsx", "reason": "larger than the upload limit"}
    ]


# ------------------------------------------------------------------ ECB feed

ODD_FEED = b"""<?xml version="1.0"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01" xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
<Cube>
  <Cube><Cube currency="USD" rate="1.1"/></Cube>
  <Cube time="2026-09-25">
    <Cube currency="US" rate="1.1"/><Cube currency="GBP" rate="abc"/><Cube currency="JPY" rate="0"/><Cube rate="1"/>
    <Cube currency="USD" rate="1.1700"/>
  </Cube>
</Cube>
</gesmes:Envelope>"""


def test_malformed_cubes_are_ignored_and_changed_fixings_update(db: Session) -> None:
    assert fx_service.parse_feed(ODD_FEED) == {date(2026, 9, 25): {"USD": Decimal("1.1700")}}
    fx_service.refresh(db, fetch=lambda url: ODD_FEED)
    revised = ODD_FEED.replace(b'currency="USD" rate="1.1700"', b'currency="USD" rate="1.1800"')
    assert fx_service.refresh(db, fetch=lambda url: revised) == 1
    db.expire_all()
    assert db.get(FxRate, (date(2026, 9, 25), "USD")).rate == Decimal("1.1800")  # type: ignore[union-attr]


def test_feed_is_fetched_over_http(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def fake_get(url: str, **kw: Any) -> httpx.Response:
        seen.append(url)
        return httpx.Response(200, content=b"<x/>", request=httpx.Request("GET", url))

    monkeypatch.setattr("app.services.fx_service.httpx.get", fake_get)
    assert fx_service._fetch("https://www.ecb.europa.eu/x.xml") == b"<x/>" and seen


# ------------------------------------------------------------------ SNS


def test_sns_unknown_types_bad_signatures_and_foreign_keys_are_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(sns.SnsVerificationError):
        sns.canonical_string({"Type": "Mystery"})
    base = {
        "Type": "Notification", "TopicArn": "arn:t", "SigningCertURL": "https://sns.eu-west-1.amazonaws.com/c.pem",
        "SignatureVersion": "2", "Message": "m", "MessageId": "1", "Timestamp": "t",
    }  # fmt: skip
    with pytest.raises(sns.SnsVerificationError, match="unreadable"):
        sns.verify({**base, "Signature": "***"}, ("arn:t",), fetch_cert=lambda u: b"")
    key = ec.generate_private_key(ec.SECP256R1())
    with pytest.raises(sns.SnsVerificationError, match="key type"):
        sns.verify(
            {**base, "Signature": base64.b64encode(b"x").decode()}, ("arn:t",), fetch_cert=lambda u: _ec_cert(key)
        )


def _ec_cert(key: ec.EllipticCurvePrivateKey) -> bytes:
    import datetime as dt

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.x509.oid import NameOID

    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "x")])
    now = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(2)
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM)


def test_signing_certificate_is_fetched_over_https(monkeypatch: pytest.MonkeyPatch) -> None:
    sns._fetch_cert.cache_clear()
    monkeypatch.setattr(
        "app.security.sns.httpx.get",
        lambda url, **kw: httpx.Response(200, content=b"PEM", request=httpx.Request("GET", url)),
    )
    assert sns._fetch_cert("https://sns.eu-west-1.amazonaws.com/c.pem") == b"PEM"
    sns._fetch_cert.cache_clear()


# ------------------------------------------------------------------ SFTP keys


def test_private_keys_are_read_or_refused() -> None:
    key = paramiko.ECDSAKey.generate()
    buf = io.StringIO()
    key.write_private_key(buf)
    assert sftp_service._load_key(buf.getvalue()).get_name().startswith("ecdsa")
    with pytest.raises(sftp_service.SftpError, match="could not be read"):
        sftp_service._load_key("-----BEGIN NOTHING-----\nAAAA\n-----END NOTHING-----\n")


def test_key_based_destination_decrypts_the_key(api: Api) -> None:
    key = paramiko.ECDSAKey.generate()
    buf = io.StringIO()
    key.write_private_key(buf)
    body = {
        "host": "sftp.partner.example", "username": "u", "private_key": buf.getvalue(),
        "host_key_fingerprint": "SHA256:" + "A" * 43, "remote_dir": "/",
    }  # fmt: skip
    r = api.client.put("/api/v1/org/sftp", json=body, headers={"X-CSRF-Token": api.csrf})
    assert r.status_code == 200 and r.json()["auth"] == "private_key"
    from app.database import get_session_factory
    from app.models.channels import SftpDestination

    db = get_session_factory()()
    try:
        set_tenant(db, api.me["tenant"]["id"])
        dest = db.query(SftpDestination).one()
        creds = sftp_service.credentials(dest)
        assert creds.private_key == buf.getvalue() and creds.password is None
        assert "BEGIN" not in (dest.private_key_enc or ""), "stored encrypted"
    finally:
        db.close()


# ------------------------------------------------------------------ AI provider selection


@pytest.mark.parametrize(
    ("env", "name"),
    [
        ({"AI_PROVIDER": "azure_openai", "AZURE_OPENAI_REGION": "uksouth", "AZURE_OPENAI_ENDPOINT": "https://x",
          "AZURE_OPENAI_DEPLOYMENT": "d"}, "azure_openai"),
        ({"AI_PROVIDER": "bedrock", "BEDROCK_REGION": "eu-west-3", "BEDROCK_MODEL_ID": "m"}, "bedrock"),
        ({"AI_PROVIDER": "fake"}, "fake"),
        ({"AI_PROVIDER": "none"}, None),
    ],
)  # fmt: skip
def test_ai_provider_follows_settings(monkeypatch: pytest.MonkeyPatch, env: dict[str, str], name: str | None) -> None:
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    try:
        p = providers.get_provider()
        assert (p.name if p else None) == name
        if p is not None and name != "fake":
            assert p.region in ("uksouth", "eu-west-3")
    finally:
        get_settings.cache_clear()
