"""Deletion and retention -- both are SOFT (P1.5, non-negotiable #7).

Deleting a report, or its retention period ending, hides it everywhere in the
application (models/reports.py filters ``deleted_at``) and writes an audit
entry. The original file and the derived rows are kept: originals are
immutable and the application has no delete path. Physically purging data
after the retention period is an operator-run storage lifecycle rule and
database purge (docs/RETENTION.md), not application code."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from ..database import set_tenant
from ..models._util import utcnow
from ..models.identity import Tenant
from ..models.reports import Report
from . import audit_service, job_service

log = logging.getLogger("truebind.retention")


def delete_report(db: Session, report: Report, action: str, actor: str = audit_service.SYSTEM_ACTOR,
                  actor_user_id: str | None = None) -> None:
    """Caller commits. Refuses while a job is running (the worker would
    otherwise write into a deleted report)."""
    if job_service.active_job(db, report.id) is not None and report.status in ("INGESTING", "PROCESSING"):
        raise job_service.JobConflict("cancel the running job before deleting this report")
    tenant_id, report_id = report.tenant_id, report.id
    audit_service.log_action(db, tenant_id, report_id, action, "REPORT", report_id,
                             before={"file_name": report.file_name, "sha256": report.source_sha256,
                                     "status": report.status},
                             actor=actor, actor_user_id=actor_user_id)
    report.deleted_at = utcnow()
    report.deleted_by = actor
    db.flush()


def expire_due_reports(db: Session, limit: int = 200) -> int:
    now = utcnow()
    n = 0
    tenants = [t.id for t in db.query(Tenant.id).all()]
    db.commit()
    for tid in tenants:
        set_tenant(db, tid)
        due = (db.query(Report).filter(Report.tenant_id == tid, Report.expires_at.is_not(None),
                                       Report.expires_at < now).limit(limit).all())
        for report in due:
            try:
                delete_report(db, report, "REPORT_EXPIRED")
                db.commit()
                n += 1
            except job_service.JobConflict:
                db.rollback()
    if n:
        log.info("retention: deleted %d expired report(s)", n)
    return n
