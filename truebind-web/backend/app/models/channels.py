"""P2 channels: inbound e-mail address, outbound webhooks and SFTP, FX rates.

- Tenant.inbound_token (identity.py) names the organisation's inbound
  address <token>@<INBOUND_EMAIL_DOMAIN>.
- WebhookEndpoint / WebhookDelivery: signed (Svix-style) event deliveries
  with retries and manual replay; one delivery row per event and endpoint.
- SftpDestination: one partner SFTP per organisation, host key pinned.
- FxRate: ECB euro reference rates (global reference data, not tenant data).
Secrets (webhook signing secret, SFTP password/key) are encrypted with a
purpose-bound key (security/crypto.py) and never returned by the API.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ._util import created_at_col, uuid_pk

WEBHOOK_EVENTS = ("report.completed", "report.failed", "report.waiting_for_review")
DELIVERY_STATES = ("PENDING", "DELIVERED", "FAILED", "EXHAUSTED")


class WebhookEndpoint(Base):
    __tablename__ = "webhook_endpoints"

    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    url: Mapped[str] = mapped_column(String(2000))
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    events: Mapped[list[str]] = mapped_column(JSON, default=list)
    secret_enc: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = created_at_col()


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    endpoint_id: Mapped[str] = mapped_column(ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(64))
    message_id: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = created_at_col()
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SftpDestination(Base):
    __tablename__ = "sftp_destinations"

    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), unique=True, index=True)
    host: Mapped[str] = mapped_column(String(253))
    port: Mapped[int] = mapped_column(Integer, default=22)
    username: Mapped[str] = mapped_column(String(200))
    password_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    private_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    host_key_fingerprint: Mapped[str] = mapped_column(String(200))
    remote_dir: Mapped[str] = mapped_column(String(500), default="/")
    auto_deliver: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = created_at_col()


class FxRate(Base):
    """Units of `currency` per 1 EUR on `rate_date` (ECB reference rate)."""

    __tablename__ = "fx_rates"

    rate_date: Mapped[date] = mapped_column(Date, primary_key=True)
    currency: Mapped[str] = mapped_column(String(3), primary_key=True)
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    source: Mapped[str] = mapped_column(String(16), default="ECB")
