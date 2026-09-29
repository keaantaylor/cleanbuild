"""P8 Sender pre-flight portal: coverholders and TPAs check a bordereau before sending it.

POST /api/v1/sender/preflight    run the checks on a file and return what would fail (sender:submit)
POST /api/v1/sender/submissions  send the file to the organisation's inbox          (sender:submit)
GET  /api/v1/sender/submissions  the sender's own submissions and their status       (sender:submit)

Pre-flight stores nothing but an audit event (file SHA-256 and counts): the
file is read, mapped by exact header aliases only (no AI -- nothing leaves
the server and no suggestion is applied unconfirmed), validated and thrown
away. A submission goes through the same intake gate as any upload and
lands in the organisation's inbox for its own analysts to map and process.
A sender sees only what they sent -- never the organisation's other data or
its findings.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import MAX_UPLOAD_BYTES, STORAGE_DIR
from ..database import get_db
from ..models.identity import Tenant
from ..models.reports import Report
from ..security.auth import Context, require
from ..security.file_guard import Verdict, safe_display_name
from ..security.permissions import Permission
from ..security.ratelimit import limiter
from ..services import audit_service, intake_service, pipeline_service
from ..services.storage import sha256_file

router = APIRouter(prefix="/api/v1/sender", tags=["sender"])
_sender = require(Permission.SENDER_SUBMIT)
_CHUNK = 1024 * 1024
_SUFFIXES = {".xlsx", ".xlsm", ".xls", ".csv"}
PREFLIGHT_MAX_ROWS = 20_000
_REJECT_STATUS = {"unsupported_type": 415, "compression_bomb": 413, "too_large_uncompressed": 413}


class PreflightSheet(BaseModel):
    sheet_name: str
    rows: int
    mapped_fields: list[str]
    missing_required_fields: list[str]
    unmapped_columns: list[str]
    notes: list[str]


class PreflightIssue(BaseModel):
    sheet_name: str | None
    row_number: int | None
    check: str
    message: str


class PreflightOut(BaseModel):
    file_name: str
    sha256: str
    ready: bool
    verdict: str
    rows: int
    missing_mandatory_rows: int
    arithmetic_mismatches: int
    exact_duplicates: int
    sheets: list[PreflightSheet]
    issues: list[PreflightIssue]
    issues_total: int
    coverage_statement: str


class SubmissionOut(BaseModel):
    id: str
    file_name: str
    status: str
    created_at: datetime
    rows_total: int


def _receive(file: UploadFile) -> tuple[Path, int, str]:
    d = Path(STORAGE_DIR) / "incoming"
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    display = safe_display_name(file.filename)
    suffix = Path(display).suffix.lower()
    fd, name = tempfile.mkstemp(dir=d, prefix="sender-", suffix=suffix if suffix in _SUFFIXES else "")
    size = 0
    with os.fdopen(fd, "wb") as out:
        while chunk := file.file.read(_CHUNK):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                Path(name).unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="The file is larger than the upload limit.")
            out.write(chunk)
    return Path(name), size, display


def _gate(db: Session, ctx: Context, path: Path, display: str, size: int, channel: str) -> Verdict:
    verdict = intake_service.inspect(
        db,
        tenant_id=ctx.tenant_id,
        path=path,
        display_name=display,
        size=size,
        channel=channel,
        actor=ctx.actor,
        actor_user_id=ctx.user_id,
    )
    if not verdict.accepted:
        db.commit()
        raise HTTPException(status_code=_REJECT_STATUS.get(verdict.code or "", 400), detail=verdict.reason)
    return verdict


def _preflight(path: Path, display: str) -> PreflightOut:
    from bordereaux.schema import FIELDS

    names = {f.code: f.name for f in FIELDS}
    sheets = pipeline_service.load_workbook(path, source_stem=Path(display).stem)
    usable = [s for s in sheets if not s.skipped]
    rows = sum(len(s.raw) for s in usable)
    if rows > PREFLIGHT_MAX_ROWS:
        raise HTTPException(
            status_code=413,
            detail=f"Pre-flight checks files of up to {PREFLIGHT_MAX_ROWS:,} rows; submit larger files directly.",
        )
    proposals = pipeline_service.propose_mapping_for_workbook(sheets)  # exact aliases only, no AI
    confirmed: dict[str, dict[str, str]] = {}
    out_sheets = []
    for p in proposals:
        chosen = {s.source_column: s.field_code for s in p.mapping.suggestions if s.field_code and s.method == "alias"}
        confirmed[p.sheet.sheet_name] = chosen
        mapped = set(chosen.values())
        out_sheets.append(
            PreflightSheet(
                sheet_name=p.sheet.sheet_name,
                rows=len(p.sheet.raw),
                mapped_fields=[names[c] for c in sorted(mapped)],
                missing_required_fields=[f.name for f in FIELDS if f.required and f.code not in mapped],
                unmapped_columns=[str(c) for c in p.sheet.raw.columns if str(c) not in chosen][:50],
                notes=list(p.sheet.notes),
            )
        )
    if not proposals:
        raise HTTPException(
            status_code=422, detail="No sheet in this file has a recognisable header row with data below it."
        )
    result = pipeline_service.run_workbook_pipeline(sheets, confirmed, proposals, source_name=display)
    health = result.health
    exc = result.validation_result.exceptions
    canon = result.canonical.reset_index(drop=True)
    src_sheet = canon["_source_sheet"].tolist() if "_source_sheet" in canon.columns else []
    src_row = canon["_source_row"].tolist() if "_source_row" in canon.columns else []
    issues: list[PreflightIssue] = []
    for pos, rule, detail in zip(
        exc["row_index"].tolist()[:200], exc["rule"].tolist(), exc["detail"].tolist(), strict=False
    ):
        i = int(pos)
        row_no = src_row[i] if i < len(src_row) else None
        issues.append(
            PreflightIssue(
                sheet_name=str(src_sheet[i]) if i < len(src_sheet) else None,
                row_number=int(row_no) if row_no is not None and row_no == row_no else None,
                check=str(rule),
                message=str(detail)[:300],
            )
        )
    for name, s in zip([s.sheet_name for s in out_sheets], out_sheets, strict=True):
        for miss in s.missing_required_fields:
            issues.insert(
                0,
                PreflightIssue(
                    sheet_name=name,
                    row_number=None,
                    check="MAPPING",
                    message=f"No column was recognised as '{miss}'. Rename the column header or add it before sending.",
                ),
            )
    blocking = (
        health.missing_mandatory_rows
        + health.arithmetic_mismatches
        + health.exact_duplicates
        + sum(len(s.missing_required_fields) for s in out_sheets)
    )
    return PreflightOut(
        file_name=display,
        sha256=sha256_file(path),
        ready=blocking == 0,
        verdict=(
            "Ready to send: no mandatory field, arithmetic or duplicate problems were found."
            if blocking == 0
            else "Fix the issues below before sending, or send it and explain them."
        ),
        rows=rows,
        missing_mandatory_rows=health.missing_mandatory_rows,
        arithmetic_mismatches=health.arithmetic_mismatches,
        exact_duplicates=health.exact_duplicates,
        sheets=out_sheets,
        issues=issues[:200],
        issues_total=len(exc) + sum(len(s.missing_required_fields) for s in out_sheets),
        coverage_statement=pipeline_service.coverage_statement(result.coverage),
    )


@router.post("/preflight", response_model=PreflightOut)
def preflight(file: UploadFile, ctx: Context = Depends(_sender), db: Session = Depends(get_db)) -> PreflightOut:
    limiter.check("preflight", ctx.user_id, limit=60, window_s=3600)
    path, size, display = _receive(file)
    try:
        _gate(db, ctx, path, display, size, "portal")
        out = _preflight(path, display)
    finally:
        path.unlink(missing_ok=True)
    audit_service.log_action(
        db,
        ctx.tenant_id,
        None,
        "SENDER_PREFLIGHT_RUN",
        "FILE",
        out.sha256[:36],
        after={
            "file_name": display,
            "sha256": out.sha256,
            "rows": out.rows,
            "ready": out.ready,
            "issues": out.issues_total,
        },
        actor=ctx.actor,
        actor_user_id=ctx.user_id,
    )
    db.commit()
    return out


@router.post("/submissions", response_model=SubmissionOut, status_code=202)
def submit(
    file: UploadFile,
    programme: str | None = Form(default=None, max_length=200),
    ctx: Context = Depends(_sender),
    db: Session = Depends(get_db),
) -> SubmissionOut:
    limiter.check("upload", ctx.user_id, limit=60, window_s=3600)
    path, size, display = _receive(file)
    try:
        verdict = _gate(db, ctx, path, display, size, "portal")
        tenant = db.get(Tenant, ctx.tenant_id)
        if tenant is None:  # pragma: no cover -- a signed-in member always has a tenant
            raise HTTPException(status_code=404, detail="Organisation not found.")
        report = intake_service.create_report(
            db,
            tenant=tenant,
            path=path,
            verdict=verdict,
            display_name=display,
            size=size,
            channel="portal",
            actor=ctx.actor,
            actor_user_id=ctx.user_id,
            sender=ctx.actor,
            programme=programme,
        )
        db.commit()
    finally:
        path.unlink(missing_ok=True)
    return SubmissionOut(
        id=report.id,
        file_name=report.file_name,
        status=report.status,
        created_at=report.created_at,
        rows_total=report.rows_total or 0,
    )


@router.get("/submissions", response_model=list[SubmissionOut])
def my_submissions(ctx: Context = Depends(_sender), db: Session = Depends(get_db)) -> list[SubmissionOut]:
    rows = (
        db.query(Report)
        .filter(Report.tenant_id == ctx.tenant_id, Report.created_by == ctx.user_id, Report.source_channel == "portal")
        .order_by(Report.created_at.desc())
        .limit(200)
    )
    return [
        SubmissionOut(
            id=r.id, file_name=r.file_name, status=r.status, created_at=r.created_at, rows_total=r.rows_total or 0
        )
        for r in rows
    ]
