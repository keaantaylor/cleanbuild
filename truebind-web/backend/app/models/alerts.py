from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ._util import created_at_col, uuid_pk

ALERT_SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "INFO")
ALERT_SOURCES = ("COVERAGE", "MANDATORY_FAIL", "NOT_EVALUABLE", "DUPLICATE", "OVERDUE", "MAPPING_COMPLETENESS")


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[str] = uuid_pk()
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id"), index=True)
    severity: Mapped[str] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(String(1000))
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = created_at_col()
