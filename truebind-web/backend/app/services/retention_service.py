"""Deletion and retention. A report's source file and every derived row
(sheets, mappings, claim rows, findings, alerts, summaries, jobs) are
deleted together; the audit log keeps a record that the deletion happened
(report_id is deliberately not a foreign key on audit_log) but holds no
claim data. Reports expire `tenant.retention_days` after upload."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from ..database import set_tenant
from ..models._util import utcnow
from ..models.identity import Tenant
from ..models.reports import Report
from . import audit_service, job_service
from .storage import store

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
    db.delete(report)
    db.flush()
    store.delete_report(tenant_id, report_id)


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
