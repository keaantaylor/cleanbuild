"""Append-only audit log writes. Every mutation route must call
log_action() -- there is no other write path to audit_log, so a route
that forgets simply produces a gap a reviewer will notice rather than a
row that lies about what happened."""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..models.audit import AuditLogEntry

DEFAULT_ACTOR = "web_user"  # single-user MVP; see README multi-user auth note


def log_action(
    db: Session,
    report_id: str,
    action_type: str,
    entity_type: str,
    entity_id: str,
    before: dict | None = None,
    after: dict | None = None,
    actor: str = DEFAULT_ACTOR,
) -> AuditLogEntry:
    entry = AuditLogEntry(
        report_id=report_id,
        action_type=action_type,
        entity_type=entity_type,
        entity_id=entity_id,
        actor=actor,
        before_value=before,
        after_value=after,
    )
    db.add(entry)
    db.flush()
    return entry
