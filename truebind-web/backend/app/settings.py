"""Typed application settings (pydantic-settings).

Every setting comes from the environment (real env vars win over
``backend/.env``, which is read only outside production). Nothing sensitive
has a default; secrets are ``SecretStr`` so they never appear in reprs,
logs or dumps. Production refuses to start with unsafe or incomplete
configuration. ``.env.example`` documents every field (enforced by
tests/test_settings.py).

Legacy modules keep importing constants from ``app.config``, which is now a
thin view over :func:`get_settings`.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DEV_DB_NAME = "truebind-mvp.db"  # never data/truebind.db: a legacy DB may live there
_MIN_SECRET_KEY_LEN = 32


def load_dotenv(path: Path = BACKEND_ROOT / ".env") -> None:
    """Minimal KEY=VALUE reader. Loaded into ``os.environ`` (not just into
    Settings) so the API, the worker, its spawned children and Alembic all
    resolve the same configuration. Real environment variables win."""
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


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore", populate_by_name=False)

    # ---- runtime
    env: Literal["development", "test", "production"] = Field(default="development", validation_alias="TRUEBIND_ENV")
    data_dir: Path = Field(default=BACKEND_ROOT / "data", validation_alias="TRUEBIND_DATA_DIR")
    database_url: str = Field(default="", validation_alias="DATABASE_URL")
    secret_key: SecretStr = Field(default=SecretStr(""), validation_alias="SECRET_KEY")
    public_app_url: str = Field(default="http://localhost:3000", validation_alias="PUBLIC_APP_URL")
    public_api_url: str = Field(default="http://localhost:8000", validation_alias="PUBLIC_API_URL")

    # ---- HTTP / sessions
    cors_origins: str = Field(default="http://localhost:3000,http://127.0.0.1:3000", validation_alias="CORS_ORIGINS")
    cookie_secure: bool | None = Field(default=None, validation_alias="COOKIE_SECURE")
    session_ttl_hours: int = Field(default=12, ge=1, le=24 * 30, validation_alias="SESSION_TTL_HOURS")
    allow_signup: bool | None = Field(default=None, validation_alias="ALLOW_SIGNUP")
    login_lockout_threshold: int = Field(default=5, ge=1, validation_alias="LOGIN_LOCKOUT_THRESHOLD")
    login_lockout_minutes: int = Field(default=15, ge=1, validation_alias="LOGIN_LOCKOUT_MINUTES")

    # ---- uploads
    max_upload_mb: int = Field(default=50, ge=1, validation_alias="MAX_UPLOAD_MB")
    max_uncompressed_mb: int = Field(default=800, ge=1, validation_alias="MAX_UNCOMPRESSED_MB")
    max_compression_ratio: int = Field(default=150, ge=1, validation_alias="MAX_COMPRESSION_RATIO")
    max_sheets: int = Field(default=200, ge=1, validation_alias="MAX_SHEETS")
    max_rows: int = Field(default=1_000_000, ge=1, validation_alias="MAX_ROWS")
    max_cells: int = Field(default=60_000_000, ge=1, validation_alias="MAX_CELLS")

    # ---- storage (original files are write-once; the app has no delete path)
    storage_backend: Literal["local", "s3"] = Field(default="local", validation_alias="STORAGE_BACKEND")
    storage_dir: Path | None = Field(default=None, validation_alias="TRUEBIND_STORAGE_DIR")
    s3_bucket: str = Field(default="", validation_alias="S3_BUCKET")
    s3_endpoint_url: str = Field(default="", validation_alias="S3_ENDPOINT_URL")
    s3_region: str = Field(default="eu-west-2", validation_alias="S3_REGION")
    s3_access_key_id: str = Field(default="", validation_alias="S3_ACCESS_KEY_ID")
    s3_secret_access_key: SecretStr = Field(default=SecretStr(""), validation_alias="S3_SECRET_ACCESS_KEY")
    s3_sse: Literal["AES256", "aws:kms", "none"] = Field(default="AES256", validation_alias="S3_SSE")

    # ---- jobs / workers
    job_timeout_s: int = Field(default=1800, ge=10, validation_alias="JOB_TIMEOUT_S")
    job_memory_mb: int = Field(default=4096, ge=256, validation_alias="JOB_MEMORY_MB")
    job_lease_s: int = Field(default=60, ge=5, validation_alias="JOB_LEASE_S")
    job_max_attempts: int = Field(default=3, ge=1, le=10, validation_alias="JOB_MAX_ATTEMPTS")
    max_concurrent_jobs_per_tenant: int = Field(default=3, ge=1, validation_alias="MAX_CONCURRENT_JOBS_PER_TENANT")
    embedded_worker: bool | None = Field(default=None, validation_alias="TRUEBIND_EMBEDDED_WORKER")
    worker_stale_s: int = Field(default=20, ge=5, validation_alias="WORKER_STALE_S")
    redis_url: str = Field(default="", validation_alias="REDIS_URL")

    # ---- AI-assisted mapping
    ai_max_calls_per_report: int = Field(default=50, ge=0, validation_alias="AI_MAX_CALLS_PER_REPORT")
    ai_time_budget_s: int = Field(default=30, ge=1, validation_alias="AI_TIME_BUDGET_S")
    anthropic_api_key: SecretStr = Field(default=SecretStr(""), validation_alias="ANTHROPIC_API_KEY")

    # ---- outbound e-mail
    smtp_host: str = Field(default="", validation_alias="SMTP_HOST")
    smtp_port: int = Field(default=587, ge=1, le=65535, validation_alias="SMTP_PORT")
    smtp_user: str = Field(default="", validation_alias="SMTP_USER")
    smtp_password: SecretStr = Field(default=SecretStr(""), validation_alias="SMTP_PASSWORD")
    smtp_from: str = Field(default="truebind@localhost", validation_alias="SMTP_FROM")
    smtp_starttls: bool = Field(default=True, validation_alias="SMTP_STARTTLS")
    max_email_attachment_mb: int = Field(default=10, ge=1, validation_alias="MAX_EMAIL_ATTACHMENT_MB")

    # ---- observability
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO", validation_alias="LOG_LEVEL")
    log_json: bool | None = Field(default=None, validation_alias="LOG_JSON")
    sentry_dsn: SecretStr = Field(default=SecretStr(""), validation_alias="SENTRY_DSN")
    sentry_traces_sample_rate: float = Field(default=0.0, ge=0.0, le=1.0, validation_alias="SENTRY_TRACES_SAMPLE_RATE")

    # ---- auth: TOTP
    totp_issuer: str = Field(default="TrueBind", validation_alias="TOTP_ISSUER")

    # ------------------------------------------------------------------ helpers

    @classmethod
    def env_name(cls, field: str) -> str:
        alias = cls.model_fields[field].validation_alias
        return alias if isinstance(alias, str) else field.upper()

    @classmethod
    def is_secret(cls, env_name: str) -> bool:
        for name, info in cls.model_fields.items():
            if cls.env_name(name) == env_name:
                return info.annotation is SecretStr
        return False

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def database_url_resolved(self) -> str:
        return resolve_database_url(self.database_url, self.is_production, self.data_dir)

    @property
    def storage_path(self) -> Path:
        return self.storage_dir or (self.data_dir / "objects")

    @model_validator(mode="after")
    def _resolve_and_check(self) -> Settings:
        if self.cookie_secure is None:
            self.cookie_secure = self.is_production
        if self.allow_signup is None:
            self.allow_signup = not self.is_production
        if self.embedded_worker is None:
            self.embedded_worker = not self.is_production
        if self.log_json is None:
            self.log_json = self.is_production
        if "*" in self.cors_origin_list:
            raise ValueError("CORS_ORIGINS='*' is not allowed: the API uses credentialed cookies")
        if self.storage_backend == "s3" and not self.s3_bucket:
            raise ValueError("S3_BUCKET is required when STORAGE_BACKEND=s3")
        if self.is_production:
            problems = []
            if not self.database_url:
                problems.append("DATABASE_URL must be set in production (PostgreSQL)")
            elif not self.database_url.startswith(("postgres://", "postgresql://", "postgresql+psycopg://")):
                problems.append("DATABASE_URL must be PostgreSQL in production")
            if len(self.secret_key.get_secret_value()) < _MIN_SECRET_KEY_LEN:
                problems.append(f"SECRET_KEY must be set to at least {_MIN_SECRET_KEY_LEN} random characters")
            if not self.cookie_secure:
                problems.append("COOKIE_SECURE cannot be disabled in production")
            if problems:
                raise ValueError("; ".join(problems))
        return self


def resolve_database_url(url: str, is_production: bool, data_dir: Path) -> str:
    if url:
        # A relative SQLite path resolves against backend/, so every process
        # started from anywhere opens the same file.
        if url.startswith("sqlite:///") and not url.startswith("sqlite:////"):
            rel = url[len("sqlite:///") :]
            if rel and not Path(rel).is_absolute() and not rel.startswith(":memory:"):
                return f"sqlite:///{(BACKEND_ROOT / rel).resolve()}"
        # Hosted Postgres hands out postgres:// or postgresql://; name the driver.
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix) :]
        return url
    if is_production:
        raise RuntimeError("DATABASE_URL must be set in production (PostgreSQL)")
    data_dir.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{data_dir / DEFAULT_DEV_DB_NAME}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings, read once at first use."""
    return Settings()
