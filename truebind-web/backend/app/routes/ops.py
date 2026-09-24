"""Operational surfaces: command-centre overview, prioritised work queue,
outbound deliveries, inbound/outbound channels, per-report processing
history and exception review. Everything is tenant-scoped and computed
from stored facts (report summaries, findings, jobs, audit) -- nothing here
is estimated or invented."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import config
from ..database import get_db
from ..models._util import utcnow
from ..models.alerts import Alert
from ..models.audit import AuditLogEntry
from ..models.deliveries import Delivery
from ..models.jobs import Job
from ..models.obligations import Obligation
from ..models.reports import Report, Sheet, ValidationResult
from ..schemas.reports import AlertOut, AuditLogOut, JobOut, Page, UtcDatetime
from ..security.auth import Context, get_context, require_writer
from ..security.ratelimit import limiter
from ..services import audit_service, delivery_service, job_service
from .deps import Paging, get_report_or_404, report_out

router = APIRouter(prefix="/api/v1", tags=["operations"])

_IN_FLIGHT = ("UPLOADED", "QUEUED", "INGESTING", "PROCESSING")


def _age_s(dt: datetime | None) -> float | None:
    if dt is None:
        return None
    dt = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return (utcnow() - dt).total_seconds()


# ------------------------------------------------------------------ overview

@router.get("/overview")
def overview(ctx: Context = Depends(get_context), db: Session = Depends(get_db)) -> dict:
    tid = ctx.tenant_id
    reports = db.query(Report).filter(Report.tenant_id == tid).order_by(Report.created_at.desc()).all()
    by_status = Counter(r.status for r in reports)
    complete = [r for r in reports if r.status == "COMPLETE" and r.summary]
    totals = Counter()
    for r in complete:
        s = r.summary
        for k in ("missing_mandatory_rows", "arithmetic_mismatches", "exact_duplicates", "probable_duplicates",
                  "development_pairs", "arithmetic_not_evaluable"):
            totals[k] += int(s.get(k) or 0)
        totals["unmapped_columns"] += sum(len(u["columns"]) for u in s.get("unmapped_source_columns") or [])
        totals["claims"] += int(s.get("total_claims") or 0)
    severity = dict(db.query(ValidationResult.severity, func.count())
                    .join(Report, Report.id == ValidationResult.report_id)
                    .filter(ValidationResult.tenant_id == tid, ValidationResult.status.in_(("FAIL", "REVIEW")))
                    .group_by(ValidationResult.severity).all())
    today = utcnow().date()
    days = [today - timedelta(days=i) for i in range(13, -1, -1)]
    per_day = Counter()
    rows_day = Counter()
    for r in reports:
        created = r.created_at.date() if isinstance(r.created_at, datetime) else r.created_at
        if created >= days[0]:
            per_day[created] += 1
            rows_day[created] += r.rows_processed or 0
    since = utcnow() - timedelta(hours=24)
    jobs = db.query(Job).filter(Job.tenant_id == tid, Job.created_at >= since).all()
    durations = [(j.finished_at - j.started_at).total_seconds() for j in jobs
                 if j.status == "SUCCEEDED" and j.started_at and j.finished_at]
    unread = db.query(Alert).filter(Alert.tenant_id == tid, Alert.acknowledged.is_(False))
    recs = []
    for r in complete[:5]:
        for rec in (r.summary.get("recommendations") or [])[:3]:
            if rec["severity"] in ("CRITICAL", "HIGH", "MEDIUM"):
                recs.append({**rec, "report_id": r.id, "file_name": r.file_name})
    activity = (db.query(AuditLogEntry).filter(AuditLogEntry.tenant_id == tid)
                .order_by(AuditLogEntry.seq.desc()).limit(15).all())
    workers = job_service.live_workers(db)
    return {
        "reports": {"total": len(reports), "complete": by_status["COMPLETE"],
                    "awaiting_review": by_status["WAITING_FOR_REVIEW"],
                    "in_flight": sum(by_status[s] for s in _IN_FLIGHT), "failed": by_status["FAILED"]},
        "received": {"last_24h": sum(1 for r in reports if (_age_s(r.created_at) or 1e9) < 86400),
                     "last_7d": sum(1 for r in reports if (_age_s(r.created_at) or 1e9) < 7 * 86400)},
        "findings": {"open_by_severity": severity, **totals},
        "trend": [{"date": d.isoformat(), "reports": per_day[d], "rows": rows_day[d]} for d in days],
        "processing": {"worker_available": bool(workers), "workers_alive": len(workers),
                       "jobs_24h": len(jobs), "failed_24h": sum(1 for j in jobs if j.status == "FAILED"),
                       "median_job_s": round(sorted(durations)[len(durations) // 2], 2) if durations else None},
        "alerts": {"unread": unread.count(),
                   "latest": [AlertOut.model_validate(a).model_dump(mode="json")
                              for a in unread.order_by(Alert.created_at.desc()).limit(6)]},
        "latest_reports": [report_out(db, r).model_dump(mode="json") for r in reports[:8]],
        "in_flight_reports": [report_out(db, r).model_dump(mode="json")
                              for r in reports if r.status in _IN_FLIGHT][:6],
        "recommendations": recs[:8],
        "activity": [AuditLogOut.model_validate(e).model_dump(mode="json") for e in activity],
    }


# ------------------------------------------------------------------ work queue

_PRIORITY = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "INFO": 3}


@router.get("/work-queue")
def work_queue(ctx: Context = Depends(get_context), db: Session = Depends(get_db)) -> dict:
    tid = ctx.tenant_id
    items: list[dict] = []

    def add(kind, priority, title, detail, report=None, href=None, count=1):
        items.append({"kind": kind, "priority": priority, "title": title, "detail": detail, "count": count,
                      "report_id": report.id if report else None, "file_name": report.file_name if report else None,
                      "href": href or (f"/reports/{report.id}" if report else None)})

    workers = job_service.live_workers(db)
    reports = db.query(Report).filter(Report.tenant_id == tid).all()
    for r in reports:
        if r.status == "WAITING_FOR_REVIEW":
            pending = db.query(Sheet).filter(Sheet.report_id == r.id, Sheet.status == "PENDING_CONFIRMATION").count()
            add("mapping", "HIGH", f"Confirm the mapping for {r.file_name}",
                f"{pending} sheet(s) awaiting confirmation before the report can be produced.", r,
                href=f"/upload?reportId={r.id}", count=pending)
        elif r.status == "FAILED":
            add("failed", "HIGH", f"Processing failed: {r.file_name}", r.processing_error or "See the report.", r)
        elif r.status in _IN_FLIGHT and not workers:
            add("stalled", "CRITICAL", f"{r.file_name} is waiting for the processing service",
                "No processing worker is running, so this file cannot start. Start the worker (or the "
                "development stack), then it will be picked up automatically.", r)
    crit = (db.query(ValidationResult.report_id, func.count()).filter(
        ValidationResult.tenant_id == tid, ValidationResult.severity == "CRITICAL",
        ValidationResult.status == "FAIL").group_by(ValidationResult.report_id).all())
    by_id = {r.id: r for r in reports}
    for rid, n in crit:
        if rid in by_id:
            add("critical", "CRITICAL", f"{n} critical finding(s) in {by_id[rid].file_name}",
                "Rows missing required data or sheets that could not be mapped.", by_id[rid],
                href=f"/exceptions?reportId={rid}&severity=CRITICAL", count=n)
    dup_rows = (db.query(ValidationResult.report_id, ValidationResult.extra)
                .filter(ValidationResult.tenant_id == tid, ValidationResult.check_type == "DUPLICATE").all())
    unreviewed = Counter(rid for rid, extra in dup_rows if not (extra or {}).get("review_status"))
    for rid, n in unreviewed.items():
        if rid in by_id:
            add("duplicates", "MEDIUM", f"{n} duplicate candidate(s) to review in {by_id[rid].file_name}",
                "Confirm or dismiss each pair; nothing is merged automatically.", by_id[rid],
                href=f"/duplicates?reportId={rid}", count=n)
    today = date.today()
    overdue = (db.query(Obligation).filter(Obligation.tenant_id == tid, Obligation.status != "RESOLVED",
                                           Obligation.deadline < today).count())
    if overdue:
        add("obligations", "HIGH", f"{overdue} overdue follow-up(s)", "Assigned follow-ups past their deadline.",
            href="/todo", count=overdue)
    failed_exports = db.query(Delivery).filter(Delivery.tenant_id == tid, Delivery.status != "DELIVERED",
                                               Delivery.created_at >= utcnow() - timedelta(days=7)).count()
    if failed_exports:
        add("exports", "MEDIUM", f"{failed_exports} export(s) not delivered in the last 7 days",
            "See Exports for the reason.", href="/exports", count=failed_exports)
    items.sort(key=lambda i: (_PRIORITY[i["priority"]], -i["count"]))
    return {"items": items, "total": len(items)}


# ------------------------------------------------------------------ deliveries (outbound)

class DeliveryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    report_id: str
    kind: str
    channel: str
    destination: str | None
    file_name: str
    size_bytes: int | None
    status: str
    error: str | None
    created_by: str | None
    created_at: UtcDatetime
    completed_at: UtcDatetime | None


class DeliveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    kind: Literal["claims_csv", "exceptions_csv", "audit_csv"]
    channel: Literal["email"]
    recipient: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@router.get("/deliveries", response_model=Page[DeliveryOut])
def list_deliveries(paging: Paging = Depends(), ctx: Context = Depends(get_context),
                    db: Session = Depends(get_db)) -> Page[DeliveryOut]:
    q = db.query(Delivery).filter(Delivery.tenant_id == ctx.tenant_id)
    total = q.count()
    rows = q.order_by(Delivery.created_at.desc()).limit(paging.limit).offset(paging.offset).all()
    return Page(items=[DeliveryOut.model_validate(d) for d in rows], total=total, limit=paging.limit,
                offset=paging.offset)


@router.post("/reports/{report_id}/deliveries", response_model=DeliveryOut, status_code=201)
def create_delivery(report_id: str, body: DeliveryRequest, ctx: Context = Depends(require_writer),
                    db: Session = Depends(get_db)) -> DeliveryOut:
    report = get_report_or_404(db, ctx, report_id)
    if report.status != "COMPLETE":
        raise HTTPException(status_code=409, detail="Outputs can be sent once the report is complete.")
    limiter.check("delivery", ctx.tenant_id, limit=30, window_s=3600)
    d = delivery_service.send_email(db, ctx.tenant_id, report, body.kind, body.recipient.lower(), ctx.actor,
                                    ctx.user_id)
    db.commit()
    return DeliveryOut.model_validate(d)


# ------------------------------------------------------------------ channels

@router.get("/channels")
def channels(ctx: Context = Depends(get_context)) -> dict:
    """Inbound and outbound channels and whether each is live on this server.
    Planned connectors are listed as such -- never shown as working."""
    email_out = delivery_service.email_configured()
    return {
        "inbound": [
            {"id": "upload", "name": "Web upload", "status": "active",
             "detail": "Drag and drop .xlsx, .xlsm, .xls or .csv on the Intake page."},
            {"id": "api", "name": "API", "status": "active",
             "detail": "POST /api/v1/reports/upload (multipart, session auth + CSRF)."},
            {"id": "email", "name": "E-mail inbox", "status": "planned",
             "detail": "Forward bordereaux to a dedicated address; attachments ingested automatically."},
            {"id": "sftp", "name": "SFTP drop", "status": "planned", "detail": "Poll a partner SFTP folder on a schedule."},
            {"id": "cloud", "name": "Cloud storage", "status": "planned",
             "detail": "Watch a SharePoint / S3 / Google Drive folder."},
            {"id": "schedule", "name": "Scheduled import", "status": "planned",
             "detail": "Fetch a recurring submission at a set time."},
        ],
        "outbound": [
            {"id": "download", "name": "Download", "status": "active", "detail": "Claims, exceptions and audit CSV."},
            {"id": "email", "name": "E-mail", "status": "active" if email_out else "not_configured",
             "detail": "Send outputs to a recipient." + ("" if email_out else " Set SMTP_HOST on the server to enable.")},
            {"id": "webhook", "name": "Webhook / API push", "status": "planned",
             "detail": "Post structured results to another system."},
            {"id": "sftp_out", "name": "SFTP delivery", "status": "planned", "detail": "Drop outputs on a partner SFTP."},
        ],
        "pipeline": ["Receive", "Validate file", "Read workbook", "Map columns", "Validate data",
                     "Check duplicates", "Reconcile", "Report", "Deliver"],
        "limits": {"max_upload_mb": config.MAX_UPLOAD_BYTES // (1024 * 1024), "ai_mapping": bool(config.ANTHROPIC_API_KEY)},
    }


# ------------------------------------------------------------------ processing history

@router.get("/reports/{report_id}/jobs", response_model=list[JobOut])
def report_jobs(report_id: str, ctx: Context = Depends(get_context), db: Session = Depends(get_db)) -> list[JobOut]:
    report = get_report_or_404(db, ctx, report_id)
    jobs = db.query(Job).filter(Job.report_id == report.id).order_by(Job.created_at).all()
    return [JobOut.model_validate(j) for j in jobs]


# ------------------------------------------------------------------ exception review

class ExceptionReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    review_status: Literal["open", "in_review", "resolved", "accepted", "false_positive"]
    assignee: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=2000)


@router.patch("/reports/{report_id}/exceptions/{validation_result_id}")
def review_exception(report_id: str, validation_result_id: str, body: ExceptionReviewRequest,
                     ctx: Context = Depends(require_writer), db: Session = Depends(get_db)) -> dict:
    """Records a reviewer's decision on a finding. The underlying data is
    never changed; the decision, who made it and why are audited."""
    report = get_report_or_404(db, ctx, report_id)
    vr = (db.query(ValidationResult).filter(ValidationResult.id == validation_result_id,
                                            ValidationResult.report_id == report.id).first())
    if vr is None:
        raise HTTPException(status_code=404, detail="Finding not found.")
    before = dict(vr.extra or {})
    after = {**before, "review_status": body.review_status, "reviewed_by": ctx.actor,
             "reviewed_at": utcnow().isoformat()}
    if body.assignee is not None:
        after["assignee"] = body.assignee or None
    if body.note:
        after["note"] = body.note
    vr.extra = after
    audit_service.log_action(db, ctx.tenant_id, report.id, "EXCEPTION_STATUS_CHANGED", "EXCEPTION", vr.id,
                             before={k: before.get(k) for k in ("review_status", "assignee")},
                             after={k: after.get(k) for k in ("review_status", "assignee", "note")},
                             actor=ctx.actor, actor_user_id=ctx.user_id)
    db.commit()
    return {"validation_result_id": vr.id, "review_status": after["review_status"], "assignee": after.get("assignee"),
            "note": after.get("note"), "reviewed_by": ctx.actor}
