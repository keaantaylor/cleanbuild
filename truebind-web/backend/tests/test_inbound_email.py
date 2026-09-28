"""P2.1 -- e-mail intake (Postmark and Amazon SES via SNS).

Acceptance:
- each organisation gets a private inbound address (created / rotated by
  org:manage, audited); a rotated address stops working;
- a Postmark inbound webhook with valid Basic credentials turns every
  attachment into a report through the same file gate as uploads
  (source_channel "email", sender recorded, INGEST queued, audited);
- provider retries of the same message create nothing new;
- bad or missing credentials are 401; an unconfigured server is 503;
- mail to an unknown address is acknowledged and dropped (no report, no
  information about organisations returned);
- a rejected attachment is audited with its channel and reported back;
- mail lands only in the addressed organisation;
- SES: only SNS messages signed by a trusted AWS certificate URL, on an
  allowed topic, with an intact signature (v1 SHA1 or v2 SHA256) are
  processed; anything else is 401.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
from email.message import EmailMessage
from typing import Any

import pytest
from app import config
from app.database import set_tenant
from app.models.audit import AuditLogEntry
from app.models.reports import Report
from app.security import sns
from conftest import Api, run_jobs, simple_rows, xlsx_bytes
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

DOMAIN = "in.truebind.test"
SECRET = "inbound-test-secret-value"
TOPIC = "arn:aws:sns:eu-west-1:123456789012:truebind-inbound"
CERT_URL = "https://sns.eu-west-1.amazonaws.com/SimpleNotificationService-test.pem"


@pytest.fixture(autouse=True)
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "INBOUND_EMAIL_DOMAIN", DOMAIN)
    monkeypatch.setattr(config, "INBOUND_WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr(config, "SES_SNS_TOPIC_ARNS", (TOPIC,))


def _address(api: Api) -> str:
    r = api.post("/api/v1/org/inbound/rotate")
    assert r.status_code == 200, r.text
    address = r.json()["address"]
    assert isinstance(address, str) and address.endswith("@" + DOMAIN)
    return address


def _postmark(to: str, attachments: list[tuple[str, bytes]], message_id: str = "pm-1") -> dict[str, Any]:
    return {
        "MessageID": message_id,
        "From": "Sender Ops <ops@coverholder.example>",
        "To": to,
        "OriginalRecipient": to,
        "Subject": "March bordereau",
        "Attachments": [
            {"Name": n, "Content": base64.b64encode(c).decode(), "ContentType": "application/octet-stream"}
            for n, c in attachments
        ],
    }


def _post(payload: dict[str, Any], password: str = SECRET) -> Any:
    auth = base64.b64encode(f"postmark:{password}".encode()).decode()
    return TestClient(__import__("app.main", fromlist=["app"]).app).post(
        "/api/v1/inbound/email/postmark", json=payload, headers={"Authorization": f"Basic {auth}"}
    )


def _reports(db: Session, tenant_id: str) -> list[Report]:
    db.expire_all()
    set_tenant(db, tenant_id)
    return db.query(Report).filter(Report.tenant_id == tenant_id).all()


def test_postmark_attachment_becomes_a_report(api: Api, db: Session) -> None:
    address = _address(api)
    r = _post(_postmark(address, [("march.xlsx", xlsx_bytes(simple_rows(4)))]))
    assert r.status_code == 200 and r.json() == {"accepted": 1, "rejected": 0, "duplicates": 0}
    [report] = _reports(db, api.me["tenant"]["id"])
    assert report.source_channel == "email" and report.sender == "ops@coverholder.example"
    run_jobs()
    assert api.get(f"/api/v1/reports/{report.id}").json()["status"] == "WAITING_FOR_REVIEW"
    uploaded = db.query(AuditLogEntry).filter_by(action_type="REPORT_UPLOADED").one()
    assert uploaded.after_value is not None and uploaded.after_value["channel"] == "email"
    assert uploaded.actor == "email:ops@coverholder.example"


def test_provider_retries_create_nothing_new(api: Api, db: Session) -> None:
    address = _address(api)
    payload = _postmark(address, [("a.xlsx", xlsx_bytes(simple_rows(3))), ("b.csv", b"Claim Reference,Paid\nX,1\n")])
    assert _post(payload).json()["accepted"] == 2
    again = _post(payload)
    assert again.json() == {"accepted": 0, "rejected": 0, "duplicates": 2}
    assert len(_reports(db, api.me["tenant"]["id"])) == 2


def test_credentials_and_configuration(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    address = _address(api)
    payload = _postmark(address, [("a.xlsx", xlsx_bytes(simple_rows()))])
    assert _post(payload, password="wrong").status_code == 401
    client = TestClient(__import__("app.main", fromlist=["app"]).app)
    assert client.post("/api/v1/inbound/email/postmark", json=payload).status_code == 401
    monkeypatch.setattr(config, "INBOUND_WEBHOOK_SECRET", "")
    assert _post(payload).status_code == 503


def test_unknown_or_rotated_address_is_dropped(api: Api, db: Session) -> None:
    old = _address(api)
    new = _address(api)
    assert old != new
    for to in (old, f"nobody@{DOMAIN}", "someone@other.example"):
        r = _post(_postmark(to, [("a.xlsx", xlsx_bytes(simple_rows()))], message_id=to))
        assert r.status_code == 200 and r.json()["accepted"] == 0
    assert _reports(db, api.me["tenant"]["id"]) == []
    rotations = db.query(AuditLogEntry).filter(AuditLogEntry.action_type.like("INBOUND_ADDRESS_%")).count()
    assert rotations == 2


def test_rejected_attachment_is_audited_and_reported(api: Api, db: Session) -> None:
    address = _address(api)
    r = _post(_postmark(address, [("payload.exe", b"MZ\x90\x00"), ("ok.xlsx", xlsx_bytes(simple_rows()))]))
    assert r.json() == {"accepted": 1, "rejected": 1, "duplicates": 0}
    rejected = db.query(AuditLogEntry).filter_by(action_type="UPLOAD_REJECTED").one()
    assert rejected.after_value is not None and rejected.after_value["channel"] == "email"


def test_mail_lands_only_in_the_addressed_organisation(api: Api, api_b: Api, db: Session) -> None:
    _address(api)
    address_b = _address(api_b)
    assert _post(_postmark(address_b, [("b.xlsx", xlsx_bytes(simple_rows()))])).json()["accepted"] == 1
    assert _reports(db, api.me["tenant"]["id"]) == []
    assert len(_reports(db, api_b.me["tenant"]["id"])) == 1


def test_inbound_settings_need_the_right_role(api: Api) -> None:
    token = api.post("/api/v1/org/invitations", json={"email": "v@a.example", "role": "VIEWER"}).json()["accept_token"]
    viewer = TestClient(__import__("app.main", fromlist=["app"]).app)
    me = viewer.post(
        "/api/v1/auth/invitations/accept",
        json={"token": token, "display_name": "V", "password": "correct horse battery staple"},
    ).json()
    assert viewer.get("/api/v1/org/inbound").status_code == 200
    r = viewer.post("/api/v1/org/inbound/rotate", headers={"X-CSRF-Token": me["csrf_token"]})
    assert r.status_code == 403


# ------------------------------------------------------------------ SES via SNS


@pytest.fixture(scope="module")
def signing() -> tuple[rsa.RSAPrivateKey, bytes]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
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
    return key, cert.public_bytes(serialization.Encoding.PEM)


def _ses_message(key: rsa.RSAPrivateKey, to: str, version: str = "2", **override: str) -> dict[str, str]:
    mime = EmailMessage()
    mime["From"] = "ops@coverholder.example"
    mime["To"] = to
    mime["Subject"] = "bordereau"
    mime.set_content("attached")
    mime.add_attachment(xlsx_bytes(simple_rows(3)), maintype="application", subtype="octet-stream", filename="s.xlsx")
    notification = {
        "notificationType": "Received",
        "mail": {"messageId": "ses-1", "destination": [to]},
        "content": base64.b64encode(mime.as_bytes()).decode(),
    }
    msg = {
        "Type": "Notification",
        "MessageId": "sns-1",
        "TopicArn": TOPIC,
        "Message": json.dumps(notification),
        "Timestamp": "2026-09-28T10:00:00.000Z",
        "SignatureVersion": version,
        "SigningCertURL": CERT_URL,
    }
    msg.update(override)
    algorithm: hashes.HashAlgorithm = hashes.SHA1() if version == "1" else hashes.SHA256()  # noqa: S303
    signature = key.sign(sns.canonical_string(msg), padding.PKCS1v15(), algorithm)
    msg["Signature"] = base64.b64encode(signature).decode()
    return msg


def _post_ses(msg: dict[str, str]) -> Any:
    return TestClient(__import__("app.main", fromlist=["app"]).app).post("/api/v1/inbound/email/ses", json=msg)


@pytest.mark.parametrize("version", ["1", "2"])
def test_ses_signed_notification_is_ingested(
    api: Api, db: Session, monkeypatch: pytest.MonkeyPatch, signing: tuple[rsa.RSAPrivateKey, bytes], version: str
) -> None:
    key, pem = signing
    monkeypatch.setattr(sns, "_fetch_cert", lambda url: pem)
    r = _post_ses(_ses_message(key, _address(api), version=version))
    assert r.status_code == 200 and r.json()["accepted"] == 1, r.text
    [report] = _reports(db, api.me["tenant"]["id"])
    assert report.source_channel == "email" and report.file_name == "s.xlsx"


def test_ses_forgeries_are_refused(
    api: Api, db: Session, monkeypatch: pytest.MonkeyPatch, signing: tuple[rsa.RSAPrivateKey, bytes]
) -> None:
    key, pem = signing
    monkeypatch.setattr(sns, "_fetch_cert", lambda url: pem)
    address = _address(api)
    tampered = _ses_message(key, address)
    tampered["Message"] = tampered["Message"].replace("ses-1", "ses-2")
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    for msg in (
        tampered,
        _ses_message(other_key, address),
        _ses_message(key, address, SigningCertURL="https://attacker.example/cert.pem"),
        _ses_message(key, address, TopicArn="arn:aws:sns:eu-west-1:999999999999:other"),
        _ses_message(key, address, SignatureVersion="3"),
    ):
        assert _post_ses(msg).status_code == 401
    assert _reports(db, api.me["tenant"]["id"]) == []


def test_sns_certificate_url_must_be_aws() -> None:
    assert sns.cert_url_is_trusted(CERT_URL)
    for bad in (
        "http://sns.eu-west-1.amazonaws.com/x.pem",
        "https://sns.eu-west-1.amazonaws.com.evil.example/x.pem",
        "https://evil.example/sns.eu-west-1.amazonaws.com/x.pem",
        "https://sns.eu-west-1.amazonaws.com/x.txt",
    ):
        assert not sns.cert_url_is_trusted(bad), bad
