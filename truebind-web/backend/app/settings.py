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
from typing import Any, Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DEV_DB_NAME = "truebind-mvp.db"  # never data/truebind.db: a legacy DB may live there
AZURE_EU_UK_REGIONS = frozenset(
    {
        "uksouth",
        "ukwest",
        "westeurope",
        "northeurope",
        "swedencentral",
        "francecentral",
        "germanywestcentral",
        "switzerlandnorth",
        "norwayeast",
        "polandcentral",
        "italynorth",
        "spaincentral",
    }
)
_MIN_SECRET_KEY_LEN = 32
# Check modules a billing plan may include (app/checks REGISTRY).
BILLING_MODULES = frozenset({"binder", "leakage", "sanctions"})


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
    # Where uploaded originals live. Unset: "db" in production (durable on hosts
    # whose local disk is wiped on restart), "local" in development and tests.
    storage_backend: Literal["local", "s3", "db"] | None = Field(default=None, validation_alias="STORAGE_BACKEND")
    storage_dir: Path | None = Field(default=None, validation_alias="TRUEBIND_STORAGE_DIR")
    s3_bucket: str = Field(default="", validation_alias="S3_BUCKET")
    s3_endpoint_url: str = Field(default="", validation_alias="S3_ENDPOINT_URL")
    s3_region: str = Field(default="eu-west-2", validation_alias="S3_REGION")
    s3_access_key_id: str = Field(default="", validation_alias="S3_ACCESS_KEY_ID")
    s3_secret_access_key: SecretStr = Field(default=SecretStr(""), validation_alias="S3_SECRET_ACCESS_KEY")
    s3_sse: Literal["AES256", "aws:kms", "none"] = Field(default="AES256", validation_alias="S3_SSE")

    # ---- jobs / workers
    # A job that runs longer than this is stopped and marked failed with a clear message (10 minutes).
    job_timeout_s: int = Field(default=600, ge=10, validation_alias="JOB_TIMEOUT_S")
    job_memory_mb: int = Field(default=4096, ge=256, validation_alias="JOB_MEMORY_MB")
    job_lease_s: int = Field(default=60, ge=5, validation_alias="JOB_LEASE_S")
    job_max_attempts: int = Field(default=2, ge=1, le=10, validation_alias="JOB_MAX_ATTEMPTS")
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

    # ---- Website enquiries (demo / Health Check / contact / updates forms)
    # Who may read them in the app (comma-separated sign-in emails), and where
    # a notification is emailed when one arrives (needs SMTP_* as well).
    leads_admin_emails: str = Field(default="", validation_alias="LEADS_ADMIN_EMAILS")
    leads_notify_email: str = Field(default="", validation_alias="LEADS_NOTIFY_EMAIL")
    # Files sent with a Health Check request are deleted after this many days.
    lead_file_retention_days: int = Field(default=30, ge=1, le=365, validation_alias="LEAD_FILE_RETENTION_DAYS")
    smtp_starttls: bool = Field(default=True, validation_alias="SMTP_STARTTLS")
    max_email_attachment_mb: int = Field(default=10, ge=1, validation_alias="MAX_EMAIL_ATTACHMENT_MB")

    # ---- AI provider (P2): EU/UK-hosted, zero retention, behind app/ai/providers.py
    ai_provider: Literal["none", "fake", "azure_openai", "bedrock"] = Field(
        default="none", validation_alias="AI_PROVIDER"
    )
    azure_openai_endpoint: str = Field(default="", validation_alias="AZURE_OPENAI_ENDPOINT")
    azure_openai_api_key: SecretStr = Field(default=SecretStr(""), validation_alias="AZURE_OPENAI_API_KEY")
    azure_openai_deployment: str = Field(default="", validation_alias="AZURE_OPENAI_DEPLOYMENT")
    azure_openai_api_version: str = Field(default="2024-10-21", validation_alias="AZURE_OPENAI_API_VERSION")
    azure_openai_region: str = Field(default="", validation_alias="AZURE_OPENAI_REGION")
    bedrock_region: str = Field(default="eu-central-1", validation_alias="BEDROCK_REGION")
    bedrock_model_id: str = Field(default="", validation_alias="BEDROCK_MODEL_ID")

    # ---- inbound e-mail (P2)
    inbound_email_domain: str = Field(default="", validation_alias="INBOUND_EMAIL_DOMAIN")
    inbound_webhook_secret: SecretStr = Field(default=SecretStr(""), validation_alias="INBOUND_WEBHOOK_SECRET")
    ses_sns_topic_arns: str = Field(default="", validation_alias="SES_SNS_TOPIC_ARNS")

    # ---- outbound webhooks (P2)
    webhook_max_attempts: int = Field(default=6, ge=1, le=20, validation_alias="WEBHOOK_MAX_ATTEMPTS")
    webhook_allow_private_targets: bool = Field(default=False, validation_alias="WEBHOOK_ALLOW_PRIVATE_TARGETS")

    # ---- FX reference rates (P2)
    fx_auto_refresh: bool = Field(default=False, validation_alias="FX_AUTO_REFRESH")
    ecb_rates_url: str = Field(
        default="https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml", validation_alias="ECB_RATES_URL"
    )

    # ---- billing (P9): plans from configuration, prices in Stripe
    billing_enabled: bool = Field(default=False, validation_alias="BILLING_ENABLED")
    billing_plans: dict[str, dict[str, Any]] = Field(default_factory=dict, validation_alias="BILLING_PLANS")
    billing_default_plan: str | None = Field(default=None, validation_alias="BILLING_DEFAULT_PLAN")
    stripe_secret_key: SecretStr = Field(default=SecretStr(""), validation_alias="STRIPE_SECRET_KEY")
    stripe_webhook_secret: SecretStr = Field(default=SecretStr(""), validation_alias="STRIPE_WEBHOOK_SECRET")
    stripe_api_base: str = Field(default="https://api.stripe.com", validation_alias="STRIPE_API_BASE")

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

    def _check_billing(self) -> None:
        if not self.stripe_secret_key.get_secret_value() or not self.stripe_webhook_secret.get_secret_value():
            raise ValueError("BILLING_ENABLED needs STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET")
        if not self.billing_plans:
            raise ValueError(
                "BILLING_ENABLED needs BILLING_PLANS (JSON: name -> modules, monthly_rows, seats, price_id)"
            )
        for name, plan in self.billing_plans.items():
            unknown = set(plan.get("modules") or []) - BILLING_MODULES
            if unknown:
                raise ValueError(f"BILLING_PLANS[{name}] names an unknown module: {', '.join(sorted(unknown))}")
            for key in ("monthly_rows", "seats"):
                v = plan.get(key)
                if v is not None and (not isinstance(v, int) or isinstance(v, bool) or v < 1):
                    raise ValueError(f"BILLING_PLANS[{name}].{key} must be a positive whole number or null")
        if self.billing_default_plan and self.billing_default_plan not in self.billing_plans:
            raise ValueError("BILLING_DEFAULT_PLAN must name one of BILLING_PLANS")

    @model_validator(mode="after")
    def _resolve_and_check(self) -> Settings:
        if self.storage_backend is None:
            self.storage_backend = "db" if self.is_production else "local"
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
        # Non-negotiable 9: AI runs in the EU/UK only.
        if self.ai_provider == "bedrock" and not self.bedrock_region.startswith("eu-"):
            raise ValueError("BEDROCK_REGION must be an EU region (eu-*) for AI_PROVIDER=bedrock")
        if self.ai_provider == "azure_openai" and self.azure_openai_region.lower() not in AZURE_EU_UK_REGIONS:
            raise ValueError(
                "AZURE_OPENAI_REGION must be an EU/UK Azure region for AI_PROVIDER=azure_openai "
                f"({', '.join(sorted(AZURE_EU_UK_REGIONS))})"
            )
        if self.ai_provider == "fake" and self.is_production:
            raise ValueError("AI_PROVIDER=fake is for tests only")
        if self.billing_enabled:
            self._check_billing()
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
