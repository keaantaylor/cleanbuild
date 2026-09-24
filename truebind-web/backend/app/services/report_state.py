"""Report lifecycle state machine. Every status change goes through
transition(), which rejects illegal moves and audits the change."""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..models._util import utcnow
from ..models.reports import Report
from . import audit_service

LEGAL = {
    "UPLOADED": {"QUEUED", "FAILED", "CANCELLED"},
    "QUEUED": {"INGESTING", "PROCESSING", "FAILED", "CANCELLED"},
    "INGESTING": {"WAITING_FOR_REVIEW", "FAILED", "QUEUED", "CANCELLED"},
    "WAITING_FOR_REVIEW": {"QUEUED", "CANCELLED", "EXPIRED"},
    "PROCESSING": {"COMPLETE", "FAILED", "QUEUED", "CANCELLED"},
    "COMPLETE": {"QUEUED", "EXPIRED"},  # re-processing after a mapping change is allowed (idempotent)
    "FAILED": {"QUEUED", "EXPIRED"},    # retry
    "CANCELLED": {"EXPIRED"},
    "EXPIRED": set(),
}
ACTIVE = {"QUEUED", "INGESTING", "PROCESSING"}


class IllegalTransition(Exception):
    pass


def transition(db: Session, report: Report, new: str, actor: str = audit_service.SYSTEM_ACTOR,
               actor_user_id: str | None = None, reason: str | None = None) -> None:
    old = report.status
    if new == old:
        return
    if new not in LEGAL.get(old, set()):
        raise IllegalTransition(f"{old} -> {new}")
    report.status = new
    report.updated_at = utcnow()
    audit_service.log_action(db, report.tenant_id, report.id, "STATUS_CHANGED", "REPORT", report.id,
                             before={"status": old}, after={"status": new, "reason": reason},
                             actor=actor, actor_user_id=actor_user_id)
