"""Test harness.

Every test gets an empty database and an empty object store:
- SQLite (default): a temp-file database created via the real Alembic
  migrations once per session, emptied between tests.
- PostgreSQL: set TRUEBIND_TEST_DATABASE_URL to a database owned by a
  NON-superuser role (superusers bypass Row Level Security). The same
  migrations run, so RLS policies and the append-only audit trigger are
  live during the tests.

The environment is configured BEFORE the app is imported, because config
is read at import time (as in production). Jobs run through the real job
system: the API enqueues, `run_jobs()` claims and executes them in-process
(tests in test_worker_isolation.py exercise the real child-process worker)."""

from __future__ import annotations

import io
import os
import shutil
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="truebind-tests-"))
os.environ.setdefault("TRUEBIND_ENV", "test")
os.environ["TRUEBIND_DATA_DIR"] = str(_TMP / "data")
os.environ["TRUEBIND_STORAGE_DIR"] = str(_TMP / "objects")
os.environ["DATABASE_URL"] = os.environ.get("TRUEBIND_TEST_DATABASE_URL") or f"sqlite:///{_TMP / 'test.db'}"
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ["ALLOW_SIGNUP"] = "1"

BACKEND = Path(__file__).resolve().parents[1]
BORDEREAUX_ROOT = BACKEND.parents[1] / "bordereaux"
sys.path.insert(0, str(BACKEND))

import openpyxl  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app import models  # noqa: E402,F401
from app.database import Base, get_engine, get_session_factory, set_tenant  # noqa: E402
from app.main import app  # noqa: E402
from app.security.ratelimit import limiter  # noqa: E402
from app.worker import run_pending_jobs_inline  # noqa: E402

IS_PG = get_engine().dialect.name == "postgresql"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PASSWORD = "correct horse battery staple"


def pytest_sessionstart(session):
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    if IS_PG:
        with get_engine().begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    command.upgrade(cfg, "head")


def _truncate() -> None:
    tables = [t.name for t in reversed(Base.metadata.sorted_tables)]
    with get_engine().begin() as conn:
        if IS_PG:
            conn.execute(text(f"TRUNCATE {', '.join(tables)} CASCADE"))
        else:
            for t in tables:
                conn.execute(text(f"DELETE FROM {t}"))


@pytest.fixture(autouse=True)
def _clean_state():
    _truncate()
    shutil.rmtree(Path(os.environ["TRUEBIND_STORAGE_DIR"]) / "tenants", ignore_errors=True)
    limiter.reset()
    yield


@pytest.fixture
def db(request):
    """A direct DB session for assertions. On PostgreSQL, RLS hides every
    tenant row unless a tenant is set -- so when the test also uses the
    `api` fixture, the session is bound to that tenant."""
    s = get_session_factory()()
    if "api" in request.fixturenames:
        set_tenant(s, request.getfixturevalue("api").me["tenant"]["id"])
    yield s
    s.close()


class Api:
    """A signed-in browser: cookie jar + CSRF header on unsafe requests."""

    def __init__(self, email: str = "owner@a.example", org: str = "Org A"):
        self.client = TestClient(app)
        r = self.client.post("/api/v1/auth/signup", json={"email": email, "password": PASSWORD,
                                                          "display_name": email.split("@")[0], "organisation": org})
        assert r.status_code == 201, r.text
        self.me = r.json()
        self.csrf = self.me["csrf_token"]

    def _h(self, extra=None):
        return {"X-CSRF-Token": self.csrf, **(extra or {})}

    def get(self, url, **kw):
        return self.client.get(url, **kw)

    def post(self, url, **kw):
        return self.client.post(url, headers=self._h(kw.pop("headers", None)), **kw)

    def patch(self, url, **kw):
        return self.client.patch(url, headers=self._h(kw.pop("headers", None)), **kw)

    def delete(self, url, **kw):
        return self.client.delete(url, headers=self._h(kw.pop("headers", None)), **kw)

    def upload(self, name: str, content: bytes, ctype: str = XLSX):
        return self.post("/api/v1/reports/upload", files={"file": (name, content, ctype)})

    def confirm_all(self, report_id: str) -> None:
        for s in self.get(f"/api/v1/reports/{report_id}/sheets").json():
            if s["status"] == "SKIPPED":
                continue
            m = self.get(f"/api/v1/reports/{report_id}/sheets/{s['id']}/mapping").json()
            choices = {f["field_code"]: f["source_column"] for f in m["fields"]}
            r = self.post(f"/api/v1/reports/{report_id}/sheets/{s['id']}/mapping", json={"mappings": choices})
            assert r.status_code == 200, r.text

    def ingest(self, name: str, content: bytes) -> str:
        r = self.upload(name, content)
        assert r.status_code == 202, r.text
        rid = r.json()["id"]
        run_jobs()
        return rid

    def full_run(self, name: str, content: bytes) -> tuple[str, dict]:
        rid = self.ingest(name, content)
        assert self.get(f"/api/v1/reports/{rid}").json()["status"] == "WAITING_FOR_REVIEW"
        self.confirm_all(rid)
        r = self.post(f"/api/v1/reports/{rid}/process")
        assert r.status_code == 202, r.text
        run_jobs()
        report = self.get(f"/api/v1/reports/{rid}").json()
        assert report["status"] == "COMPLETE", report
        return rid, report


def run_jobs() -> int:
    return run_pending_jobs_inline()


def xlsx_bytes(rows: list[list], sheet: str = "Claims", extra_sheets: dict[str, list[list]] | None = None) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    for r in rows:
        ws.append(r)
    for name, srows in (extra_sheets or {}).items():
        w2 = wb.create_sheet(name)
        for r in srows:
            w2.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


SIMPLE_HEADER = ["Claim Reference", "Insured Name", "Date of Loss", "Claim Status", "Currency",
                 "Paid to Date", "Outstanding Reserve", "Total Incurred"]


def simple_rows(n: int = 3) -> list[list]:
    rows = [SIMPLE_HEADER]
    for i in range(n):
        rows.append([f"CLM-{i:04d}", f"Insured {chr(65 + i % 26)}{i}", "2024-01-15", "Open", "GBP",
                     1000 + i, 500, 1500 + i])
    return rows


@pytest.fixture
def api():
    return Api()


@pytest.fixture
def api_b():
    return Api(email="owner@b.example", org="Org B")
