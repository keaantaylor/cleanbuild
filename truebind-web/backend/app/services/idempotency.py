"""Idempotency-Key for unsafe requests (POST /reports/upload, /process).

A client retrying after a timeout or a dropped connection sends the same
Idempotency-Key header; it gets the first response back (with
"Idempotent-Replayed: true") instead of a second report or job.

- Scope: per organisation and per endpoint; a key is pinned to one request by
  a fingerprint (the file's SHA-256 and form fields for an upload, the report
  id for processing). The same key for a different request is 422.
- The key row is written in the same transaction as the work, together with
  the response: a request that fails stores nothing, so its key can be used
  again; a request that succeeds stores both or neither.
- Concurrent duplicates: INSERT ... ON CONFLICT DO NOTHING waits for the
  other transaction, then replays its stored response.
- Keys expire after KEY_TTL and are then treated as new (deleted on the
  organisation's next keyed request).
"""

from __future__ import annotations

import hashlib
import re
from datetime import timedelta
from typing import Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import delete, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from ..models._util import new_uuid, utcnow
from ..models.idempotency import IdempotencyKey

HEADER = "Idempotency-Key"
REPLAYED_HEADER = "Idempotent-Replayed"
KEY_TTL = timedelta(hours=24)
_KEY = re.compile(r"[\x21-\x7e]{1,255}")


def validate_key(raw: str | None) -> str | None:
    if raw is None:
        return None
    if not _KEY.fullmatch(raw):
        raise HTTPException(
            status_code=400, detail="The Idempotency-Key header must be 1 to 255 visible ASCII characters."
        )
    return raw


def fingerprint(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def _find(db: Session, tenant_id: str, scope: str, key: str) -> IdempotencyKey | None:
    q = select(IdempotencyKey).where(
        IdempotencyKey.tenant_id == tenant_id, IdempotencyKey.scope == scope, IdempotencyKey.key == key
    )
    return db.execute(q).scalars().first()


def claim(
    db: Session, *, tenant_id: str, user_id: str | None, scope: str, key: str, request_fingerprint: str
) -> IdempotencyKey | JSONResponse:
    """Our new key row (proceed, then complete() it before committing), or
    the response to replay."""
    now = utcnow()
    # Expired keys of this organisation go first (so an expired key is new
    # again); cleanup stays inside the tenant's own RLS scope.
    db.execute(delete(IdempotencyKey).where(IdempotencyKey.tenant_id == tenant_id, IdempotencyKey.expires_at <= now))
    values: dict[str, Any] = {
        "id": new_uuid(),
        "tenant_id": tenant_id,
        "scope": scope,
        "key": key,
        "fingerprint": request_fingerprint,
        "user_id": user_id,
        "created_at": now,
        "expires_at": now + KEY_TTL,
    }
    dialect = postgresql if db.get_bind().dialect.name == "postgresql" else sqlite
    stmt = (
        dialect.insert(IdempotencyKey)
        .values(**values)
        .on_conflict_do_nothing(index_elements=["tenant_id", "scope", "key"])
        .returning(IdempotencyKey.id)
    )
    # RETURNING yields a row only when this request inserted the key (rowcount
    # is not reliable for ON CONFLICT DO NOTHING across drivers).
    inserted = db.execute(stmt).first() is not None
    row = _find(db, tenant_id, scope, key)
    if row is None:  # pragma: no cover -- the row was either inserted or already there
        raise HTTPException(status_code=409, detail="Retry the request.")
    if inserted:
        return row
    if row.fingerprint != request_fingerprint:
        raise HTTPException(
            status_code=422,
            detail="This Idempotency-Key was already used for a different request. Use a new key for a new request.",
        )
    if row.response_status is None or row.response_body is None:  # pragma: no cover -- stored with the work
        raise HTTPException(status_code=409, detail="A request with this Idempotency-Key is still in progress.")
    return JSONResponse(row.response_body, status_code=row.response_status, headers={REPLAYED_HEADER: "true"})


def complete(row: IdempotencyKey, status_code: int, body: dict[str, Any]) -> JSONResponse:
    """Store the response with the work (same transaction) and return it."""
    row.response_status = status_code
    row.response_body = body
    return JSONResponse(body, status_code=status_code)
