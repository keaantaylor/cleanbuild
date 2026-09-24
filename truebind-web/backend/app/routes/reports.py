"""Report lifecycle: upload (gate + store + enqueue), list, status, summary,
cancel, retry, delete, exports. Heavy work never runs here -- the API
only enqueues jobs for app/worker.py."""

from __future__ import annotations

import csv
import io
import json
import os
import tempfile
from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import MAX_UPLOAD_BYTES, STORAGE_DIR
from ..database import get_db, get_session_factory, set_tenant
from ..models._util import new_uuid, utcnow
from ..models.audit import AuditLogEntry
from ..models.identity import Tenant
from ..models.reports import ClaimRow, Report, Sheet, ValidationResult
from ..schemas.reports import Page, ReportOut, ReportSummaryOut
from ..security.auth import Context, get_context, require_writer
from ..security.file_guard import inspect_upload, safe_display_name
from ..security.ratelimit import limiter
from ..services import audit_service, job_service, retention_service
from ..services.storage import sha256_file, source_key, store
from .deps import Paging, get_report_or_404, latest_job, report_out

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])

_CHUNK = 1024 * 1024
_REJECT_STATUS = {"unsupported_type": 415, "compression_bomb": 413, "too_large_uncompressed": 413}


def _incoming_dir() -> Path:
    d = Path(STORAGE_DIR) / "incoming"
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    return d


@router.post("/upload", response_model=ReportOut, status_code=202)
def upload_report(file: UploadFile, ctx: Context = Depends(require_writer), db: Session = Depends(get_db)) -> ReportOut:
    limiter.check("upload", ctx.user_id, limit=60, window_s=3600)
    display = safe_display_name(file.filename)
    fd, tmp_name = tempfile.mkstemp(dir=_incoming_dir(), prefix="up-")
    tmp = Path(tmp_name)
    size = 0
    try:
        with os.fdopen(fd, "wb") as out:
            while chunk := file.file.read(_CHUNK):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail=f"The file is larger than the "
                                        f"{MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit.")
                out.write(chunk)
        verdict = inspect_upload(tmp, display)
        if not verdict.accepted:
            audit_service.log_action(db, ctx.tenant_id, None, "UPLOAD_REJECTED", "REPORT", new_uuid(),
                                     after={"file_name": display, "size": size, "sha256": sha256_file(tmp),
                                            "code": verdict.code},
                                     actor=ctx.actor, actor_user_id=ctx.user_id)
            db.commit()
            raise HTTPException(status_code=_REJECT_STATUS.get(verdict.code, 400), detail=verdict.reason)
        tenant = db.get(Tenant, ctx.tenant_id)
        report = Report(tenant_id=ctx.tenant_id, created_by=ctx.user_id, file_name=display, file_size_bytes=size,
                        file_kind=verdict.kind, status="UPLOADED", ingest_notes={"file_notes": verdict.notes},
                        expires_at=utcnow() + timedelta(days=tenant.retention_days), updated_at=utcnow())
        db.add(report)
        db.flush()
        key = source_key(ctx.tenant_id, report.id, verdict.kind)
        report.source_sha256 = store.put_file(key, tmp)
        report.storage_key = key
        try:
            audit_service.log_action(db, ctx.tenant_id, report.id, "REPORT_UPLOADED", "REPORT", report.id,
                                     after={"file_name": display, "size": size, "sha256": report.source_sha256,
                                            "kind": verdict.kind, "notes": verdict.notes},
                                     actor=ctx.actor, actor_user_id=ctx.user_id)
            job_service.enqueue(db, report, "INGEST", actor=ctx.actor, actor_user_id=ctx.user_id)
            db.commit()
        except Exception:
            db.rollback()
            store.delete_report(ctx.tenant_id, report.id)
            raise
        db.refresh(report)
        return report_out(db, report)
    finally:
        tmp.unlink(missing_ok=True)


@router.get("", response_model=Page[ReportOut])
def list_reports(paging: Paging = Depends(), ctx: Context = Depends(get_context),
                 db: Session = Depends(get_db)) -> Page[ReportOut]:
    q = db.query(Report).filter(Report.tenant_id == ctx.tenant_id)
    total = q.count()
    rows = q.order_by(Report.created_at.desc()).limit(paging.limit).offset(paging.offset).all()
    return Page(items=[report_out(db, r) for r in rows], total=total, limit=paging.limit, offset=paging.offset)


