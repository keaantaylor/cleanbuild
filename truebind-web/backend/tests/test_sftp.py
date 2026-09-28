"""P2.4 -- SFTP destination settings and delivery outcomes (no server needed).

Real transfers are in tests/integration/test_sftp_sftpgo.py.

Acceptance:
- an admin saves one destination per organisation; the host key fingerprint
  (SHA256:...) is required, exactly one of password / private key, no ".."
  in the folder; secrets are write-only (never returned); saves audited;
- viewers cannot change it; other organisations cannot see it;
- delivering by SFTP without a destination is recorded NOT_CONFIGURED, and an
  unreachable server FAILED with a customer-safe reason -- never "sent".
"""

from __future__ import annotations

from typing import Any

from app.models.audit import AuditLogEntry
from conftest import PASSWORD, Api, simple_rows, xlsx_bytes
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

FP = "SHA256:" + "A" * 43
DEST: dict[str, Any] = {
    "host": "sftp.partner.example",
    "port": 22,
    "username": "truebind",
    "password": "partner-password-value",
    "host_key_fingerprint": FP,
    "remote_dir": "/inbound",
}


def test_destination_saved_without_exposing_secrets(api: Api, db: Session) -> None:
    r = api.client.put("/api/v1/org/sftp", json=DEST, headers={"X-CSRF-Token": api.csrf})
    assert r.status_code == 200, r.text
    body = api.get("/api/v1/org/sftp").json()
    assert body["auth"] == "password" and body["host_key_fingerprint"] == FP
    assert "partner-password-value" not in str(body) and "password" not in body
    entry = db.query(AuditLogEntry).filter_by(action_type="SFTP_DESTINATION_SAVED").one()
    assert "partner-password-value" not in str(entry.after_value)


def test_destination_validation(api: Api) -> None:
    def put(body: dict[str, Any]) -> Any:
        return api.client.put("/api/v1/org/sftp", json=body, headers={"X-CSRF-Token": api.csrf})

    assert put({**DEST, "host_key_fingerprint": "md5:aa:bb"}).status_code == 422
    assert put({**DEST, "private_key": "-----BEGIN KEY-----"}).status_code == 422
    assert put({k: v for k, v in DEST.items() if k != "password"}).status_code == 422
    assert put({**DEST, "remote_dir": "/inbound/../etc"}).status_code == 422
    assert put({**DEST, "host": "evil.example; rm -rf"}).status_code == 422


def test_viewers_cannot_change_it_and_other_orgs_cannot_see_it(api: Api, api_b: Api) -> None:
    api.client.put("/api/v1/org/sftp", json=DEST, headers={"X-CSRF-Token": api.csrf})
    other = api_b.get("/api/v1/org/sftp")
    assert other.status_code == 200 and other.json() is None
    token = api.post("/api/v1/org/invitations", json={"email": "v@a.example", "role": "VIEWER"}).json()["accept_token"]
    viewer = TestClient(api.client.app)
    me = viewer.post(
        "/api/v1/auth/invitations/accept", json={"token": token, "display_name": "V", "password": PASSWORD}
    ).json()
    assert viewer.get("/api/v1/org/sftp").status_code == 200
    r = viewer.put("/api/v1/org/sftp", json=DEST, headers={"X-CSRF-Token": me["csrf_token"]})
    assert r.status_code == 403


def test_sftp_delivery_outcomes_are_recorded_honestly(api: Api) -> None:
    rid, _ = api.full_run("a.xlsx", xlsx_bytes(simple_rows()))
    none = api.post(f"/api/v1/reports/{rid}/deliveries", json={"kind": "claims_csv", "channel": "sftp"})
    assert none.status_code == 201 and none.json()["status"] == "NOT_CONFIGURED"
    api.client.put(
        "/api/v1/org/sftp", json={**DEST, "host": "127.0.0.1", "port": 1}, headers={"X-CSRF-Token": api.csrf}
    )
    failed = api.post(f"/api/v1/reports/{rid}/deliveries", json={"kind": "claims_csv", "channel": "sftp"})
    assert failed.json()["status"] == "FAILED" and "Could not reach" in failed.json()["error"]
    assert (
        api.post(f"/api/v1/reports/{rid}/deliveries", json={"kind": "claims_csv", "channel": "email"}).status_code
        == 422
    )
