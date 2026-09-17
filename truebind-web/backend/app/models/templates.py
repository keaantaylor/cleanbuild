from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ._util import created_at_col, uuid_pk


class Template(Base):
    __tablename__ = "templates"

    id: Mapped[str] = uuid_pk()
    name: Mapped[str] = mapped_column(String(255))
    sender_identifier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    field_mappings: Mapped[dict] = mapped_column(JSON)
    is_standard: Mapped[bool] = mapped_column(Boolean, default=False)
    is_deletable: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = created_at_col()
