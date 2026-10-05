"""The workbook as the review surface (tiles, states, formulas, search, issue
cells) and the provider-agnostic connector layer."""

from __future__ import annotations

import io
import json

import httpx
import openpyxl
import pytest
from conftest import Api
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from test_deliverables import _book, _rows, _run

from app import connectors
from app.connectors.base import RemoteFile
from app.connectors.google import GoogleSheetsConnector
from app.connectors.microsoft import Microsoft365Connector


def _sheet(api: Api, rid: str) -> dict:
    return next(s for s in api.get(f"/api/v1/reports/{rid}/sheets").json() if s["sheet_name"] == "Claims")


def _grid(api: Api, rid: str, sid: str, **params) -> dict:
    r = api.get(f"/api/v1/reports/{rid}/sheets/{sid}/grid", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_grid_tiles_carry_state_issue_and_formula(api: Api):
    wb = openpyxl.load_workbook(io.BytesIO(_book(_rows())))
    wb["Claims"]["K3"] = "=G3+H3"  # a formula in an unmapped column
    buf = io.BytesIO()
    wb.save(buf)
    rid = _run(api, buf.getvalue())
    sid = _sheet(api, rid)["id"]
    g = _grid(api, rid, sid, offset=14, limit=1, col_offset=8, col_limit=2)  # row 15, columns I..J
    [row] = g["rows"]
    bad = row["cells"][0]
    assert row["row"] == 15 and g["col_offset"] == 8 and len(row["cells"]) == 2
    assert bad["state"] == "requires_reconciliation" and bad["issues"][0]["expected"] == 1500.0
    assert bad["issues"][0]["rule"] == "arithmetic_mismatch" and bad["issues"][0]["issue_id"]
    ok = _grid(api, rid, sid, offset=2, limit=1)["rows"][0]
    assert ok["cells"][0]["state"] == "verified"
    assert ok["cells"][10]["f"] == "=G3+H3"  # formula kept for inspection
    picked = _grid(api, rid, sid, rows="15,3")
    assert [r["row"] for r in picked["rows"]] == [3, 15]


def test_search_and_issue_cells(api: Api):
    rid = _run(api, _book(_rows()))
    sid = _sheet(api, rid)["id"]
    hits = api.get(f"/api/v1/reports/{rid}/sheets/{sid}/grid/search", params={"q": "euro"}).json()["items"]
    assert [h["cell"] for h in hits] == ["F16"]
    cells = api.get(f"/api/v1/reports/{rid}/sheets/{sid}/grid/issues").json()["items"]
    i15 = next(c for c in cells if c["cell"] == "I15")
    assert i15["state"] == "requires_reconciliation" and i15["open"] == 1


class FakeProvider:
    key, label, open_label = "fake", "Fake Sheets", "Open in Fake"

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    def configured(self) -> bool:
        return True

    def upload(self, name: str, body: bytes, file_id: str | None = None) -> RemoteFile:
        fid = file_id or f"f{len(self.files) + 1}"
        self.files[fid] = body
        return RemoteFile(fid, f"https://fake.example/{fid}", name)

    def download(self, file_id: str) -> bytes:
        return self.files[file_id]


def test_open_edit_and_pull_back_as_proposed_corrections(api: Api, monkeypatch: pytest.MonkeyPatch):
    fake = FakeProvider()
    monkeypatch.setitem(connectors.PROVIDERS, "fake", fake)
    rid = _run(api, _book(_rows()))
    assert {"key": "fake", "label": "Fake Sheets", "open_label": "Open in Fake", "configured": True} in \
        api.get("/api/v1/connectors").json()["items"]
    link = api.post(f"/api/v1/reports/{rid}/connectors/fake/open")
    assert link.status_code == 201, link.text
    link = link.json()
    assert link["web_url"] == "https://fake.example/f1"
    # Someone edits the copy in the provider: a value, a header, a claim reference.
    wb = openpyxl.load_workbook(io.BytesIO(fake.files["f1"]))
    ws = wb["Claims"]
    ws["I15"], ws["A2"], ws["A3"] = 1500, "Ref", "CLM-9999"
    buf = io.BytesIO()
    wb.save(buf)
    fake.files["f1"] = buf.getvalue()
    out = api.post(f"/api/v1/reports/{rid}/connectors/links/{link['id']}/pull").json()
    assert out["changed_cells"] == 3 and out["proposed"] == 1 and out["blocked"] == 2
    [c] = [c for c in api.get(f"/api/v1/reports/{rid}/corrections").json()["items"]]
    assert c["cell"] == "I15" and c["status"] == "PROPOSED" and c["source"] == "connector"
    assert c["policy"] == "APPROVAL_REQUIRED"  # an amount: never applied from outside without approval
    # Pulling again does not duplicate the pending proposal.
    assert api.post(f"/api/v1/reports/{rid}/connectors/links/{link['id']}/pull").json()["proposed"] == 0
    # Another tenant cannot reach the link.
    assert api.get("/api/v1/reports/x/connectors").status_code == 404


def test_unconfigured_provider_is_refused(api: Api, monkeypatch: pytest.MonkeyPatch):
    for name in ("M365_TENANT_ID", "M365_CLIENT_ID", "M365_CLIENT_SECRET", "M365_DRIVE_PATH"):
        monkeypatch.delenv(name, raising=False)
    rid = _run(api, _book(_rows()))
    r = api.post(f"/api/v1/reports/{rid}/connectors/microsoft365/open")
    assert r.status_code == 409 and "not connected" in r.json()["detail"]


def test_microsoft_graph_requests(monkeypatch: pytest.MonkeyPatch):
    for k, v in {"M365_TENANT_ID": "t1", "M365_CLIENT_ID": "c1", "M365_CLIENT_SECRET": "s1",
                 "M365_DRIVE_PATH": "users/reviews@example.com/drive"}.items():
        monkeypatch.setenv(k, v)
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if "oauth2" in req.url.path:
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        if req.method == "PUT":
            return httpx.Response(201, json={"id": "item1", "webUrl": "https://x.sharepoint.com/item1", "name": "a.xlsx"})
        return httpx.Response(200, content=b"xlsx-bytes")

    m = Microsoft365Connector(transport=httpx.MockTransport(handler))
    f = m.upload("a.xlsx", b"data")
    assert f.web_url.endswith("/item1") and m.download("item1") == b"xlsx-bytes"
    put = next(r for r in seen if r.method == "PUT")
    assert put.url.path == "/v1.0/users/reviews@example.com/drive/root:/TrueBind/a.xlsx:/content"
    assert put.headers["Authorization"] == "Bearer tok"
    assert b"client_secret=s1" in seen[0].content  # the secret goes only to the token endpoint


def test_google_drive_requests(monkeypatch: pytest.MonkeyPatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", json.dumps({"client_email": "sa@p.iam.gserviceaccount.com",
                                                                  "private_key": pem}))
    monkeypatch.setenv("GOOGLE_DRIVE_FOLDER_ID", "folder1")
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if req.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "gt", "expires_in": 3600})
        if "/upload/" in req.url.path:
            return httpx.Response(200, json={"id": "g1", "webViewLink": "https://docs.google.com/g1", "name": "a"})
        return httpx.Response(200, content=b"exported")

    g = GoogleSheetsConnector(transport=httpx.MockTransport(handler))
    assert g.configured()
    f = g.upload("a.xlsx", b"data")
    assert f.web_url == "https://docs.google.com/g1" and g.download("g1") == b"exported"
    assert b"jwt-bearer" in seen[0].content and b"assertion=" in seen[0].content
    up = next(r for r in seen if "/upload/" in r.url.path)
    assert b'"mimeType": "application/vnd.google-apps.spreadsheet"' in up.content and b'"folder1"' in up.content
