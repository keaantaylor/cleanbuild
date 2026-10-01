"""P1.1 -- typed settings (pydantic-settings).

Acceptance:
- every setting is typed and read from the environment; defaults match the
  pre-P1 behaviour;
- production refuses unsafe or incomplete configuration at startup;
- malformed values fail loudly instead of silently falling back;
- .env.example documents every setting (and contains no values for secrets).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from app.settings import Settings
from pydantic import ValidationError

BACKEND = Path(__file__).resolve().parents[1]
PROD_OK = {
    "TRUEBIND_ENV": "production",
    "DATABASE_URL": "postgresql://u:p@db.internal:5432/truebind",
    "SECRET_KEY": "x" * 48,
}


def _settings(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    for name in list(Settings.model_fields):
        monkeypatch.delenv(Settings.env_name(name), raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return Settings()


def test_defaults_match_pre_p1_behaviour(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(monkeypatch)
    assert s.env == "development" and not s.is_production
    assert s.session_ttl_hours == 12
    assert s.max_upload_mb == 50 and s.max_upload_bytes == 50 * 1024 * 1024
    assert s.max_uncompressed_mb == 800 and s.max_compression_ratio == 150
    assert (s.max_sheets, s.max_rows, s.max_cells) == (200, 1_000_000, 60_000_000)
    assert (s.job_timeout_s, s.job_memory_mb, s.job_lease_s) == (600, 4096, 60)
    assert s.max_concurrent_jobs_per_tenant == 3
    assert (s.ai_max_calls_per_report, s.ai_time_budget_s) == (50, 30)
    assert s.embedded_worker is True and s.allow_signup is True and s.cookie_secure is False
    assert s.smtp_port == 587 and s.smtp_starttls is True and s.smtp_from == "truebind@localhost"
    assert s.cors_origin_list == ["http://localhost:3000", "http://127.0.0.1:3000"]


def test_production_defaults_are_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(monkeypatch, **PROD_OK)
    assert s.is_production
    assert s.cookie_secure is True
    assert s.allow_signup is False
    assert s.embedded_worker is False
    assert s.database_url_resolved.startswith("postgresql+psycopg://")


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"DATABASE_URL": ""}, "DATABASE_URL"),
        ({"DATABASE_URL": "sqlite:///data/x.db"}, "PostgreSQL"),
        ({"SECRET_KEY": ""}, "SECRET_KEY"),
        ({"SECRET_KEY": "short"}, "SECRET_KEY"),
        ({"COOKIE_SECURE": "false"}, "COOKIE_SECURE"),
        ({"CORS_ORIGINS": "*"}, "CORS_ORIGINS"),
    ],
)
def test_production_rejects_unsafe_configuration(
    monkeypatch: pytest.MonkeyPatch, override: dict[str, str], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        _settings(monkeypatch, **{**PROD_OK, **override})


def test_malformed_values_fail_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError, match=r"session_ttl_hours|SESSION_TTL_HOURS"):
        _settings(monkeypatch, SESSION_TTL_HOURS="twelve")


def test_wildcard_cors_rejected_everywhere(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        _settings(monkeypatch, CORS_ORIGINS="http://localhost:3000,*")


def test_secrets_are_not_shown_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(monkeypatch, **PROD_OK, SMTP_PASSWORD="smtp-secret-value", SENTRY_DSN="https://k@o.ingest/1")
    text = repr(s) + str(s.model_dump())
    for secret in ("x" * 48, "smtp-secret-value", "k@o.ingest"):
        assert secret not in text


def test_env_example_documents_every_setting() -> None:
    example = (BACKEND / ".env.example").read_text(encoding="utf-8")
    documented = set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", example, flags=re.MULTILINE))
    expected = {Settings.env_name(name) for name in Settings.model_fields}
    missing = expected - documented
    assert not missing, f".env.example does not document: {sorted(missing)}"
    for line in example.splitlines():
        m = re.match(r"^([A-Z][A-Z0-9_]+)=(.*)$", line)
        if m and Settings.is_secret(m.group(1)):
            assert m.group(2) == "", f"{m.group(1)} must not have a value in .env.example"
