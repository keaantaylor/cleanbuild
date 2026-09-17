"""Environment-driven settings. No hardcoded secrets/URLs -- everything
here has a sane local-dev default and is overridden via env vars in
docker-compose/production, same convention as bordereaux/db/session.py."""

from __future__ import annotations

import os
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_ROOT / "data"


def get_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{DATA_DIR / 'truebind.db'}"


def get_cors_origins() -> list[str]:
    raw = os.environ.get("CORS_ORIGINS", "http://localhost:3000")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


UPLOAD_DIR = DATA_DIR / "uploads"
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
