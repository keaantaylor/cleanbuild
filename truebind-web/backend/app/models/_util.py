"""Shared column helpers so every model uses the same UUID-pk / timestamp
convention instead of each file inventing its own."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column


def new_uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def uuid_pk() -> Mapped[str]:
    return mapped_column(String(36), primary_key=True, default=new_uuid)


def created_at_col() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
