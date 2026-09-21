"""Every test gets a fresh, isolated SQLite database -- never the
dev-mode data/truebind.db file -- via a get_db dependency override, same
isolation pattern as bordereaux/tests/test_audit_governance.py's
_fresh_session().

A real (temp-file) database, not `sqlite:///:memory:`, on purpose: since
Section 6, /process's pipeline work happens on a background thread with
its own session, running concurrently with whatever the test's main
thread does next (typically polling GET /{report_id} in a loop). An
in-memory db only exists per-connection, so making both threads see the
same data required forcing them onto one literal shared sqlite3
connection via StaticPool -- but a raw sqlite3 connection isn't safe for
two threads to drive at once regardless of check_same_thread, and that
setup produced exactly the intermittent partial-read corruption a real
concurrent DB access bug would (a report reading back COMPLETE with only
part of its exception rows persisted). A temp-file database lets each
session open its own real connection, coordinated by SQLite's normal
file-level locking -- the same story a genuine multi-connection Postgres
pool has in production -- so this setup exercises the actual concurrency
this feature introduces instead of a test-only artifact of it."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401 -- populates Base.metadata
from app.database import Base, get_db, get_session_factory
from app.main import app


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    # Section 6: /process's background thread builds its own session from
    # this factory instead of from the request-scoped `get_db` generator
    # -- override it too, to the same engine, or it would otherwise land
    # on the real dev/prod sqlite file `get_session_factory()` builds.
    app.dependency_overrides[get_session_factory] = lambda: TestSession
    yield TestClient(app)
    app.dependency_overrides.clear()
    engine.dispose()
