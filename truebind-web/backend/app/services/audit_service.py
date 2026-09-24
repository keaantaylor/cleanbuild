"""The only write path to audit_log. Entries are hash-chained per tenant:
entry_hash = SHA-256(prev_hash + canonical JSON of the entry's content).
Any later edit/deletion breaks verify_chain(). Actor identity comes from
the authenticated Context (never from a request body -- forensic S8)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models._util import utcnow
from ..models.audit import AuditLogEntry
from ..models.identity import Tenant

GENESIS = "0" * 64
SYSTEM_ACTOR = "system"


def _ts(dt: datetime | None) -> str | None:
    """UTC, no offset, microseconds: identical whether the driver hands back
    an aware (PostgreSQL) or naive (SQLite) datetime."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.isoformat(timespec="microseconds")


def _canonical(e: AuditLogEntry) -> str:
    return json.dumps({
        "tenant_id": e.tenant_id, "seq": e.seq, "report_id": e.report_id, "action_type": e.action_type,
        "entity_type": e.entity_type, "entity_id": e.entity_id, "actor": e.actor,
        "actor_user_id": e.actor_user_id, "before": e.before_value, "after": e.after_value,
        "created_at": _ts(e.created_at),
    }, sort_keys=True, default=str, separators=(",", ":"))


def log_action(
    db: Session, tenant_id: str, report_id: str | None, action_type: str, entity_type: str, entity_id: str,
    before: dict | None = None, after: dict | None = None, actor: str = SYSTEM_ACTOR,
    actor_user_id: str | None = None,
) -> AuditLogEntry:
    # Serialise audit writes per tenant (row lock on PostgreSQL; SQLite
    # already serialises writers) so the sequence and chain stay linear.
    db.query(Tenant).filter_by(id=tenant_id).with_for_update().first()
    last = (db.query(AuditLogEntry).filter_by(tenant_id=tenant_id)
            .order_by(AuditLogEntry.seq.desc()).first())
    entry = AuditLogEntry(
        tenant_id=tenant_id, seq=(last.seq + 1) if last else 1, report_id=report_id, action_type=action_type,
        entity_type=entity_type, entity_id=str(entity_id)[:36], actor=actor[:255], actor_user_id=actor_user_id,
        before_value=before, after_value=after, prev_hash=last.entry_hash if last else GENESIS,
        created_at=utcnow(), entry_hash="",
    )
    entry.entry_hash = hashlib.sha256((entry.prev_hash + _canonical(entry)).encode()).hexdigest()
    db.add(entry)
    db.flush()
    return entry


def verify_chain(db: Session, tenant_id: str) -> tuple[bool, int | None]:
    """(True, None) if the tenant's audit chain is intact, else (False, seq of the first bad entry)."""
    prev = GENESIS
    expected_seq = 1
    for e in db.query(AuditLogEntry).filter_by(tenant_id=tenant_id).order_by(AuditLogEntry.seq):
        if e.seq != expected_seq or e.prev_hash != prev:
            return False, e.seq
        if hashlib.sha256((e.prev_hash + _canonical(e)).encode()).hexdigest() != e.entry_hash:
            return False, e.seq
        prev, expected_seq = e.entry_hash, expected_seq + 1
    return True, None
