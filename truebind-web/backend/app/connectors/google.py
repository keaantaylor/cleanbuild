"""Google Sheets (Google Drive API) with a service account.

The workbook is uploaded and converted to a Google Sheet in
GOOGLE_DRIVE_FOLDER_ID (share that folder with the service account); edits
are read back by exporting the sheet as xlsx. The service account key is read
from GOOGLE_SERVICE_ACCOUNT_JSON (the JSON itself, or a path to it) and is
used only to sign a short-lived token request (RS256).
"""

from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from .base import ConnectorError, RemoteFile

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
SHEET = "application/vnd.google-apps.spreadsheet"
SCOPE = "https://www.googleapis.com/auth/drive.file"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class GoogleSheetsConnector:
    key = "google"
    label = "Google Sheets"
    open_label = "Open in Google Sheets"

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport
        self._token: tuple[str, float] | None = None

    def _account(self) -> dict | None:
        raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
        if not raw:
            return None
        try:
            return json.loads(raw if raw.startswith("{") else Path(raw).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def configured(self) -> bool:
        acc = self._account()
        return bool(acc and acc.get("client_email") and acc.get("private_key")
                    and os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "").strip())

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=60, transport=self._transport)

    def _access_token(self, client: httpx.Client) -> str:
        if self._token and self._token[1] > time.time() + 60:
            return self._token[0]
        acc = self._account() or {}
        uri = acc.get("token_uri", "https://oauth2.googleapis.com/token")
        now = int(time.time())
        head = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
        claims = _b64(json.dumps({"iss": acc["client_email"], "scope": SCOPE, "aud": uri, "iat": now,
                                  "exp": now + 3600}).encode())
        key = serialization.load_pem_private_key(acc["private_key"].encode(), password=None)
        sig = key.sign(f"{head}.{claims}".encode(), padding.PKCS1v15(), hashes.SHA256())  # type: ignore[union-attr]
        r = client.post(uri, data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                                   "assertion": f"{head}.{claims}.{_b64(sig)}"})
        if r.status_code != 200:
            raise ConnectorError("Google refused the service account.")
        body = r.json()
        self._token = (body["access_token"], time.time() + int(body.get("expires_in", 3600)))
        return self._token[0]

    def upload(self, name: str, body: bytes, file_id: str | None = None) -> RemoteFile:
        if not self.configured():
            raise ConnectorError("Google Sheets is not connected on this server.")
        meta: dict = {"name": name.rsplit(".", 1)[0], "mimeType": SHEET}
        if not file_id:
            meta["parents"] = [os.environ["GOOGLE_DRIVE_FOLDER_ID"].strip()]
        boundary = "truebind-upload-boundary"
        payload = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{json.dumps(meta)}\r\n"
                   f"--{boundary}\r\nContent-Type: {XLSX}\r\n\r\n").encode() + body + f"\r\n--{boundary}--".encode()
        url = "https://www.googleapis.com/upload/drive/v3/files"
        with self._client() as client:
            headers = {"Authorization": f"Bearer {self._access_token(client)}",
                       "Content-Type": f"multipart/related; boundary={boundary}"}
            params = {"uploadType": "multipart", "fields": "id,name,webViewLink", "supportsAllDrives": "true"}
            r = (client.patch(f"{url}/{file_id}", params=params, content=payload, headers=headers) if file_id
                 else client.post(url, params=params, content=payload, headers=headers))
            if r.status_code not in (200, 201):
                raise ConnectorError("Google did not accept the file.")
            item = r.json()
            return RemoteFile(file_id=item["id"], web_url=item.get("webViewLink", ""), name=item.get("name", name))

    def download(self, file_id: str) -> bytes:
        if not self.configured():
            raise ConnectorError("Google Sheets is not connected on this server.")
        with self._client() as client:
            r = client.get(f"https://www.googleapis.com/drive/v3/files/{file_id}/export",
                           params={"mimeType": XLSX}, headers={"Authorization": f"Bearer {self._access_token(client)}"})
            if r.status_code != 200:
                raise ConnectorError("Google could not export the sheet.")
            return r.content
