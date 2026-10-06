"""A report's workbook opened in a connected spreadsheet provider (migration 0024)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ._util import created_at_col, uuid_pk


class ConnectorLink(Base):
    """The remote copy, and the exact bytes it started from (base_sha256), so
    edits made in Excel or Google Sheets can be read back as proposed changes."""

    __tablename__ = "connector_links"

    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(32))
    file_id: Mapped[str] = mapped_column(String(255))
    web_url: Mapped[str] = mapped_column(String(2000))
    base_sha256: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(String(320))
    created_at: Mapped[datetime] = created_at_col()
    last_pulled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
