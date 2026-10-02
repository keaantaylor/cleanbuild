"""Deletion and retention.

Deleting a report, or its retention period (default 30 days, set per
organisation) ending, first hides it everywhere (models/reports.py filters
``deleted_at``) with an audit entry. The worker's next sweep then PURGES it:
the original file, everything derived from it, the claim rows, findings,
samples and summary are physically deleted. The report record keeps only its
file name, SHA-256, dates and status, and the hash-chained audit trail is kept,
so what happened stays provable without keeping the data. Database backups
expire on the hosting provider's schedule (see the security page)."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from ..database import set_tenant
from ..models._util import utcnow
from ..models.identity import Tenant
from ..models.alerts import Alert
from ..models.exception_summary import ExceptionSummary
from ..models.leakage import LeakageFlag
from ..models.modules import Finding, ModuleRun
from ..models.reports import ClaimRow, ExcludedRow, Mapping, Report, Sheet, ValidationResult
from . import audit_service, job_service
from .storage import get_store

_PURGED_TABLES = (ValidationResult, ClaimRow, ExcludedRow, Mapping, Sheet, ExceptionSummary, Alert, LeakageFlag,
                  Finding, ModuleRun)

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


def purge_report(db: Session, report: Report) -> int:
    """Physically delete a deleted/expired report's data. Caller commits.
    The original is kept only while another live report of the same
    organisation was uploaded from the very same file."""
    from sqlalchemy import delete as sa_delete

    for model in _PURGED_TABLES:
        db.execute(sa_delete(model).where(model.report_id == report.id))
    shared = (db.query(Report.id).filter(Report.tenant_id == report.tenant_id, Report.id != report.id,
                                         Report.source_sha256 == report.source_sha256,
                                         Report.purged_at.is_(None)).first())
    removed = 0
    if not shared and report.source_sha256:
        removed = get_store().delete_source(report.storage_key or "", report.tenant_id, report.source_sha256, db=db)
    report.summary = None
    report.ingest_notes = None
    report.storage_key = None if not shared else report.storage_key
    report.purged_at = utcnow()
    audit_service.log_action(db, report.tenant_id, report.id, "REPORT_PURGED", "REPORT", report.id,
                             after={"objects_deleted": removed, "original_kept_for_other_report": bool(shared)})
    db.flush()
    return removed


def purge_deleted_reports(db: Session, limit: int = 100) -> int:
    """Purge every report that was deleted or expired and not yet purged."""
    n = 0
    tenants = [t.id for t in db.query(Tenant.id).all()]
    db.commit()
    for tid in tenants:
        set_tenant(db, tid)
        due = (db.query(Report).execution_options(include_deleted=True)
               .filter(Report.tenant_id == tid, Report.deleted_at.is_not(None), Report.purged_at.is_(None))
               .limit(limit).all())
        for report in due:
            purge_report(db, report)
            db.commit()
            n += 1
    if n:
        log.info("retention: purged %d report(s)", n)
    return n


def purge_old_lead_files(db: Session) -> int:
    """Files sent with website Health Check requests are deleted after
    LEAD_FILE_RETENTION_DAYS (default 30); the enquiry itself is kept."""
    from datetime import timedelta

    from ..models.leads import LeadFile
    from ..settings import get_settings

    cutoff = utcnow() - timedelta(days=get_settings().lead_file_retention_days)
    n = db.query(LeadFile).filter(LeadFile.created_at < cutoff).delete(synchronize_session=False)
    db.commit()
    if n:
        log.info("retention: deleted %d Health Check file(s)", n)
    return n
