"""Outbound deliveries: every output Truebind produces for someone --
a downloaded export today; e-mail (when SMTP is configured) and, later,
SFTP/webhook destinations. One row per attempt, with its outcome, so the
Exports page shows what was sent where, when, and whether it arrived."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ._util import created_at_col, uuid_pk

DELIVERY_KINDS = ("claims_csv", "exceptions_csv", "audit_csv")
DELIVERY_CHANNELS = ("download", "email")
DELIVERY_STATUSES = ("DELIVERED", "FAILED", "NOT_CONFIGURED")


class Delivery(Base):
    __tablename__ = "deliveries"

    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    channel: Mapped[str] = mapped_column(String(16))
    destination: Mapped[str | None] = mapped_column(String(320), nullable=True)
    file_name: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16))
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)  # customer-safe
    created_by: Mapped[str | None] = mapped_column(String(320), nullable=True)
    created_at: Mapped[datetime] = created_at_col()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
