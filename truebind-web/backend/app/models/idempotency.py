"""Idempotency keys for unsafe API requests (upload, process).

A client that retries a request with the same Idempotency-Key gets the first
response back instead of a second report or job. Scoped per organisation
and per endpoint; the fingerprint pins the key to one request body, so the
same key cannot be reused for a different request. Rows expire (expires_at)
and are then treated as absent."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ._util import created_at_col, uuid_pk


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("tenant_id", "scope", "key", name="uq_idempotency_keys_tenant_scope_key"),)

    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    scope: Mapped[str] = mapped_column(String(64))
    key: Mapped[str] = mapped_column(String(255))
    fingerprint: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = created_at_col()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
