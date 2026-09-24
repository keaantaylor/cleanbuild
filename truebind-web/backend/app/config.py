"""Environment-driven settings. No secrets in code: everything sensitive
comes from the environment (see .env.example, which contains no values)."""

from __future__ import annotations

import os
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Minimal .env reader (KEY=VALUE, # comments). Real environment
    variables always win. Loaded here, at import time of the single config
    module, so the API, the worker, its child processes and Alembic all
    resolve the SAME settings -- a second terminal can no longer end up on
    a different database because one env var was forgotten there."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


if os.environ.get("TRUEBIND_ENV", "development") != "production" and not os.environ.get("TRUEBIND_NO_DOTENV"):
    _load_dotenv(BACKEND_ROOT / ".env")

DATA_DIR = Path(os.environ.get("TRUEBIND_DATA_DIR", str(BACKEND_ROOT / "data")))
# The development database. Deliberately NOT data/truebind.db: that name was
# used by earlier builds and may hold a large legacy database that must never
# be migrated or overwritten by this version.
DEFAULT_DEV_DB_NAME = "truebind-mvp.db"


def _bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    return default if v is None else v.strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


ENV = os.environ.get("TRUEBIND_ENV", "development")
IS_PRODUCTION = ENV == "production"


def get_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        # A relative SQLite path is resolved against the backend folder, not
        # the current directory, so every process started from anywhere
        # opens the same file.
        if url.startswith("sqlite:///") and not url.startswith("sqlite:////"):
            rel = url[len("sqlite:///"):]
            if rel and not Path(rel).is_absolute() and not rel.startswith(":memory:"):
                return f"sqlite:///{(BACKEND_ROOT / rel).resolve()}"
        return url
    if IS_PRODUCTION:
        raise RuntimeError("DATABASE_URL must be set in production (PostgreSQL)")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{DATA_DIR / DEFAULT_DEV_DB_NAME}"


def describe_database_url(url: str | None = None) -> str:
    """Safe for logs/UI: no credentials."""
    url = url or get_database_url()
    if url.startswith("sqlite"):
        return url
    scheme, _, rest = url.partition("://")
    return f"{scheme}://***@{rest.split('@', 1)[-1]}"


def get_cors_origins() -> list[str]:
    raw = os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    if "*" in origins:
        raise RuntimeError("CORS_ORIGINS='*' is not allowed: the API uses credentialed cookies")
    return origins


STORAGE_DIR = Path(os.environ.get("TRUEBIND_STORAGE_DIR", str(DATA_DIR / "objects")))
COOKIE_SECURE = _bool("COOKIE_SECURE", IS_PRODUCTION)
SESSION_TTL_HOURS = _int("SESSION_TTL_HOURS", 12)
ALLOW_SIGNUP = _bool("ALLOW_SIGNUP", not IS_PRODUCTION)
MAX_UPLOAD_BYTES = _int("MAX_UPLOAD_MB", 50) * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = _int("MAX_UNCOMPRESSED_MB", 800) * 1024 * 1024
MAX_COMPRESSION_RATIO = _int("MAX_COMPRESSION_RATIO", 150)
MAX_SHEETS = _int("MAX_SHEETS", 200)
MAX_ROWS = _int("MAX_ROWS", 1_000_000)
MAX_CELLS = _int("MAX_CELLS", 60_000_000)
JOB_TIMEOUT_S = _int("JOB_TIMEOUT_S", 1800)
JOB_MEMORY_MB = _int("JOB_MEMORY_MB", 4096)
JOB_LEASE_S = _int("JOB_LEASE_S", 60)
MAX_CONCURRENT_JOBS_PER_TENANT = _int("MAX_CONCURRENT_JOBS_PER_TENANT", 3)
AI_MAX_CALLS_PER_REPORT = _int("AI_MAX_CALLS_PER_REPORT", 50)
# Development: the API process also runs the job worker loop (each job still
# runs in its own isolated child process), so an upload can never sit queued
# because nobody started a worker. Production: off -- run `python -m app.worker`
# as separate, independently scaled processes.
EMBEDDED_WORKER = _bool("TRUEBIND_EMBEDDED_WORKER", not IS_PRODUCTION)
# A worker is considered alive if it checked in within this many seconds.
WORKER_STALE_S = _int("WORKER_STALE_S", 20)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")  # server-side only; never sent to clients or logged

# Outbound e-mail (deliveries). Unset SMTP_HOST = e-mail delivery is shown as
# "not configured" and nothing is sent.
SMTP_HOST = os.environ.get("SMTP_HOST") or None
SMTP_PORT = _int("SMTP_PORT", 587)
SMTP_USER = os.environ.get("SMTP_USER") or None
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD") or None  # server-side only; never returned or logged
SMTP_FROM = os.environ.get("SMTP_FROM") or "truebind@localhost"
SMTP_STARTTLS = _bool("SMTP_STARTTLS", True)
MAX_EMAIL_ATTACHMENT_BYTES = _int("MAX_EMAIL_ATTACHMENT_MB", 10) * 1024 * 1024
