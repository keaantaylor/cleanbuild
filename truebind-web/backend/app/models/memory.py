"""Counterparty memory and the e-mail loop (migration 0023)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ._util import created_at_col, uuid_pk


class ApprovedRule(Base):
    """A reusable correction a person approved after TrueBind observed it
    repeatedly. Never created by the system on its own."""

    __tablename__ = "approved_rules"

    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    sender: Mapped[str | None] = mapped_column(String(200), nullable=True)  # None: every counterparty
    field_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    rule: Mapped[str | None] = mapped_column(String(64), nullable=True)
    match_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    replace_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    observed: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")  # ACTIVE | RETIRED
    applied: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str] = mapped_column(String(320))
    created_at: Mapped[datetime] = created_at_col()


class InfoRequest(Base):
    """One question sent to a sender about one root cause. Replies are matched
    back by the [TB-<number>] reference, never by what the e-mail says."""

    __tablename__ = "info_requests"
    __table_args__ = (UniqueConstraint("tenant_id", "number"),)

    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    root_cause: Mapped[str] = mapped_column(String(300))
    issue_ids: Mapped[list] = mapped_column(JSON)
    to_address: Mapped[str | None] = mapped_column(String(320), nullable=True)
    subject: Mapped[str] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text)
    message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    delivery: Mapped[str] = mapped_column(String(16))  # SENT | NOT_CONFIGURED | NO_ADDRESS | FAILED
    delivery_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(16))  # OPEN | ANSWERED | RESOLVED
    replies: Mapped[list | None] = mapped_column(JSON, nullable=True)
    reply_report_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    resolution: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[str] = mapped_column(String(320))
    created_at: Mapped[datetime] = created_at_col()
