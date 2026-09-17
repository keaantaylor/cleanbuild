"""Report / Sheet / Mapping / ClaimRow / ValidationResult -- the core
processing pipeline's persisted shape. Unlike the Streamlit build (which
only persisted the health-report summary and kept full canonical rows
in-memory per session), the web app persists every claim row and its
validation outcomes, since results now need to survive a page reload and
be queried by the Exceptions/Duplicates screens independently of the
upload session that produced them."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from ._util import created_at_col, uuid_pk

REPORT_STATUSES = ("PENDING_MAPPING", "READY_FOR_REVIEW", "COMPLETE")
SHEET_STATUSES = ("PENDING_CONFIRMATION", "CONFIRMED", "SKIPPED")
MAPPING_STATES = ("MAPPED_BY_ALIAS", "MAPPED_BY_AI", "UNMAPPED")
VALIDATION_CHECK_TYPES = ("MANDATORY_FIELD", "ARITHMETIC", "DUPLICATE", "MAPPING_COMPLETENESS")
VALIDATION_STATUSES = ("PASS", "FAIL", "NOT_EVALUABLE")
VALIDATION_SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "INFO")


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[str] = uuid_pk()
    created_at: Mapped[datetime] = created_at_col()
    file_name: Mapped[str] = mapped_column(String(500))
    file_size_bytes: Mapped[int] = mapped_column(Integer)
    sheet_count_total: Mapped[int] = mapped_column(Integer, default=0)
    rows_processed: Mapped[int] = mapped_column(Integer, default=0)
    rows_total: Mapped[int] = mapped_column(Integer, default=0)
    coverage_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    grade: Mapped[str | None] = mapped_column(String(4), nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="PENDING_MAPPING")
    # Rows not evaluable for arithmetic reconciliation aren't flagged as a
    # per-row exception (see bordereaux.validation._check_arithmetic) --
    # the only place this count exists is here on the report summary.
    arithmetic_not_evaluable: Mapped[int] = mapped_column(Integer, default=0)

    sheets: Mapped[list["Sheet"]] = relationship(back_populates="report", cascade="all, delete-orphan")
    claim_rows: Mapped[list["ClaimRow"]] = relationship(back_populates="report", cascade="all, delete-orphan")


class Sheet(Base):
    __tablename__ = "sheets"

    id: Mapped[str] = uuid_pk()
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id"), index=True)
    sheet_name: Mapped[str] = mapped_column(String(255))
    sheet_index: Mapped[int] = mapped_column(Integer)
    header_row_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="PENDING_CONFIRMATION")
    skip_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    report: Mapped[Report] = relationship(back_populates="sheets")
    mappings: Mapped[list["Mapping"]] = relationship(back_populates="sheet", cascade="all, delete-orphan")


class Mapping(Base):
    __tablename__ = "mappings"

    id: Mapped[str] = uuid_pk()
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id"), index=True)
    sheet_id: Mapped[str] = mapped_column(ForeignKey("sheets.id"), index=True)
    field_code: Mapped[str] = mapped_column(String(32))
    field_name: Mapped[str] = mapped_column(String(255))
    source_column: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mapping_state: Mapped[str] = mapped_column(String(32))
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    sheet: Mapped[Sheet] = relationship(back_populates="mappings")


class ClaimRow(Base):
    __tablename__ = "claim_rows"

    id: Mapped[str] = uuid_pk()
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id"), index=True)
    sheet_id: Mapped[str] = mapped_column(ForeignKey("sheets.id"), index=True)
    row_index: Mapped[int] = mapped_column(Integer)
    claim_reference: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    insured_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    claim_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    date_of_loss: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_notified: Mapped[date | None] = mapped_column(Date, nullable=True)
    policy_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    paid_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    reserve_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    incurred_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    extracted_at: Mapped[datetime] = created_at_col()

    report: Mapped[Report] = relationship(back_populates="claim_rows")
    validation_results: Mapped[list["ValidationResult"]] = relationship(
        back_populates="claim_row", cascade="all, delete-orphan"
    )


class ValidationResult(Base):
    __tablename__ = "validation_results"

    id: Mapped[str] = uuid_pk()
    claim_row_id: Mapped[str] = mapped_column(ForeignKey("claim_rows.id"), index=True)
    check_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))
    severity: Mapped[str] = mapped_column(String(16))
    message: Mapped[str] = mapped_column(String(1000))
    delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    extra: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    claim_row: Mapped[ClaimRow] = relationship(back_populates="validation_results")
