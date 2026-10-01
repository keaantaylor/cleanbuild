"""Durable object storage inside PostgreSQL (STORAGE_BACKEND=db).

Uploaded originals (write-once) and derived artefacts such as the parsed-
workbook cache live here, so they survive instance restarts and redeploys on
hosts whose local disk is ephemeral. Tenant-owned: Row Level Security applies
like every other tenant table."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ._util import created_at_col


class StoredBlob(Base):
    __tablename__ = "stored_blobs"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(Integer)
    content: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = created_at_col()
