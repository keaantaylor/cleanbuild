"""Durable job queue on the application database (no extra infrastructure:
the deployment already requires PostgreSQL; adding Redis/Celery would add a
moving part without a measured need -- AI/DECISIONS.md 2026-09-24).

Lifecycle: QUEUED -> RUNNING -> SUCCEEDED | FAILED | CANCELLED.
- Claim: one row, atomically, with FOR UPDATE SKIP LOCKED on PostgreSQL,
  honouring a per-tenant concurrency limit.
- Lease: a RUNNING job has lease_expires_at; the worker heartbeats it.
- Reaper: a RUNNING job whose lease expired (worker crashed / killed / host
  lost) is re-queued with backoff while attempts < max_attempts, otherwise
  FAILED("worker_lost"). No job stays RUNNING forever.
- Retries never duplicate results: handlers replace a report's results
  inside one transaction (persistence_service)."""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..config import JOB_LEASE_S, MAX_CONCURRENT_JOBS_PER_TENANT, WORKER_STALE_S
from ..database import set_tenant
from ..models._util import utcnow
from ..models.jobs import TERMINAL_JOB_STATUSES, Job, WorkerHeartbeat
from ..models.reports import Report
from . import audit_service, report_state

log = logging.getLogger("truebind.jobs")

REPORT_STATUS_FOR_KIND = {"INGEST": "INGESTING", "PROCESS": "PROCESSING"}


class JobConflict(Exception):
    pass


def active_job(db: Session, report_id: str) -> Job | None:
    return (db.query(Job).filter(Job.report_id == report_id, Job.status.in_(("QUEUED", "RUNNING")))
            .order_by(Job.created_at.desc()).first())


def enqueue(db: Session, report: Report, kind: str, actor: str, actor_user_id: str | None) -> Job:
    if active_job(db, report.id) is not None:
        raise JobConflict("this report already has a job queued or running")
    job = Job(tenant_id=report.tenant_id, report_id=report.id, kind=kind, status="QUEUED")
    db.add(job)
    db.flush()
    report_state.transition(db, report, "QUEUED", actor=actor, actor_user_id=actor_user_id, reason=f"{kind} job")
    report.processing_error = None
    report.error_code = None
    audit_service.log_action(db, report.tenant_id, report.id, "JOB_QUEUED", "JOB", job.id, after={"kind": kind},
                             actor=actor, actor_user_id=actor_user_id)
    return job


def claim_next(db: Session, worker_id: str) -> Job | None:
    """Atomically claim the next runnable job. Returns it RUNNING, or None."""
    now = utcnow()
    set_tenant(db, None, worker=True)
    running = (select(Job.tenant_id, func.count().label("n")).where(Job.status == "RUNNING")
               .group_by(Job.tenant_id).subquery())
    q = (select(Job).outerjoin(running, running.c.tenant_id == Job.tenant_id)
         .where(Job.status == "QUEUED", (Job.run_after.is_(None)) | (Job.run_after <= now),
                func.coalesce(running.c.n, 0) < MAX_CONCURRENT_JOBS_PER_TENANT)
         .order_by(Job.created_at).limit(1))
    if db.get_bind().dialect.name == "postgresql":
        q = q.with_for_update(skip_locked=True, of=Job)
    job = db.execute(q).scalars().first()
    if job is None:
        db.commit()
        return None
    # Compare-and-set: even where SKIP LOCKED is unavailable (SQLite), two
    # workers can never both win the same job.
    won = db.execute(
        update(Job).where(Job.id == job.id, Job.status == "QUEUED")
        .values(status="RUNNING", attempts=Job.attempts + 1, lease_owner=worker_id,
                lease_expires_at=now + timedelta(seconds=JOB_LEASE_S), heartbeat_at=now, started_at=now,
                stage="starting")
        .execution_options(synchronize_session=False)
    ).rowcount
    if won != 1:
        db.rollback()
        return None
    db.refresh(job)
    tenant_id = job.tenant_id
    set_tenant(db, tenant_id)
    report = db.get(Report, job.report_id)
    if report is not None:
        report_state.transition(db, report, REPORT_STATUS_FOR_KIND[job.kind], reason=f"claimed by {worker_id}")
    audit_service.log_action(db, tenant_id, job.report_id, "JOB_STARTED", "JOB", job.id,
                             after={"worker": worker_id, "attempt": job.attempts})
    db.commit()
    return job


def heartbeat(db: Session, job_id: str, worker_id: str) -> str:
    """Extend the lease. Returns "ok", "cancel" (a user asked to stop: the
    worker must kill the job) or "gone" (the job is already terminal or no
    longer ours)."""
    set_tenant(db, None, worker=True)
    job = db.get(Job, job_id)
    if job is None or job.status != "RUNNING" or job.lease_owner != worker_id:
        db.commit()
        return "gone"
    if job.error_code == "cancel_requested":
        db.commit()
        return "cancel"
    now = utcnow()
    job.heartbeat_at = now
    job.lease_expires_at = now + timedelta(seconds=JOB_LEASE_S)
    db.commit()
    return "ok"


def set_stage(db: Session, job: Job, stage: str) -> None:
    job.stage = stage
    db.commit()


