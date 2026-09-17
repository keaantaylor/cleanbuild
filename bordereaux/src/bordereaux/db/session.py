"""Engine/session factory. Default is a local SQLite file, appropriate
for MVP development (Section 0 of the redevelopment prompt explicitly
allows this); set DATABASE_URL to point at Postgres for a
production-minded deployment -- no code change required, only the
connection string."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_SQLITE_PATH = REPO_ROOT / "data" / "app.db"


def get_database_url() -> str:
    return os.environ.get("DATABASE_URL", f"sqlite:///{DEFAULT_SQLITE_PATH}")


def build_engine(database_url: str | None = None):
    url = database_url or get_database_url()
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    if url.startswith("sqlite"):
        DEFAULT_SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(url, connect_args=connect_args)


_engine = None
_SessionLocal: sessionmaker | None = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = build_engine()
    return _engine


def get_session_factory() -> sessionmaker:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionLocal


def new_session() -> Session:
    return get_session_factory()()
