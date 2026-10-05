"""Microsoft 365 (OneDrive / SharePoint through Microsoft Graph).

App-only access (client credentials) to one drive named by M365_DRIVE_PATH,
for example "users/reviews@insurer.example/drive" or "sites/<site-id>/drive".
Files go into M365_FOLDER (default "TrueBind"). The webUrl Graph returns
opens the workbook in Excel; OneDrive keeps every earlier version when a new
one is uploaded over it.

Environment: M365_TENANT_ID, M365_CLIENT_ID, M365_CLIENT_SECRET, M365_DRIVE_PATH.
"""

from __future__ import annotations

import os
import time
from urllib.parse import quote

import httpx

from .base import ConnectorError, RemoteFile

GRAPH = "https://graph.microsoft.com/v1.0"
SIMPLE_UPLOAD_MAX = 4 * 1024 * 1024
CHUNK = 5 * 320 * 1024  # Graph wants multiples of 320 KiB


class Microsoft365Connector:
    key = "microsoft365"
    label = "Microsoft 365"
    open_label = "Open in Excel"

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport
        self._token: tuple[str, float] | None = None

    def _env(self, name: str) -> str:
        return os.environ.get(name, "").strip()

    def configured(self) -> bool:
        return all(self._env(n) for n in ("M365_TENANT_ID", "M365_CLIENT_ID", "M365_CLIENT_SECRET", "M365_DRIVE_PATH"))

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=60, transport=self._transport)

    def _access_token(self, client: httpx.Client) -> str:
        if self._token and self._token[1] > time.time() + 60:
            return self._token[0]
        r = client.post(f"https://login.microsoftonline.com/{quote(self._env('M365_TENANT_ID'))}/oauth2/v2.0/token",
                        data={"grant_type": "client_credentials", "client_id": self._env("M365_CLIENT_ID"),
                              "client_secret": self._env("M365_CLIENT_SECRET"),
                              "scope": "https://graph.microsoft.com/.default"})
        if r.status_code != 200:
            raise ConnectorError("Microsoft 365 refused the app credentials.")
        body = r.json()
        self._token = (body["access_token"], time.time() + int(body.get("expires_in", 3600)))
        return self._token[0]

    def _drive(self) -> str:
        return f"{GRAPH}/{self._env('M365_DRIVE_PATH').strip('/')}"

    def upload(self, name: str, body: bytes, file_id: str | None = None) -> RemoteFile:
        if not self.configured():
            raise ConnectorError("Microsoft 365 is not connected on this server.")
        folder = self._env("M365_FOLDER") or "TrueBind"
        target = (f"{self._drive()}/items/{quote(file_id)}" if file_id
                  else f"{self._drive()}/root:/{quote(folder)}/{quote(name)}:")
        with self._client() as client:
            auth = {"Authorization": f"Bearer {self._access_token(client)}"}
            if len(body) <= SIMPLE_UPLOAD_MAX:
                r = client.put(f"{target}/content", content=body, headers={
                    **auth, "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"})
            else:
                s = client.post(f"{target}/createUploadSession", headers=auth,
                                json={"item": {"@microsoft.graph.conflictBehavior": "replace"}})
                if s.status_code not in (200, 201):
                    raise ConnectorError("Microsoft 365 did not accept the upload.")
                url, r = s.json()["uploadUrl"], None
                for start in range(0, len(body), CHUNK):
                    part = body[start:start + CHUNK]
                    r = client.put(url, content=part, headers={
                        "Content-Range": f"bytes {start}-{start + len(part) - 1}/{len(body)}"})
                    if r.status_code not in (200, 201, 202):
                        raise ConnectorError("Microsoft 365 stopped the upload part-way.")
            if r is None or r.status_code not in (200, 201):
                raise ConnectorError("Microsoft 365 did not accept the file.")
            item = r.json()
            return RemoteFile(file_id=item["id"], web_url=item.get("webUrl", ""), name=item.get("name", name))

    def download(self, file_id: str) -> bytes:
        if not self.configured():
            raise ConnectorError("Microsoft 365 is not connected on this server.")
        with self._client() as client:
            r = client.get(f"{self._drive()}/items/{quote(file_id)}/content", follow_redirects=True,
                           headers={"Authorization": f"Bearer {self._access_token(client)}"})
            if r.status_code != 200:
                raise ConnectorError("Microsoft 365 could not return the file.")
            return r.content
