from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ._util import created_at_col, uuid_pk

# OVERDUE is computed from (deadline < today and status not in RESOLVED),
# never set directly -- see services/obligation_service.py.
OBLIGATION_STATUSES = ("OPEN", "IN_PROGRESS", "RESOLVED", "OVERDUE")


class Obligation(Base):
    __tablename__ = "obligations"

    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    claim_row_id: Mapped[str | None] = mapped_column(ForeignKey("claim_rows.id", ondelete="CASCADE"), nullable=True)
    owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="OPEN")
    note: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = created_at_col()
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