def finish(db: Session, job: Job, ok: bool, code: str | None = None, message: str | None = None,
           detail: str | None = None, retryable: bool = False, metrics: dict | None = None) -> None:
    """Record a terminal (or retry) outcome and move the report accordingly."""
    set_tenant(db, job.tenant_id)
    report = db.get(Report, job.report_id)
    job.finished_at = utcnow()
    job.lease_owner = None
    job.lease_expires_at = None
    job.metrics = metrics or job.metrics
    if ok:
        job.status = "SUCCEEDED"
        audit_service.log_action(db, job.tenant_id, job.report_id, "JOB_SUCCEEDED", "JOB", job.id,
                                 after={"kind": job.kind, "metrics": metrics})
    elif job.error_code == "cancel_requested" or code == "cancelled":
        job.status = "CANCELLED"
        job.error_code, job.error_message = "cancelled", "Cancelled by a user."
        if report is not None and report.status in report_state.ACTIVE:
            report_state.transition(db, report, "CANCELLED", reason="cancelled")
        audit_service.log_action(db, job.tenant_id, job.report_id, "JOB_CANCELLED", "JOB", job.id)
    elif retryable and job.attempts < job.max_attempts:
        job.status = "QUEUED"
        job.run_after = utcnow() + timedelta(seconds=15 * job.attempts)
        job.error_code, job.error_message, job.error_detail = code, message, (detail or "")[:4000]
        if report is not None:
            report_state.transition(db, report, "QUEUED", reason=f"retry after {code}")
    else:
        job.status = "FAILED"
        job.error_code, job.error_message, job.error_detail = code, message, (detail or "")[:4000]
        if report is not None and report.status in report_state.ACTIVE:
            report_state.transition(db, report, "FAILED", reason=code)
            report.processing_error = message
            report.error_code = code
        audit_service.log_action(db, job.tenant_id, job.report_id, "JOB_FAILED", "JOB", job.id,
                                 after={"code": code, "message": message})
    db.commit()


def dead_worker_ids(db: Session) -> set[str]:
    """Workers that registered but stopped checking in (process killed, API
    restarted, machine lost). Their RUNNING jobs are recovered immediately
    instead of waiting for the lease to run out."""
    cutoff = utcnow() - timedelta(seconds=WORKER_STALE_S * 2)
    return {w for (w,) in db.query(WorkerHeartbeat.id).filter(WorkerHeartbeat.last_seen_at < cutoff)}


def live_workers(db: Session) -> list[WorkerHeartbeat]:
    cutoff = utcnow() - timedelta(seconds=WORKER_STALE_S)
    return db.query(WorkerHeartbeat).filter(WorkerHeartbeat.last_seen_at >= cutoff).all()


def reap_expired(db: Session) -> int:
    """Recover jobs whose worker vanished: lease expired, or the owning
    worker's liveness record went stale. Returns the number reaped."""
    now = utcnow()
    set_tenant(db, None, worker=True)
    dead = dead_worker_ids(db)
    q = db.query(Job).filter(Job.status == "RUNNING")
    stale = [j for j in q.all() if (j.lease_expires_at is not None and _aware(j.lease_expires_at) < now)
             or (j.lease_owner in dead)]
    ids = [(j.id, j.tenant_id) for j in stale]
    # Forget registry rows of long-dead workers (their jobs are handled above).
    old = utcnow() - timedelta(days=1)
    db.query(WorkerHeartbeat).filter(WorkerHeartbeat.last_seen_at < old).delete(synchronize_session=False)
    db.commit()
    for job_id, tenant_id in ids:
        set_tenant(db, tenant_id)
        job = db.get(Job, job_id)
        if job is None or job.status != "RUNNING":
            continue
        log.warning("recovering job %s (owner %s stopped responding)", job.id, job.lease_owner)
        again = job.attempts < job.max_attempts
        finish(db, job, ok=False, code="worker_lost",
               message=("Processing was interrupted because the processing service stopped. It has been "
                        "queued again automatically." if again else
                        "Processing was interrupted twice because the processing service stopped. "
                        "Use Try again once the service is running."),
               detail=f"lease expired at {job.lease_expires_at}; owner {job.lease_owner}", retryable=True)
    return len(ids)


def _aware(dt):
    from datetime import timezone as _tz
    return dt.replace(tzinfo=_tz.utc) if dt is not None and dt.tzinfo is None else dt


def request_cancel(db: Session, report: Report, actor: str, actor_user_id: str | None) -> bool:
    job = active_job(db, report.id)
    if job is None:
        return False
    if job.status == "QUEUED":
        job.status = "CANCELLED"
        job.finished_at = utcnow()
        job.error_code, job.error_message = "cancelled", "Cancelled by a user."
        report_state.transition(db, report, "CANCELLED", actor=actor, actor_user_id=actor_user_id, reason="cancelled")
        audit_service.log_action(db, report.tenant_id, report.id, "JOB_CANCELLED", "JOB", job.id,
                                 actor=actor, actor_user_id=actor_user_id)
    else:
        job.error_code = "cancel_requested"  # the worker stops at its next heartbeat
    return True


def is_terminal(job: Job) -> bool:
    return job.status in TERMINAL_JOB_STATUSES

