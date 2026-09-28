"""Reachability of every docker-compose.test.yml service (P0 harness).

Runs only under `verify.py --full` (TRUEBIND_IT=1). There, an unreachable
service is a FAILURE, not a skip: the later phases' integration tests
depend on every one of these being up."""

from __future__ import annotations

import json
import smtplib
import socket
import time
import urllib.request
import uuid
from email.message import EmailMessage

import pytest
from integration_env import IT, service_url

pytestmark = [pytest.mark.integration, pytest.mark.skipif(not IT, reason="integration: run via verify.py --full")]


def _get(url: str, headers: dict[str, str] | None = None, timeout: float = 10) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def test_redis_ping() -> None:
    host, port = service_url("REDIS").split("//")[1].split(":")
    with socket.create_connection((host, int(port)), timeout=5) as s:
        s.sendall(b"*1\r\n$4\r\nPING\r\n")
        assert s.recv(16).startswith(b"+PONG")


def test_minio_live() -> None:
    status, _ = _get(service_url("S3") + "/minio/health/live")
    assert status == 200


def test_mailpit_receives_smtp() -> None:
    subject = f"verify-{uuid.uuid4()}"
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = "verify@truebind.test", "ops@truebind.test", subject
    msg.set_content("harness probe")
    host, port = service_url("SMTP").split("//")[1].split(":")
    with smtplib.SMTP(host, int(port), timeout=10) as smtp:
        smtp.send_message(msg)
    for _ in range(20):
        _, body = _get(service_url("MAILPIT_API") + f"/api/v1/search?query=subject:{subject}")
        if json.loads(body)["messages_count"] == 1:
            return
        time.sleep(0.25)
    pytest.fail("message did not arrive in Mailpit")


def test_sftpgo_healthy() -> None:
    status, _ = _get(service_url("SFTPGO_API") + "/healthz")
    assert status == 200


def test_oidc_discovery() -> None:
    _, body = _get(service_url("OIDC_ISSUER") + "/.well-known/openid-configuration")
    doc = json.loads(body)
    assert doc["issuer"].rstrip("/").endswith("/default")
    assert "authorization_endpoint" in doc and "token_endpoint" in doc


def test_stripe_mock() -> None:
    status, body = _get(service_url("STRIPE_API") + "/v1/customers", {"Authorization": "Bearer sk_test_verify"})
    assert status == 200 and json.loads(body)["object"] == "list"


def test_webhook_receiver_roundtrip() -> None:
    base = service_url("WEBHOOK_RECEIVER")
    marker = str(uuid.uuid4())
    req = urllib.request.Request(
        base + "/hooks/probe",
        data=json.dumps({"m": marker}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        assert r.status == 200
    _, body = _get(base + "/deliveries")
    assert any(marker in d["body"] for d in json.loads(body))
