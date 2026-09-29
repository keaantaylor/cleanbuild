"""Check modules (P3-P5): one shared Finding model and a record of each run.

- ModuleRun: one row per (report, module) holding the latest run: whether
  the module was assessed at all, per-rule coverage (rows assessed, rows
  not assessed and why) and the configuration it ran against. A module that
  could not run says so with a reason -- never an empty "no findings".
- Finding: one issue a module raised, in plain English, with drill-down to
  sheet / row / field and an optional amount in an ISO 4217 currency.
  status FAIL (a breach) or REVIEW (a person must decide). Findings are
  replaced on each run; a person's disposition (CONFIRMED / DISMISSED) is
  carried over to the identical finding on the next run.
- Binder: an organisation's delegated-authority contract (P3).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ._util import created_at_col, uuid_pk
from .money import Money

MODULES = ("binder", "leakage", "sanctions")
FINDING_STATUSES = ("FAIL", "REVIEW")
FINDING_SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "INFO")
DISPOSITIONS = ("OPEN", "CONFIRMED", "DISMISSED")
RUN_STATES = ("ASSESSED", "PARTIAL", "NOT_ASSESSED")


def _tenant() -> Mapped[str]:
    return mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)


class ModuleRun(Base):
    __tablename__ = "module_runs"
    __table_args__ = (UniqueConstraint("report_id", "module", name="uq_module_runs_report_module"),)

    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[str] = _tenant()
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    module: Mapped[str] = mapped_column(String(32))
    state: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    rules: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    config: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    finding_count: Mapped[int] = mapped_column(Integer, default=0)
    ran_at: Mapped[datetime] = created_at_col()
    ran_by: Mapped[str] = mapped_column(String(255))


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[str] = _tenant()
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    module: Mapped[str] = mapped_column(String(32), index=True)
    rule_code: Mapped[str] = mapped_column(String(48))
    status: Mapped[str] = mapped_column(String(16))
    severity: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(200))
    explanation: Mapped[str] = mapped_column(String(2000))
    sheet_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    row_number: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-based source row
    field_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_column: Mapped[str | None] = mapped_column(String(255), nullable=True)
    claim_row_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    claim_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    disposition: Mapped[str] = mapped_column(String(16), default="OPEN")
    disposition_note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    disposed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    disposed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = created_at_col()


class Binder(Base):
    __tablename__ = "binders"

    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[str] = _tenant()
    name: Mapped[str] = mapped_column(String(200))
    umr: Mapped[str | None] = mapped_column(String(64), nullable=True)
    coverholder: Mapped[str | None] = mapped_column(String(200), nullable=True)
    inception_date: Mapped[date] = mapped_column(Date)
    expiry_date: Mapped[date] = mapped_column(Date)
    currencies: Mapped[list[str]] = mapped_column(JSON, default=list)
    limit_currency: Mapped[str] = mapped_column(String(3))
    claims_authority: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    aggregate_limit: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    created_at: Mapped[datetime] = created_at_col()
    created_by: Mapped[str] = mapped_column(String(255))


class SanctionsList(Base):
    """A sanctions list an organisation loaded (P5). Entries live in sanctions_entries."""

    __tablename__ = "sanctions_lists"

    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[str] = _tenant()
    name: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(16))  # OFSI | OFAC | EU | UN | CUSTOM
    file_name: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64))
    entry_count: Mapped[int] = mapped_column(Integer)
    uploaded_at: Mapped[datetime] = created_at_col()
    uploaded_by: Mapped[str] = mapped_column(String(255))


class SanctionsEntry(Base):
    __tablename__ = "sanctions_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = _tenant()
    list_id: Mapped[str] = mapped_column(ForeignKey("sanctions_lists.id", ondelete="CASCADE"), index=True)
    reference: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(500))
    kind: Mapped[str] = mapped_column(String(32))