@router.get("/{report_id}", response_model=ReportOut)
def get_report(report_id: str, ctx: Context = Depends(get_context), db: Session = Depends(get_db)) -> ReportOut:
    return report_out(db, get_report_or_404(db, ctx, report_id))


@router.get("/{report_id}/summary", response_model=ReportSummaryOut)
def get_report_summary(report_id: str, ctx: Context = Depends(get_context),
                       db: Session = Depends(get_db)) -> ReportSummaryOut:
    report = get_report_or_404(db, ctx, report_id)
    return ReportSummaryOut(report=report_out(db, report), summary=report.summary)


@router.post("/{report_id}/cancel", response_model=ReportOut)
def cancel_report(report_id: str, ctx: Context = Depends(require_writer), db: Session = Depends(get_db)) -> ReportOut:
    report = get_report_or_404(db, ctx, report_id)
    if not job_service.request_cancel(db, report, actor=ctx.actor, actor_user_id=ctx.user_id):
        raise HTTPException(status_code=409, detail="There is no queued or running job to cancel.")
    audit_service.log_action(db, ctx.tenant_id, report.id, "JOB_CANCEL_REQUESTED", "REPORT", report.id,
                             actor=ctx.actor, actor_user_id=ctx.user_id)
    db.commit()
    db.refresh(report)
    return report_out(db, report)


@router.post("/{report_id}/retry", response_model=ReportOut, status_code=202)
def retry_report(report_id: str, ctx: Context = Depends(require_writer), db: Session = Depends(get_db)) -> ReportOut:
    report = get_report_or_404(db, ctx, report_id)
    last = latest_job(db, report.id)
    if report.status != "FAILED" or last is None:
        raise HTTPException(status_code=409, detail="Only a failed report can be retried.")
    try:
        job_service.enqueue(db, report, last.kind, actor=ctx.actor, actor_user_id=ctx.user_id)
    except job_service.JobConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    db.refresh(report)
    return report_out(db, report)


@router.delete("/{report_id}", status_code=204)
def delete_report(report_id: str, ctx: Context = Depends(require_writer), db: Session = Depends(get_db)) -> Response:
    report = get_report_or_404(db, ctx, report_id)
    try:
        retention_service.delete_report(db, report, "REPORT_DELETED", actor=ctx.actor, actor_user_id=ctx.user_id)
    except job_service.JobConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return Response(status_code=204)


# ------------------------------------------------------------------ exports

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")


def csv_safe(v):
    """Neutralise spreadsheet formula injection (OWASP CSV Injection): text
    beginning with a formula trigger is prefixed with a quote. Numbers are
    left as numbers (a negative amount stays numeric)."""
    if v is None:
        return ""
    if isinstance(v, str) and v.startswith(_FORMULA_PREFIXES):
        return "'" + v
    return v


def _csv_stream(header: list[str], rows_iter):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    n = 0
    for row in rows_iter:
        w.writerow([csv_safe(v) for v in row])
        n += 1
        if n % 2000 == 0:
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate()
    yield buf.getvalue()


def _stream_query(tenant_id: str, stmt):
    """Rows for a streamed body, read on a session owned by the generator:
    the request-scoped session may be closed before the body is sent."""
    db = get_session_factory()()
    try:
        set_tenant(db, tenant_id)
        yield from db.execute(stmt.execution_options(yield_per=5000))
    finally:
        db.close()


