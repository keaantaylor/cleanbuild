"""Report lifecycle: upload (gate + store + enqueue), list, status, summary,
cancel, retry, delete, exports. Heavy work never runs here -- the API
only enqueues jobs for app/worker.py."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse
from sqlalchemy.orm import Session

from ..config import MAX_UPLOAD_BYTES, STORAGE_DIR
from ..database import get_db
from ..models._util import utcnow
from ..models.identity import Tenant
from ..models.reports import Report
from ..schemas.reports import Page, ReportOut, ReportSummaryOut
from ..security.auth import Context, require, require_reader, require_writer
from ..security.permissions import Permission
from ..security.file_guard import safe_display_name
from ..security.ratelimit import limiter
from ..services import (audit_pack_service, audit_service, delivery_service, export_service, idempotency, intake_service,
                        job_service, retention_service)
from ..services.storage import sha256_file
from .deps import Paging, get_report_or_404, latest_job, report_out

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])

_CHUNK = 1024 * 1024
_REJECT_STATUS = {"unsupported_type": 415, "compression_bomb": 413, "too_large_uncompressed": 413}


def _incoming_dir() -> Path:
    d = Path(STORAGE_DIR) / "incoming"
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    return d


@router.post("/upload", response_model=ReportOut, status_code=202)
def upload_report(file: UploadFile, sender: str | None = Form(default=None, max_length=200),
                  programme: str | None = Form(default=None, max_length=200),
                  idempotency_key: str | None = Header(default=None, alias=idempotency.HEADER),
                  ctx: Context = Depends(require_writer), db: Session = Depends(get_db)) -> ReportOut | JSONResponse:
    key = idempotency.validate_key(idempotency_key)
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
        verdict = intake_service.inspect(db, tenant_id=ctx.tenant_id, path=tmp, display_name=display, size=size,
                                         channel="upload", actor=ctx.actor, actor_user_id=ctx.user_id)
        if not verdict.accepted:
            db.commit()
            raise HTTPException(status_code=_REJECT_STATUS.get(verdict.code, 400), detail=verdict.reason)
        idem = None
        if key is not None:
            claimed = idempotency.claim(
                db, tenant_id=ctx.tenant_id, user_id=ctx.user_id, scope="reports.upload", key=key,
                request_fingerprint=idempotency.fingerprint(sha256_file(tmp), display, sender or "", programme or ""))
            if isinstance(claimed, JSONResponse):
                return claimed
            idem = claimed
        tenant = db.get(Tenant, ctx.tenant_id)
        if verdict.kind is None or tenant is None:  # an accepted verdict always names its kind
            raise HTTPException(status_code=415, detail="Unsupported file type.")
        try:
            # Write-once, content-addressed original, stored before the database
            # rows: if the transaction fails, the object is merely unused.
            report = intake_service.create_report(
                db, tenant=tenant, path=tmp, verdict=verdict, display_name=display, size=size, channel="upload",
                actor=ctx.actor, actor_user_id=ctx.user_id, sender=sender, programme=programme)
            replay = (idempotency.complete(idem, 202, report_out(db, report).model_dump(mode="json"))
                      if idem is not None else None)
            db.commit()
        except Exception:
            db.rollback()
            raise
        if replay is not None:
            return replay
        db.refresh(report)
        return report_out(db, report)
    finally:
        tmp.unlink(missing_ok=True)


@router.get("", response_model=Page[ReportOut])
def list_reports(paging: Paging = Depends(), ctx: Context = Depends(require_reader),
                 db: Session = Depends(get_db)) -> Page[ReportOut]:
    q = db.query(Report).filter(Report.tenant_id == ctx.tenant_id)
    total = q.count()
    rows = q.order_by(Report.created_at.desc()).limit(paging.limit).offset(paging.offset).all()
    return Page(items=[report_out(db, r) for r in rows], total=total, limit=paging.limit, offset=paging.offset)


@router.get("/{report_id}", response_model=ReportOut)
def get_report(report_id: str, ctx: Context = Depends(require_reader), db: Session = Depends(get_db)) -> ReportOut:
    return report_out(db, get_report_or_404(db, ctx, report_id))


@router.get("/{report_id}/summary", response_model=ReportSummaryOut)
def get_report_summary(report_id: str, ctx: Context = Depends(require_reader),
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
def delete_report(report_id: str, ctx: Context = Depends(require(Permission.DATA_DELETE)), db: Session = Depends(get_db)) -> Response:
    report = get_report_or_404(db, ctx, report_id)
    try:
        retention_service.delete_report(db, report, "REPORT_DELETED", actor=ctx.actor, actor_user_id=ctx.user_id)
    except job_service.JobConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return Response(status_code=204)


# ------------------------------------------------------------------ exports

def _export(db: Session, ctx: Context, report: Report, kind: str) -> StreamingResponse:
    header, rows = export_service.export_rows(db, ctx.tenant_id, report, kind)
    name = export_service.file_name(report, kind)
    audit_service.log_action(db, ctx.tenant_id, report.id, "EXPORT_GENERATED", "REPORT", report.id,
                             after={"export": kind, "channel": "download"}, actor=ctx.actor, actor_user_id=ctx.user_id)
    delivery_service.record(db, ctx.tenant_id, report.id, kind, "download", None, name, None, "DELIVERED", None,
                            ctx.actor)
    db.commit()
    return StreamingResponse(export_service.csv_stream(header, rows), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/{report_id}/export/claims.csv")
def export_claims(report_id: str, ctx: Context = Depends(require_reader), db: Session = Depends(get_db)):
    """One line per extracted claim row with lineage (sheet + source row),
    unmapped source values and the findings raised against it."""
    return _export(db, ctx, get_report_or_404(db, ctx, report_id), "claims_csv")


@router.get("/{report_id}/export/exceptions.csv")
def export_exceptions(report_id: str, ctx: Context = Depends(require_reader), db: Session = Depends(get_db)):
    return _export(db, ctx, get_report_or_404(db, ctx, report_id), "exceptions_csv")


@router.get("/{report_id}/export/audit.csv")
def export_audit(report_id: str, ctx: Context = Depends(require_reader), db: Session = Depends(get_db)):
    return _export(db, ctx, get_report_or_404(db, ctx, report_id), "audit_csv")

@router.get("/{report_id}/audit-pack.zip")
def audit_pack(report_id: str, ctx: Context = Depends(require_reader), db: Session = Depends(get_db)) -> Response:
    """Everything an auditor needs for this report in one ZIP, with a manifest of SHA-256 hashes."""
    report = get_report_or_404(db, ctx, report_id)
    if report.status != "COMPLETE":
        raise HTTPException(status_code=409, detail="The audit pack is available once the report is processed.")
    summary = report.summary if isinstance(report.summary, dict) else {}
    statement = str(summary.get("coverage_statement") or "No coverage statement was recorded.")
    try:
        body = audit_pack_service.build(db, report, statement, ctx.actor, utcnow())
    except audit_pack_service.PackIntegrityError as exc:
        raise HTTPException(status_code=409, detail="The stored original no longer matches the file uploaded; "
                            "the pack was not built.") from exc
    name = f"truebind_{report.id}_audit_pack.zip"
    audit_service.log_action(db, ctx.tenant_id, report.id, "AUDIT_PACK_EXPORTED", "REPORT", report.id,
                             after={"export": "audit_pack", "sha256": hashlib.sha256(body).hexdigest(),
                                    "bytes": len(body)}, actor=ctx.actor, actor_user_id=ctx.user_id)
    delivery_service.record(db, ctx.tenant_id, report.id, "audit_pack", "download", None, name, None, "DELIVERED",
                            None, ctx.actor)
    db.commit()
    return Response(body, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})
