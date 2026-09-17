"""Truebind 2.2: the audit trail. Append-only -- every mapping
confirmation, manual override, obligation status change, and export gets
one row here, with actor, timestamp, and before/after values. Nothing in
this module ever updates or deletes a row once written.
"""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from .db.models import AuditLogEntry

# Canonical action_type values -- keep this list authoritative so every
# caller (and the governance pack) agrees on what a given action means.
ACTION_MAPPING_CONFIRMED = "mapping_confirmed"
ACTION_MAPPING_OVERRIDDEN = "mapping_overridden"
ACTION_OBLIGATION_STATUS_CHANGED = "obligation_status_changed"
ACTION_LEAKAGE_FLAG_REVIEWED = "leakage_flag_reviewed"
ACTION_EXCEPTION_STATUS_CHANGED = "exception_status_changed"
ACTION_EXPORT_TRIGGERED = "export_triggered"
ACTION_TEMPLATE_CREATED = "template_created"


def log_action(
    session: Session,
    actor: str,
    action_type: str,
    entity_type: str,
    entity_id: str | None = None,
    before: object = None,
    after: object = None,
    report_id: str | None = None,
) -> AuditLogEntry:
    entry = AuditLogEntry(
        report_id=report_id,
        actor=actor,
        action_type=action_type,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        before_value=json.dumps(before, default=str) if before is not None else None,
        after_value=json.dumps(after, default=str) if after is not None else None,
    )
    session.add(entry)
    session.flush()
    return entry


def log_mapping_decisions(
    session: Session, actor: str, report_id: str | None, audit_records: list,
) -> list[AuditLogEntry]:
    """audit_records: mapping.MappingAuditRecord list (see mapping.audit_trail).
    Logs one entry per confirmed column mapping, distinguishing an
    automatic suggestion the user accepted from a manual override."""
    entries = []
    for rec in audit_records:
        if not rec.confirmed:
            continue
        action_type = ACTION_MAPPING_CONFIRMED if rec.method in ("alias", "ai") else ACTION_MAPPING_OVERRIDDEN
        entries.append(log_action(
            session, actor, action_type, entity_type="column_mapping",
            entity_id=rec.source_column,
            before={"suggested_field_code": rec.field_code, "method": rec.method, "confidence": rec.confidence},
            after={"confirmed_field_code": rec.field_code},
            report_id=report_id,
        ))
    return entries
