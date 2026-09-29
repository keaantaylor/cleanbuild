"""P2.4 -- SFTP delivery to a real server (compose SFTPGo, TRUEBIND_IT=1).

- "Test connection" succeeds with the right pinned host key;
- a delivery writes the CSV (atomically renamed into place) and is recorded
  DELIVERED; the file's content is the export;
- a wrong pinned fingerprint sends nothing and is recorded FAILED;
- with auto-delivery on, a completed report is delivered without a request.
"""

from __future__ import annotations

import io
import secrets
import socket
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlparse

import httpx
import paramiko
import pytest
from app.services import sftp_service
from conftest import Api, simple_rows, xlsx_bytes
from integration_env import IT, service_url

pytestmark = pytest.mark.skipif(not IT, reason="integration: needs docker-compose.test.yml (TRUEBIND_IT=1)")


@pytest.fixture
def sftp_user() -> Iterator[dict[str, Any]]:
    api_base = service_url("SFTPGO_API")
    token = httpx.get(f"{api_base}/api/v2/token", auth=("admin", "sftpgo-test-only"), timeout=10).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    username = "tb" + secrets.token_hex(4)
    password = secrets.token_urlsafe(16)
    r = httpx.post(
        f"{api_base}/api/v2/users",
        headers=headers,
        json={
            "status": 1,
            "username": username,
            "password": password,
            "home_dir": f"/srv/sftpgo/data/{username}",
            "permissions": {"/": ["*"]},
        },
        timeout=10,
    )
    assert r.status_code == 201, r.text
    target = urlparse(service_url("SFTP"))
    host, port = target.hostname or "127.0.0.1", target.port or 22
    sock = socket.create_connection((host, port), timeout=10)
    transport = paramiko.Transport(sock)
    transport.start_client(timeout=10)
    fp = sftp_service.fingerprint(transport.get_remote_server_key())
    transport.close()
    yield {"host": host, "port": port, "username": username, "password": password, "fp": fp}
    httpx.delete(f"{api_base}/api/v2/users/{username}", headers=headers, timeout=10)


def _configure(api: Api, user: dict[str, Any], **extra: Any) -> None:
    body = {
        "host": user["host"],
        "port": user["port"],
        "username": user["username"],
        "password": user["password"],
        "host_key_fingerprint": user["fp"],
        "remote_dir": "/",
        **extra,
    }
    r = api.client.put("/api/v1/org/sftp", json=body, headers={"X-CSRF-Token": api.csrf})
    assert r.status_code == 200, r.text


def _files(user: dict[str, Any]) -> dict[str, bytes]:
    transport = paramiko.Transport((user["host"], user["port"]))
    transport.connect(username=user["username"], password=user["password"])
    client = paramiko.SFTPClient.from_transport(transport)
    assert client is not None
    out = {}
    for name in client.listdir("/"):
        buf = io.BytesIO()
        client.getfo(f"/{name}", buf)
        out[name] = buf.getvalue()
    client.close()
    transport.close()
    return out


def test_delivery_to_a_real_server(api: Api, sftp_user: dict[str, Any]) -> None:
    _configure(api, sftp_user)
    assert api.post("/api/v1/org/sftp/test").json()["ok"] is True
    rid, _ = api.full_run("a.xlsx", xlsx_bytes(simple_rows(4)))
    r = api.post(f"/api/v1/reports/{rid}/deliveries", json={"kind": "claims_csv", "channel": "sftp"})
    assert r.json()["status"] == "DELIVERED", r.text
    files = _files(sftp_user)
    [name] = [n for n in files if n.endswith(".csv")]
    assert not any(n.endswith(".part") for n in files)
    assert b"CLM-0003" in files[name]


def test_wrong_pinned_key_sends_nothing(api: Api, sftp_user: dict[str, Any]) -> None:
    _configure(api, sftp_user, host_key_fingerprint="SHA256:" + "B" * 43)
    test = api.post("/api/v1/org/sftp/test").json()
    assert test["ok"] is False and "does not match" in test["message"]
    rid, _ = api.full_run("a.xlsx", xlsx_bytes(simple_rows()))
    r = api.post(f"/api/v1/reports/{rid}/deliveries", json={"kind": "claims_csv", "channel": "sftp"})
    assert r.json()["status"] == "FAILED" and "does not match" in r.json()["error"]
    assert _files(sftp_user) == {}


def test_auto_delivery_on_completion(api: Api, sftp_user: dict[str, Any]) -> None:
    _configure(api, sftp_user, auto_deliver=True)
    api.full_run("auto.xlsx", xlsx_bytes(simple_rows()))
    names = sorted(_files(sftp_user))
    assert len(names) == 2 and all(n.endswith(".csv") for n in names), names