def _export(db: Session, ctx: Context, report: Report, name: str, header, rows) -> StreamingResponse:
    audit_service.log_action(db, ctx.tenant_id, report.id, "EXPORT_GENERATED", "REPORT", report.id,
                             after={"export": name}, actor=ctx.actor, actor_user_id=ctx.user_id)
    db.commit()
    return StreamingResponse(_csv_stream(header, rows), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="truebind_{report.id}_{name}.csv"'})


_CLAIM_EXPORT_COLS = [
    ("claim_reference", ClaimRow.claim_reference), ("insured_name", ClaimRow.insured_name),
    ("policy_reference", ClaimRow.policy_reference), ("claim_status", ClaimRow.claim_status),
    ("date_of_loss", ClaimRow.date_of_loss), ("date_notified", ClaimRow.date_notified),
    ("reporting_period", ClaimRow.reporting_period), ("currency", ClaimRow.currency),
    ("paid_this_month", ClaimRow.paid_this_month), ("previously_paid", ClaimRow.previously_paid),
    ("paid_to_date", ClaimRow.paid_amount), ("reserve", ClaimRow.reserve_amount),
    ("fees_paid_this_month", ClaimRow.fees_paid_this_month), ("fees_previously_paid", ClaimRow.fees_previously_paid),
    ("fees_reserve", ClaimRow.fees_reserve), ("fees_paid_to_date", ClaimRow.fees_paid_to_date), ("total_incurred_indemnity", ClaimRow.incurred_indemnity),
    ("total_incurred_incl_fees", ClaimRow.incurred_amount),
]


@router.get("/{report_id}/export/claims.csv")
def export_claims(report_id: str, ctx: Context = Depends(get_context), db: Session = Depends(get_db)):
    """One line per extracted claim row with lineage (sheet + source row)
    and the findings raised against it."""
    report = get_report_or_404(db, ctx, report_id)
    sheet_names = dict(db.query(Sheet.id, Sheet.sheet_name).filter(Sheet.report_id == report.id).all())
    findings: dict[str, list[str]] = {}
    for crid, rule, status in (db.query(ValidationResult.claim_row_id, ValidationResult.rule, ValidationResult.status)
                               .filter(ValidationResult.report_id == report.id)):
        findings.setdefault(crid, []).append(f"{rule}:{status}")
    stmt = (select(ClaimRow.id, ClaimRow.sheet_id, ClaimRow.source_row_number, *[c for _, c in _CLAIM_EXPORT_COLS],
                   ClaimRow.unmapped_values)
            .where(ClaimRow.report_id == report.id).order_by(ClaimRow.sheet_id, ClaimRow.row_index))
    header = (["sheet_name", "source_row_number"] + [n for n, _ in _CLAIM_EXPORT_COLS]
              + ["unmapped_source_values", "findings"])

    def rows():
        for r in _stream_query(ctx.tenant_id, stmt):
            extra = json.dumps(r[-1], ensure_ascii=False, sort_keys=True) if r[-1] else ""
            yield [sheet_names.get(r[1]), r[2], *r[3:-1], extra, "; ".join(findings.get(r[0], []))]
    return _export(db, ctx, report, "claims", header, rows())


@router.get("/{report_id}/export/exceptions.csv")
def export_exceptions(report_id: str, ctx: Context = Depends(get_context), db: Session = Depends(get_db)):
    report = get_report_or_404(db, ctx, report_id)
    sheet_names = dict(db.query(Sheet.id, Sheet.sheet_name).filter(Sheet.report_id == report.id).all())
    stmt = (select(ClaimRow.sheet_id, ClaimRow.source_row_number, ClaimRow.claim_reference, ValidationResult.check_type,
                   ValidationResult.rule, ValidationResult.status, ValidationResult.severity, ValidationResult.message)
            .join(ClaimRow, ClaimRow.id == ValidationResult.claim_row_id)
            .where(ValidationResult.report_id == report.id)
            .order_by(ClaimRow.sheet_id, ClaimRow.row_index))

    def rows():
        for r in _stream_query(ctx.tenant_id, stmt):
            yield [sheet_names.get(r[0]), *r[1:]]
    return _export(db, ctx, report, "exceptions",
                   ["sheet_name", "source_row_number", "claim_reference", "check_type", "rule", "status",
                    "severity", "message"], rows())


@router.get("/{report_id}/export/audit.csv")
def export_audit(report_id: str, ctx: Context = Depends(get_context), db: Session = Depends(get_db)):
    report = get_report_or_404(db, ctx, report_id)
    entries = (db.query(AuditLogEntry).filter(AuditLogEntry.tenant_id == ctx.tenant_id,
                                              AuditLogEntry.report_id == report.id)
               .order_by(AuditLogEntry.seq).all())
    rows = ([e.seq, e.created_at.isoformat(), e.action_type, e.entity_type, e.entity_id, e.actor,
             e.before_value, e.after_value, e.entry_hash] for e in entries)
    return _export(db, ctx, report, "audit",
                   ["seq", "timestamp", "action_type", "entity_type", "entity_id", "actor", "before", "after",
                    "entry_hash"], rows)

