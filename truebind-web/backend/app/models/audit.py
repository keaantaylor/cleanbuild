"""Append-only audit log. Every mutation route calls
services.audit_service.log_action(...) -- see that module's docstring for
the "never write directly" rule."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ._util import created_at_col, uuid_pk

ACTION_TYPES = (
    "MAPPING_CONFIRMED",
    "MAPPING_OVERRIDDEN",
    "OBLIGATION_STATUS_CHANGED",
    "LEAKAGE_FLAG_REVIEWED",
    "EXCEPTION_STATUS_CHANGED",
    "EXPORT_GENERATED",
    "TEMPLATE_CREATED",
    "ALERT_ACKNOWLEDGED",
)
ENTITY_TYPES = ("MAPPING", "EXCEPTION", "OBLIGATION", "REPORT", "LEAKAGE_FLAG", "TEMPLATE", "ALERT")


class AuditLogEntry(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = uuid_pk()
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id"), index=True)
    action_type: Mapped[str] = mapped_column(String(32))
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str] = mapped_column(String(36))
    actor: Mapped[str] = mapped_column(String(255))
    before_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = created_at_col()
