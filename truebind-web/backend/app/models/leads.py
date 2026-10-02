"""Website enquiries (Book a demo, Health Check, contact, product updates).

Not tenant data: these are people who contacted TrueBind itself, so there is
no tenant_id and no Row Level Security policy. Only the operators named in
LEADS_ADMIN_EMAILS can read them (app/routes/leads.py)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ._util import created_at_col, uuid_pk

LEAD_KINDS = ("demo", "health", "contact", "updates")


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[str] = uuid_pk()
    kind: Mapped[str] = mapped_column(String(16), index=True)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    company: Mapped[str | None] = mapped_column(String(200), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # utm_* / referrer / landing_page as captured by the site (first touch).
    attribution: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    page: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = created_at_col()
    # Health Check requests: the visitor's consent to us reading the file they sent.
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)


class LeadFile(Base):
    """A file sent with a Health Check request. Kept apart from the lead row
    (lists never load it), readable only by operators, deleted after
    LEAD_FILE_RETENTION_DAYS."""

    __tablename__ = "lead_files"

    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), primary_key=True)
    content: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = created_at_col()
