"""P8 -- sender pre-flight portal.

Acceptance:
- a SENDER member can pre-flight a file: the same intake gate, exact alias
  mapping only (no AI), the engine's checks; the answer lists required
  fields not found, rows missing mandatory values, arithmetic mismatches,
  duplicates and the coverage statement; nothing is stored except an audit
  event with the file's SHA-256;
- a SENDER can send a file: it enters the organisation's inbox as a normal
  report (channel "portal") and is listed in the sender's own submissions;
- a SENDER sees only their own submissions, never the organisation's
  reports; other roles cannot use the sender endpoints;
- files the intake gate refuses are refused here too.
"""

from __future__ import annotations

from typing import Any

from app.main import app
from app.models.reports import Report
from conftest import PASSWORD, XLSX, Api, simple_rows, xlsx_bytes
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


class Sender:
    def __init__(self, owner: Api, email: str = "tpa@partner.example") -> None:
        inv = owner.post("/api/v1/org/invitations", json={"email": email, "role": "SENDER"}).json()
        self.client = TestClient(app)
        r = self.client.post(
            "/api/v1/auth/invitations/accept",
            json={"token": inv["accept_token"], "display_name": "TPA", "password": PASSWORD},
        )
        assert r.status_code in (200, 201), r.text
        self.h = {"X-CSRF-Token": r.json()["csrf_token"]}

    def post(self, url: str, **kw: Any) -> Any:
        return self.client.post(url, headers=self.h, **kw)


def _file(rows: list[list[Any]]) -> dict[str, tuple[str, bytes, str]]:
    return {"file": ("bdx.xlsx", xlsx_bytes(rows), XLSX)}


def test_preflight_reports_problems_and_stores_nothing(api: Api, db: Session) -> None:
    sender = Sender(api)
    header = ["Claim Reference", "Insured Name", "Date of Loss", "Claim Status", "Currency", "Paid to Date",
              "Outstanding Reserve", "Total Incurred", "Broker Notes"]  # fmt: skip
    rows: list[list[Any]] = [
            header,
            ["P-1", "", "2024-01-15", "Open", "GBP", 100, 50, 999, "x"],
            ["P-2", "Ok Ltd", "2024-01-16", "Open", "GBP", 100, 50, 150, "y"]]  # fmt: skip
    r = sender.post("/api/v1/sender/preflight", files=_file(rows))
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["ready"] is False and out["rows"] == 2
    assert out["missing_mandatory_rows"] == 1 and out["arithmetic_mismatches"] == 1
    assert out["sheets"][0]["unmapped_columns"] == ["Broker Notes"]
    assert any(i["row_number"] == 2 for i in out["issues"]) and out["coverage_statement"]
    assert db.query(Report).count() == 0, "pre-flight keeps nothing"
    actions = [e["action_type"] for e in api.get("/api/v1/audit").json()["items"]]
    assert "SENDER_PREFLIGHT_RUN" in actions
    clean = sender.post("/api/v1/sender/preflight", files=_file(simple_rows(3))).json()
    assert clean["ready"] is True and clean["issues"] == []


def test_submission_reaches_the_inbox_and_senders_see_only_their_own(api: Api) -> None:
    sender = Sender(api)
    other = Sender(api, "other@partner.example")
    r = sender.post("/api/v1/sender/submissions", files=_file(simple_rows(2)), data={"programme": "Marine"})
    assert r.status_code == 202, r.text
    sub = r.json()
    inbox = api.get("/api/v1/reports").json()["items"]
    mine = next(x for x in inbox if x["id"] == sub["id"])
    assert mine["source_channel"] == "portal" and mine["programme"] == "Marine" and mine["sender"]
    assert [s["id"] for s in sender.client.get("/api/v1/sender/submissions").json()] == [sub["id"]]
    assert other.client.get("/api/v1/sender/submissions").json() == []
    assert sender.client.get("/api/v1/reports").status_code == 403
    assert sender.client.get(f"/api/v1/reports/{sub['id']}").status_code == 403


def test_only_senders_use_the_portal_and_the_gate_still_applies(api: Api) -> None:
    assert api.post("/api/v1/sender/preflight", files=_file(simple_rows(1))).status_code == 403
    sender = Sender(api)
    bad = sender.post("/api/v1/sender/preflight", files={"file": ("x.xlsx", b"MZ\x90\x00not a workbook", XLSX)})
    assert bad.status_code in (400, 415), bad.text
