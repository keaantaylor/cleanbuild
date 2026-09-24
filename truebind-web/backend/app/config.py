"""Environment-driven settings. No secrets in code: everything sensitive
comes from the environment (see .env.example, which contains no values)."""

from __future__ import annotations

import os
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("TRUEBIND_DATA_DIR", str(BACKEND_ROOT / "data")))


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
        return url
    if IS_PRODUCTION:
        raise RuntimeError("DATABASE_URL must be set in production (PostgreSQL)")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{DATA_DIR / 'truebind.db'}"


def get_cors_origins() -> list[str]:
    raw = os.environ.get("CORS_ORIGINS", "http://localhost:3000")
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
EMBEDDED_WORKER = _bool("TRUEBIND_EMBEDDED_WORKER", False)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")  # server-side only; never sent to clients or logged
