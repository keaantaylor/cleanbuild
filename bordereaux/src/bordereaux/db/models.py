"""Persistence layer (Truebind Phase 1): reports, leakage flags, the
append-only audit log, templates, obligations and alerts all need to
survive between sessions and be queryable -- this is the real database
schema that replaces the original MVP's stateless per-upload processing.

Every status/category field here is a plain string, not a DB-level enum:
Section 0 of the redevelopment prompt is explicit that thresholds and
business rules must live in config a compliance officer or ops lead can
tune, not be locked into a schema that needs a migration to change a
label.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Base(DeclarativeBase):
    pass


class Report(Base):
    """One persisted run of the pipeline against one uploaded workbook."""

    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source_name: Mapped[str] = mapped_column(String(500))
    uploaded_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    uploaded_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    sheets_total: Mapped[int] = mapped_column(default=0)
    sheets_processed: Mapped[int] = mapped_column(default=0)
    rows_total: Mapped[int] = mapped_column(default=0)
    rows_assessed: Mapped[int] = mapped_column(default=0)

    grade: Mapped[int] = mapped_column(default=0)
    composite_score: Mapped[float] = mapped_column(default=0.0)
    score_reliable: Mapped[bool] = mapped_column(default=True)

    # Full health-report snapshot (field completeness, exception/duplicate
    # counts, coverage detail) as JSON text -- queried in bulk by the
    # dashboards, not filtered column-by-column, so a flexible blob here
    # avoids a schema migration every time the report gains a new metric.
    summary_json: Mapped[str] = mapped_column(Text, default="{}")

    segregated_export_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    health_report_xlsx_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    health_report_pdf_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    leakage_flags: Mapped[list["LeakageFlag"]] = relationship(back_populates="report")
    exception_records: Mapped[list["ExceptionRecord"]] = relationship(back_populates="report")
    audit_entries: Mapped[list["AuditLogEntry"]] = relationship(back_populates="report")
    obligations: Mapped[list["Obligation"]] = relationship(back_populates="report")
    alerts: Mapped[list["Alert"]] = relationship(back_populates="report")


LEAKAGE_CONFIDENCE_TIERS = ("CERTAIN", "PROBABLE", "POSSIBLE")
LEAKAGE_STATUSES = ("open", "confirmed", "dismissed")


class LeakageFlag(Base):
    """A probable duplicate *payment*, not just a duplicate claim record
    -- see leakage.py. Never a single duplicate/not-duplicate boolean:
    `confidence` is always one of LEAKAGE_CONFIDENCE_TIERS."""

    __tablename__ = "leakage_flags"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id"))
    report: Mapped["Report"] = relationship(back_populates="leakage_flags")

    confidence: Mapped[str] = mapped_column(String(20))  # LEAKAGE_CONFIDENCE_TIERS

    sheet_a: Mapped[str] = mapped_column(String(200))
    row_a: Mapped[int] = mapped_column()
    claim_ref_a: Mapped[str | None] = mapped_column(String(200), nullable=True)
    insured_name_a: Mapped[str | None] = mapped_column(String(500), nullable=True)
    amount_a: Mapped[float | None] = mapped_column(nullable=True)

    sheet_b: Mapped[str] = mapped_column(String(200))
    row_b: Mapped[int] = mapped_column()
    claim_ref_b: Mapped[str | None] = mapped_column(String(200), nullable=True)
    insured_name_b: Mapped[str | None] = mapped_column(String(500), nullable=True)
    amount_b: Mapped[float | None] = mapped_column(nullable=True)

    matched_fields: Mapped[str] = mapped_column(Text, default="[]")  # JSON list of str
    amount_exposure: Mapped[float] = mapped_column(default=0.0)
    detail: Mapped[str] = mapped_column(Text, default="")

    status: Mapped[str] = mapped_column(String(20), default="open")  # LEAKAGE_STATUSES
    reviewer: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reviewed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


EXCEPTION_STATUSES = ("open", "resolved", "dismissed")


class ExceptionRecord(Base):
    """A persisted copy of one validation.py exception row. Needed so the
    governance review pack (2.2) can be generated on demand for a past
    report/period, not only immediately after upload -- the in-memory
    ValidationResult from that run doesn't survive the session. `status`
    defaults to "open" and stays there until a resolution workflow exists;
    the pack reports that honestly rather than fabricating a resolved
    state."""

    __tablename__ = "exception_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id"))
    report: Mapped["Report"] = relationship(back_populates="exception_records")

    sheet: Mapped[str | None] = mapped_column(String(200), nullable=True)
    row: Mapped[int | None] = mapped_column(nullable=True)
    claim_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    rule: Mapped[str] = mapped_column(String(100))
    detail: Mapped[str] = mapped_column(Text)

    status: Mapped[str] = mapped_column(String(20), default="open")  # EXCEPTION_STATUSES
    resolved_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    resolved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AuditLogEntry(Base):
    """Append-only. Never updated or deleted after creation -- code that
    writes here must never also expose an update/delete path."""

    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    report_id: Mapped[str | None] = mapped_column(ForeignKey("reports.id"), nullable=True)
    report: Mapped["Report | None"] = relationship(back_populates="audit_entries")

    actor: Mapped[str] = mapped_column(String(200))
    action_type: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    before_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


TEMPLATE_TYPES = ("STANDARD", "CUSTOM")


class Template(Base):
    """A saved sender mapping (CUSTOM) or a built-in standard like Lloyd's
    v5.2 (STANDARD, non-deletable). Matched against incoming sheet headers
    as a third mapping signal alongside alias/AI (see mapping.py)."""

    __tablename__ = "templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200))
    template_type: Mapped[str] = mapped_column(String(20))  # TEMPLATE_TYPES
    created_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    is_deletable: Mapped[bool] = mapped_column(default=True)
    # Free-form JSON for standard-specific metadata that doesn't fit the
    # header->field_code mapping rows below (e.g. Lloyd's real 12-value
    # claim status enum). See lloyds_template.py.
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")

    field_mappings: Mapped[list["TemplateFieldMapping"]] = relationship(
        back_populates="template", cascade="all, delete-orphan"
    )


class TemplateFieldMapping(Base):
    __tablename__ = "template_field_mappings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    template_id: Mapped[str] = mapped_column(ForeignKey("templates.id"))
    template: Mapped["Template"] = relationship(back_populates="field_mappings")

    header_text: Mapped[str] = mapped_column(String(300))
    field_code: Mapped[str] = mapped_column(String(20))
    # True for a field the standard marks mandatory (Lloyd's template) or
    # the user marked required when saving a custom template. Independent
    # of schema.py's own requirement tag -- see lloyds_template.py's notes
    # on why the two must never be conflated.
    mandatory: Mapped[bool] = mapped_column(default=False)


OBLIGATION_STATUSES = ("open", "met", "missed", "dismissed")


class Obligation(Base):
    """A lightweight action item with a deadline, linkable to any entity
    (a leakage flag, an exception, later a sanctions match) -- sized to
    exactly what the leakage/audit modules need, not a workflow engine."""

    __tablename__ = "obligations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    report_id: Mapped[str | None] = mapped_column(ForeignKey("reports.id"), nullable=True)
    report: Mapped["Report | None"] = relationship(back_populates="obligations")

    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(100))
    due_date: Mapped[dt.date | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")  # OBLIGATION_STATUSES

    linked_entity_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    linked_entity_id: Mapped[str | None] = mapped_column(String(200), nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    resolved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(200), nullable=True)


ALERT_STATUSES = ("open", "acknowledged", "dismissed")


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    report_id: Mapped[str | None] = mapped_column(ForeignKey("reports.id"), nullable=True)
    report: Mapped["Report | None"] = relationship(back_populates="alerts")

    alert_type: Mapped[str] = mapped_column(String(100))
    severity: Mapped[str] = mapped_column(String(20))  # e.g. "info" | "warning" | "critical"
    message: Mapped[str] = mapped_column(Text)

    entity_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    obligation_id: Mapped[str | None] = mapped_column(ForeignKey("obligations.id"), nullable=True)

    status: Mapped[str] = mapped_column(String(20), default="open")  # ALERT_STATUSES
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
