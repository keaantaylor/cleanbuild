"""Append-only, tamper-evident audit log.

Written only through services.audit_service.log_action(). Each entry stores
entry_hash = SHA-256(prev_hash || canonical JSON of the entry), chained per
tenant, so any later modification or deletion of a row breaks the chain and
is detectable (services.audit_service.verify_chain). On PostgreSQL a trigger
additionally rejects UPDATE and DELETE on this table (migration
c1a0b2d3e4f5). report_id is deliberately NOT a foreign key: audit history
must outlive the report it describes (e.g. REPORT_DELETED)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ._util import created_at_col, uuid_pk

ACTION_TYPES = (
    "REPORT_UPLOADED", "UPLOAD_REJECTED", "JOB_QUEUED", "JOB_STARTED", "JOB_SUCCEEDED", "JOB_FAILED",
    "JOB_CANCELLED", "STATUS_CHANGED", "MAPPING_CONFIRMED", "MAPPING_OVERRIDDEN", "OBLIGATION_STATUS_CHANGED",
    "LEAKAGE_FLAG_REVIEWED", "EXCEPTION_STATUS_CHANGED", "EXPORT_GENERATED", "TEMPLATE_CREATED",
    "ALERT_ACKNOWLEDGED", "AI_SUMMARY_GENERATED", "AI_MAPPING_SUGGESTED", "REPORT_DELETED",
    "LOGIN_SUCCEEDED", "LOGIN_FAILED", "LOGOUT", "REPORT_EXPIRED", "ACCOUNT_CREATED", "JOB_CANCEL_REQUESTED", "SOURCE_COLUMN_UNMAPPED",
)
ENTITY_TYPES = ("MAPPING", "EXCEPTION", "OBLIGATION", "REPORT", "LEAKAGE_FLAG", "TEMPLATE", "ALERT",
                "EXCEPTION_SUMMARY", "JOB", "SESSION", "USER")


class AuditLogEntry(Base):
    __tablename__ = "audit_log"
    __table_args__ = (UniqueConstraint("tenant_id", "seq", name="uq_audit_log_tenant_seq"),)

    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer, default=0)  # per-tenant sequence, gap-free
    report_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    action_type: Mapped[str] = mapped_column(String(32))
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str] = mapped_column(String(36))
    actor: Mapped[str] = mapped_column(String(255))  # display label, derived server-side from identity
    actor_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    before_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    prev_hash: Mapped[str] = mapped_column(String(64))
    entry_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = created_at_col()
