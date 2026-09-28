"""Engine/session factory. Mirrors bordereaux/db/session.py's pattern:
SQLite by default, Postgres via DATABASE_URL, no code change needed."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import MetaData, create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_database_url


# Deterministic constraint names so migrations can alter/drop constraints on
# every backend (SQLite batch mode cannot target unnamed constraints).
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def build_engine(url: str | None = None):
    url = url or get_database_url()
    if url.startswith("sqlite"):
        engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _):  # WAL: readers are not blocked by the writer (forensic: poll 5xx)
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA busy_timeout=30000")
            cur.close()
        return engine
    return create_engine(url, pool_size=10, max_overflow=10, pool_pre_ping=True, pool_recycle=1800)


def set_tenant(db: Session, tenant_id: str | None, worker: bool = False) -> None:
    """Bind this session to a tenant. On PostgreSQL every transaction the
    session begins sets `app.tenant_id` (transaction-local), which the RLS
    policies from migration 0002 enforce. Application queries are ALSO
    filtered by tenant; the database policy is the backstop."""
    db.info["tenant_id"] = tenant_id
    db.info["worker"] = worker
    if db.in_transaction():
        _apply_tenant(db, db.connection())


def set_identity(db: Session, *, user_id: str | None = None, session_token_hash: str | None = None) -> None:
    """Bind the caller's identity for identity-table RLS (migration 0007):
    before a tenant is known, a session row is visible only to the holder of
    its token hash and membership rows only to their own user."""
    if user_id is not None:
        db.info["user_id"] = user_id
    if session_token_hash is not None:
        db.info["session_token_hash"] = session_token_hash
    if db.in_transaction():
        _apply_tenant(db, db.connection())


def _apply_tenant(session: Session, connection) -> None:
    if connection.dialect.name != "postgresql":
        return
    connection.execute(
        text("SELECT set_config('app.tenant_id', :t, true), set_config('app.worker', :w, true), "
             "set_config('app.user_id', :u, true), set_config('app.session_token_hash', :s, true)"),
        {"t": session.info.get("tenant_id") or "", "w": "on" if session.info.get("worker") else "off",
         "u": session.info.get("user_id") or "", "s": session.info.get("session_token_hash") or ""})


@event.listens_for(Session, "after_begin")
def _after_begin(session, transaction, connection):
    _apply_tenant(session, connection)


_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = build_engine()
    return _engine


def get_session_factory() -> sessionmaker:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: one session per request."""
    session_factory = get_session_factory()
    db = session_factory()
    try:
        yield db
    finally:
        db.close()
