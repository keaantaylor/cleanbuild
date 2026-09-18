"""Every test gets a fresh, isolated in-memory SQLite database -- never
the dev-mode data/truebind.db file -- via a get_db dependency override,
same isolation pattern as bordereaux/tests/test_audit_governance.py's
_fresh_session()."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import database
from app import models  # noqa: F401 -- populates Base.metadata
from app.database import Base, get_db
from app.main import app


@pytest.fixture
def client():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # Report processing now runs as a background task (fix spec Section
    # 6.2) with its own DB session, opened via database.get_session_
    # factory() rather than the get_db FastAPI dependency -- a background
    # task isn't part of the request's DI graph, so it can't reuse a
    # session handed out through app.dependency_overrides. Point the
    # module-level engine/session-factory cache at this same test engine
    # for the duration of the test, so a background task sees the exact
    # same isolated in-memory DB the request layer does, and restore the
    # real (env-driven) singletons afterward.
    prev_engine, prev_session_factory = database._engine, database._SessionLocal
    database._engine, database._SessionLocal = engine, TestSession

    yield TestClient(app)

    app.dependency_overrides.clear()
    database._engine, database._SessionLocal = prev_engine, prev_session_factory
    engine.dispose()
