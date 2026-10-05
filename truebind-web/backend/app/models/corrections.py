"""Corrections and workbook versions.

A correction never touches the uploaded file. It records one cell's change:
before (read from the stored original), after, reason, the rule it addresses,
who proposed it and who approved or rejected it. A workbook version is a
fingerprint (SHA-256) of a specific workbook: the original as received, a
corrected copy built from the original plus approved corrections, or that copy
once approved for submission. Versions are built deterministically, so the same
original and the same approved corrections always give the same bytes and hash.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ._util import created_at_col, uuid_pk

CORRECTION_STATUSES = ("PROPOSED", "APPROVED", "REJECTED")
VERSION_KINDS = ("original", "corrected", "approved")


class Correction(Base):
    __tablename__ = "corrections"

    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    issue_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)  # validation_results.id
    sheet_name: Mapped[str] = mapped_column(String(255))
    cell: Mapped[str] = mapped_column(String(16))
    before_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    rule: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="manual")  # manual | auto
    status: Mapped[str] = mapped_column(String(16), default="PROPOSED")
    proposed_by: Mapped[str] = mapped_column(String(320))
    created_at: Mapped[datetime] = created_at_col()
    decided_by: Mapped[str | None] = mapped_column(String(320), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class WorkbookVersion(Base):
    __tablename__ = "workbook_versions"
    __table_args__ = (UniqueConstraint("report_id", "number"),)

    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(16))
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(Integer)
    corrections: Mapped[list | None] = mapped_column(JSON, nullable=True)  # ids of the approved corrections applied
    based_on: Mapped[str | None] = mapped_column(String(36), nullable=True)  # the version this one approves
    created_by: Mapped[str] = mapped_column(String(320))
    created_at: Mapped[datetime] = created_at_col()
