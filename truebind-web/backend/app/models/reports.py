"""Report / Sheet / Mapping / ClaimRow / ValidationResult / ExcludedRow.

Every row carries tenant_id. On PostgreSQL, Row Level Security policies
(migration 0002_pg_security) enforce tenant isolation in the database itself;
application queries are additionally scoped by tenant (defence in depth).

Report lifecycle (see app/services/report_state.py for legal transitions):
UPLOADED -> QUEUED -> INGESTING -> WAITING_FOR_REVIEW -> QUEUED -> PROCESSING
-> COMPLETE, with FAILED / CANCELLED / EXPIRED as terminal exits."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy import event, select
from sqlalchemy.orm import ORMExecuteState, Session, with_loader_criteria
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from ._util import created_at_col, uuid_pk
from .money import Money

REPORT_STATUSES = ("UPLOADED", "QUEUED", "INGESTING", "WAITING_FOR_REVIEW", "PROCESSING",
                   "COMPLETE", "FAILED", "CANCELLED", "EXPIRED")
SHEET_STATUSES = ("PENDING_CONFIRMATION", "CONFIRMED", "SKIPPED")
MAPPING_STATES = ("MAPPED_BY_ALIAS", "MAPPED_BY_AI", "UNMAPPED", "MANUAL")
REVIEW_STATES = ("HIGH_CONFIDENCE", "REVIEW", "AMBIGUOUS", "UNMAPPED", "CONFIRMED")
VALIDATION_CHECK_TYPES = ("MANDATORY_FIELD", "ARITHMETIC", "DUPLICATE", "MAPPING_COMPLETENESS",
                          "DATE", "CURRENCY", "STATUS")
VALIDATION_STATUSES = ("PASS", "FAIL", "NOT_EVALUABLE", "REVIEW")
VALIDATION_SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "INFO")


def _tenant_col() -> Mapped[str]:
    return mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[str] = _tenant_col()
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = created_at_col()
    file_name: Mapped[str] = mapped_column(String(255))  # display only; never used as a path
    storage_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_size_bytes: Mapped[int] = mapped_column(Integer)
    file_kind: Mapped[str | None] = mapped_column(String(8), nullable=True)  # xlsx | xlsm | xls | csv
    # Inbound provenance: how the file arrived and who sent it. Today only
    # "upload" (web) and "api" exist; email/SFTP/cloud connectors will set
    # their own channel. sender/programme are optional, user-supplied labels.
    source_channel: Mapped[str] = mapped_column(String(16), default="upload")
    sender: Mapped[str | None] = mapped_column(String(200), nullable=True)
    programme: Mapped[str | None] = mapped_column(String(200), nullable=True)
    sheet_count_total: Mapped[int] = mapped_column(Integer, default=0)
    rows_processed: Mapped[int] = mapped_column(Integer, default=0)
    rows_total: Mapped[int] = mapped_column(Integer, default=0)
    coverage_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    grade: Mapped[str | None] = mapped_column(String(4), nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="UPLOADED")
    arithmetic_not_evaluable: Mapped[int] = mapped_column(Integer, default=0)
    # Customer-safe failure message + stable code. Internal detail lives on
    # jobs.error_detail and in logs, never in API responses.
    processing_error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # computed once at persist time
    ingest_notes: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # AI usage, file notes
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Soft delete (P1.5): the record, its derived rows and the original file are
    # kept; the report is hidden from every query unless include_deleted is set.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by: Mapped[str | None] = mapped_column(String(320), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    binder_id: Mapped[str | None] = mapped_column(  # P3: the binder this bordereau is reported under
        ForeignKey("binders.id", ondelete="SET NULL"), nullable=True, index=True)

    sheets: Mapped[list["Sheet"]] = relationship(back_populates="report", cascade="all, delete-orphan")
    claim_rows: Mapped[list["ClaimRow"]] = relationship(back_populates="report", cascade="all, delete-orphan")
    excluded_rows: Mapped[list["ExcludedRow"]] = relationship(back_populates="report", cascade="all, delete-orphan")


class Sheet(Base):
    __tablename__ = "sheets"

    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[str] = _tenant_col()
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    sheet_name: Mapped[str] = mapped_column(String(255))
    sheet_index: Mapped[int] = mapped_column(Integer)
    header_row_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    source_column_count: Mapped[int] = mapped_column(Integer, default=0)
    headers: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Up to 3 example values per header (truncated), captured at ingest so the
    # mapping screen never needs to re-read the file in the API process.
    samples: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="PENDING_CONFIRMATION")
    skip_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    transforms: Mapped[list | None] = mapped_column(JSON, nullable=True)
    trailing_blank_rows: Mapped[int] = mapped_column(Integer, default=0)

    report: Mapped[Report] = relationship(back_populates="sheets")
    mappings: Mapped[list["Mapping"]] = relationship(back_populates="sheet", cascade="all, delete-orphan")


class ExcludedRow(Base):
    """A source row filtered out before mapping/validation (blank, run of
    blanks, subtotal, repeated header, title) -- never a claim, always
    recorded with its reason and raw values so the ledger accounts for every
    source row. `row_count` > 1 only for a collapsed run of blank rows."""
    __tablename__ = "excluded_rows"

    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[str] = _tenant_col()
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    sheet_name: Mapped[str] = mapped_column(String(255))
    row_number: Mapped[int] = mapped_column(Integer)
    row_count: Mapped[int] = mapped_column(Integer, default=1)
    reason: Mapped[str] = mapped_column(String(32))
    detail: Mapped[str] = mapped_column(String(500))
    values: Mapped[dict] = mapped_column(JSON)

    report: Mapped[Report] = relationship(back_populates="excluded_rows")


class Mapping(Base):
    __tablename__ = "mappings"

    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[str] = _tenant_col()
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    sheet_id: Mapped[str] = mapped_column(ForeignKey("sheets.id", ondelete="CASCADE"), index=True)
    field_code: Mapped[str] = mapped_column(String(32))
    field_name: Mapped[str] = mapped_column(String(255))
    source_column: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mapping_state: Mapped[str] = mapped_column(String(32))
    review_state: Mapped[str] = mapped_column(String(32), default="UNMAPPED")
    evidence: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    rule_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ai_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    sheet: Mapped[Sheet] = relationship(back_populates="mappings")


class ClaimRow(Base):
    __tablename__ = "claim_rows"

    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[str] = _tenant_col()
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    sheet_id: Mapped[str] = mapped_column(ForeignKey("sheets.id", ondelete="CASCADE"), index=True)
    row_index: Mapped[int] = mapped_column(Integer)
    source_row_number: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-based sheet row (lineage)
    claim_reference: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    insured_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    claim_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    date_of_loss: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_notified: Mapped[date | None] = mapped_column(Date, nullable=True)
    policy_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reporting_period: Mapped[str | None] = mapped_column(String(32), nullable=True)
    paid_amount: Mapped[Decimal | None] = mapped_column(Money, nullable=True)  # indemnity paid to date
    paid_this_month: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    previously_paid: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    reserve_amount: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    fees_paid_this_month: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    fees_previously_paid: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    fees_reserve: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    fees_paid_to_date: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    # Values of source columns the confirmed mapping bound to no canonical
    # field, kept verbatim with the row (never silently discarded).
    unmapped_values: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    incurred_indemnity: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    incurred_amount: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(64), nullable=True)
    extracted_at: Mapped[datetime] = created_at_col()

    report: Mapped[Report] = relationship(back_populates="claim_rows")
    validation_results: Mapped[list["ValidationResult"]] = relationship(
        back_populates="claim_row", cascade="all, delete-orphan"
    )


class ValidationResult(Base):
    __tablename__ = "validation_results"

    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[str] = _tenant_col()
    report_id: Mapped[str | None] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True,
                                                  nullable=True)
    claim_row_id: Mapped[str] = mapped_column(ForeignKey("claim_rows.id", ondelete="CASCADE"), index=True)
    check_type: Mapped[str] = mapped_column(String(32), index=True)
    rule: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16))
    severity: Mapped[str] = mapped_column(String(16))
    message: Mapped[str] = mapped_column(String(2000))
    delta: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    extra: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    claim_row: Mapped[ClaimRow] = relationship(back_populates="validation_results")


@event.listens_for(Session, "do_orm_execute")
def _hide_deleted_reports(state: ORMExecuteState) -> None:
    """Soft-deleted reports are invisible to the application: every ORM
    SELECT (including Session.get and relationship loads) filters them out
    unless executed with ``execution_options(include_deleted=True)``."""
    if state.is_select and not state.execution_options.get("include_deleted", False):
        from .alerts import Alert
        from .deliveries import Delivery
        from .obligations import Obligation

        live = select(Report.id).where(Report.deleted_at.is_(None)).scalar_subquery()
        state.statement = state.statement.options(
            with_loader_criteria(Report, lambda cls: cls.deleted_at.is_(None), include_aliases=True),
            # Tenant-wide lists that point at a report hide that report's rows too.
            *(with_loader_criteria(m, m.report_id.in_(live), include_aliases=True)
              for m in (Alert, Obligation, Delivery)),
        )
