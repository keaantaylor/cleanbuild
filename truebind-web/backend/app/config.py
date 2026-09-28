"""Legacy settings view. The source of truth is ``app.settings.Settings``
(typed, validated, documented in .env.example); this module keeps the
module-level constants the pre-P1 code imports. New code should call
``get_settings()`` instead of importing from here."""

from __future__ import annotations

import os

from pydantic import ValidationError

from .settings import BACKEND_ROOT, DEFAULT_DEV_DB_NAME, Settings, get_settings, load_dotenv, resolve_database_url

if os.environ.get("TRUEBIND_ENV", "development") != "production" and not os.environ.get("TRUEBIND_NO_DOTENV"):
    load_dotenv()

_s = get_settings()

__all__ = ["BACKEND_ROOT", "DEFAULT_DEV_DB_NAME"]

DATA_DIR = _s.data_dir
ENV = _s.env
IS_PRODUCTION = _s.is_production


def _fresh() -> Settings:
    """Re-read the environment (tests and tools change it at runtime)."""
    try:
        return Settings()
    except ValidationError as exc:
        raise RuntimeError(str(exc)) from exc


def get_database_url() -> str:
    s = _fresh()
    return resolve_database_url(s.database_url, s.is_production, s.data_dir)


def describe_database_url(url: str | None = None) -> str:
    """Safe for logs/UI: no credentials."""
    url = url or get_database_url()
    if url.startswith("sqlite"):
        return url
    scheme, _, rest = url.partition("://")
    return f"{scheme}://***@{rest.split('@', 1)[-1]}"


def get_cors_origins() -> list[str]:
    return _fresh().cors_origin_list


STORAGE_DIR = _s.storage_path
COOKIE_SECURE = bool(_s.cookie_secure)
SESSION_TTL_HOURS = _s.session_ttl_hours
ALLOW_SIGNUP = bool(_s.allow_signup)
MAX_UPLOAD_BYTES = _s.max_upload_bytes
MAX_UNCOMPRESSED_BYTES = _s.max_uncompressed_mb * 1024 * 1024
MAX_COMPRESSION_RATIO = _s.max_compression_ratio
MAX_SHEETS = _s.max_sheets
MAX_ROWS = _s.max_rows
MAX_CELLS = _s.max_cells
JOB_TIMEOUT_S = _s.job_timeout_s
JOB_MEMORY_MB = _s.job_memory_mb
JOB_LEASE_S = _s.job_lease_s
JOB_MAX_ATTEMPTS = _s.job_max_attempts
REDIS_URL = _s.redis_url  # optional: job wake-ups (app/services/job_signal.py)
MAX_CONCURRENT_JOBS_PER_TENANT = _s.max_concurrent_jobs_per_tenant
AI_MAX_CALLS_PER_REPORT = _s.ai_max_calls_per_report
# Wall-clock budget for the whole AI-mapping stage of one report; after it,
# remaining sheets use deterministic (alias) mapping only.
AI_TIME_BUDGET_S = _s.ai_time_budget_s
EMBEDDED_WORKER = bool(_s.embedded_worker)
WORKER_STALE_S = _s.worker_stale_s
ANTHROPIC_API_KEY = _s.anthropic_api_key.get_secret_value() or None  # server-side only; never sent or logged

# Outbound e-mail. Unset SMTP_HOST = delivery shows "not configured".
SMTP_HOST = _s.smtp_host or None
SMTP_PORT = _s.smtp_port
SMTP_USER = _s.smtp_user or None
SMTP_PASSWORD = _s.smtp_password.get_secret_value() or None  # server-side only; never returned or logged
SMTP_FROM = _s.smtp_from
SMTP_STARTTLS = _s.smtp_starttls
MAX_EMAIL_ATTACHMENT_BYTES = _s.max_email_attachment_mb * 1024 * 1024
