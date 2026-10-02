"""Website enquiries: stored reliably, bots ignored, rate-limited, and only
readable by the operators named in LEADS_ADMIN_EMAILS."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.leads import Lead
from app.settings import get_settings

from conftest import Api

FORM = {"kind": "demo", "email": "Jo@Acme.example", "name": "Jo", "company": "Acme MGA", "note": "=HYPERLINK(1)",
        "page": "/", "attribution": {"utm_source": "linkedin", "utm_campaign": "launch", "evil": "x"}}


@pytest.fixture
def operators(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("LEADS_ADMIN_EMAILS", "owner@a.example")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_submission_is_stored_with_attribution(db):
    r = TestClient(app).post("/api/v1/leads", json=FORM)
    assert r.status_code == 201
    lead = db.query(Lead).one()
    assert (lead.kind, lead.email, lead.company) == ("demo", "jo@acme.example", "Acme MGA")
    assert lead.attribution == {"utm_source": "linkedin", "utm_campaign": "launch"}, "unknown keys are dropped"


def test_honeypot_is_accepted_but_not_stored(db):
    r = TestClient(app).post("/api/v1/leads", json={**FORM, "website": "http://spam.example"})
    assert r.status_code == 201
    assert db.query(Lead).count() == 0


def test_invalid_email_and_kind_are_rejected():
    c = TestClient(app)
    assert c.post("/api/v1/leads", json={**FORM, "email": "not-an-email"}).status_code == 422
    assert c.post("/api/v1/leads", json={**FORM, "kind": "admin"}).status_code == 422


def test_rate_limited_per_ip():
    c = TestClient(app)
    codes = [c.post("/api/v1/leads", json=FORM).status_code for _ in range(11)]
    assert codes[:10] == [201] * 10 and codes[10] == 429


def test_only_operators_can_read(operators):
    TestClient(app).post("/api/v1/leads", json=FORM)
    assert TestClient(app).get("/api/v1/leads").status_code == 401
    other = Api("someone@b.example", "Org B")
    assert other.get("/api/v1/leads").status_code == 403
    op = Api()
    rows = op.get("/api/v1/leads").json()
    assert [x["email"] for x in rows] == ["jo@acme.example"]
    csv = op.get("/api/v1/leads/export.csv").text
    assert "'=HYPERLINK(1)" in csv, "formula-looking text is neutralised in the CSV"


# ---- Health Check requests with a file

_XLSX: list[bytes] = []


def _xlsx() -> bytes:
    """Built once: an xlsx embeds a timestamp, so rebuilding it gives different bytes."""
    from conftest import simple_rows, xlsx_bytes

    if not _XLSX:
        _XLSX.append(xlsx_bytes(simple_rows(3)))
    return _XLSX[0]


def _send(c: TestClient, **over):
    data = {"email": "kim@coverholder.example", "name": "Kim", "company": "Cover Ltd", "consent": "true", **over}
    files = over.pop("files", None) or {"file": ("bordereau.xlsx", _xlsx(),
                                                 "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    data.pop("files", None)
    return c.post("/api/v1/leads/health-check", data=data, files=files)


def test_health_check_file_is_stored_and_emailed(db, monkeypatch: pytest.MonkeyPatch, operators):
    from app.models.leads import LeadFile
    from app.routes import leads as leads_route

    sent: list[tuple] = []
    monkeypatch.setattr(leads_route, "_notify", lambda *a: sent.append(a))
    r = _send(TestClient(app))
    assert r.status_code == 201, r.text
    lead = db.query(Lead).one()
    assert lead.kind == "health" and lead.consent_at is not None and lead.file_name == "bordereau.xlsx"
    assert db.get(LeadFile, lead.id).content == _xlsx()
    assert sent and sent[0][-1][0] == "bordereau.xlsx", "the notification carries the file"
    op = Api()
    assert op.get(f"/api/v1/leads/{lead.id}/file").content == _xlsx()
    assert Api("someone@b.example", "Org B").get(f"/api/v1/leads/{lead.id}/file").status_code == 403


def test_health_check_needs_consent_a_spreadsheet_and_at_most_10mb(db):
    c = TestClient(app)
    assert _send(c, consent="false").status_code == 422
    assert _send(c, files={"file": ("notes.pdf", b"%PDF-1.4", "application/pdf")}).status_code == 422
    assert _send(c, files={"file": ("fake.xlsx", b"not a zip at all", "application/octet-stream")}).status_code == 422
    big = b"a,b\n" + b"1,2\n" * (10 * 1024 * 1024 // 4 + 10)
    assert _send(c, files={"file": ("big.csv", big, "text/csv")}).status_code == 413
    assert db.query(Lead).count() == 0


def test_old_health_check_files_are_deleted(db):
    import datetime as dt

    from app.models.leads import LeadFile
    from app.services import retention_service

    assert _send(TestClient(app)).status_code == 201
    f = db.query(LeadFile).one()
    f.created_at = dt.datetime.now(dt.UTC) - dt.timedelta(days=31)
    db.commit()
    assert retention_service.purge_old_lead_files(db) == 1
    assert db.query(LeadFile).count() == 0 and db.query(Lead).count() == 1
