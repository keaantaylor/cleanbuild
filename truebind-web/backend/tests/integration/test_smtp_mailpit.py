"""P2.2 -- outbound e-mail through a real SMTP server (compose Mailpit).

A delivery request sends the export as an attachment; the message arrives
with the right subject, recipient and CSV attachment, and the delivery is
recorded DELIVERED and audited."""

from __future__ import annotations

from urllib.parse import urlparse

import httpx
import pytest
from app import config
from conftest import Api, simple_rows, xlsx_bytes
from integration_env import IT, service_url

pytestmark = pytest.mark.skipif(not IT, reason="integration: needs docker-compose.test.yml (TRUEBIND_IT=1)")


def test_export_is_delivered_by_email(api: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    smtp = urlparse(service_url("SMTP"))
    monkeypatch.setattr(config, "SMTP_HOST", smtp.hostname or "")
    monkeypatch.setattr(config, "SMTP_PORT", smtp.port or 25)
    monkeypatch.setattr(config, "SMTP_STARTTLS", False)
    monkeypatch.setattr(config, "SMTP_USER", "")
    mail_api = service_url("MAILPIT_API")
    httpx.delete(f"{mail_api}/api/v1/messages", timeout=10)

    rid, _ = api.full_run("mail.xlsx", xlsx_bytes(simple_rows(5)))
    r = api.post(
        f"/api/v1/reports/{rid}/deliveries",
        json={"kind": "claims_csv", "channel": "email", "recipient": "ops@partner.example"},
    )
    assert r.status_code == 201 and r.json()["status"] == "DELIVERED", r.text

    messages = httpx.get(f"{mail_api}/api/v1/messages", timeout=10).json()["messages"]
    assert len(messages) == 1
    msg = messages[0]
    assert msg["To"][0]["Address"] == "ops@partner.example"
    assert "mail.xlsx" in msg["Subject"]
    detail = httpx.get(f"{mail_api}/api/v1/message/{msg['ID']}", timeout=10).json()
    names = [a["FileName"] for a in detail["Attachments"]]
    assert len(names) == 1 and names[0].endswith(".csv")
    audit = api.get(f"/api/v1/reports/{rid}/audit").json()["items"]
    assert any(e["action_type"] == "EXPORT_GENERATED" and e["after_value"]["status"] == "DELIVERED" for e in audit)
