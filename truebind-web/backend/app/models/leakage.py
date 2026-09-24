from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ._util import created_at_col, uuid_pk

LEAKAGE_CONFIDENCE_TIERS = ("CERTAIN", "PROBABLE", "POSSIBLE")
LEAKAGE_STATUSES = ("OPEN", "CONFIRMED", "DISMISSED")


class LeakageFlag(Base):
    __tablename__ = "leakage_flags"

    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    source_row_id: Mapped[str] = mapped_column(ForeignKey("claim_rows.id", ondelete="CASCADE"))
    match_row_id: Mapped[str] = mapped_column(ForeignKey("claim_rows.id", ondelete="CASCADE"))
    confidence_category: Mapped[str] = mapped_column(String(16))
    amount_exposure: Mapped[float | None] = mapped_column(Float, nullable=True)
    matched_fields: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="OPEN")
    reviewed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = created_at_col()
