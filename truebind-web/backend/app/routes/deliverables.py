"""Customer deliverables for a processed report: the annotated workbook, the
corrected copy, the query letter to the sender and the month-on-month check.
Every download is recorded in the audit trail and the deliveries list."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.reports import Report
from ..security.auth import Context, require_reader
from ..services import audit_service, deliverables, delivery_service, grid_view
from .deps import get_report_or_404, get_sheet_or_404

router = APIRouter(prefix="/api/v1/reports", tags=["deliverables"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _complete(db: Session, ctx: Context, report_id: str) -> Report:
    report = get_report_or_404(db, ctx, report_id)
    if report.status != "COMPLETE":
        raise HTTPException(status_code=409, detail="This is available once the report is processed.")
    return report


def _stem(report: Report) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", Path(report.file_name).stem)[:80] or "bordereau"


def _download(db: Session, ctx: Context, report: Report, kind: str, name: str, body: bytes, extra: dict | None = None):
    audit_service.log_action(db, ctx.tenant_id, report.id, "EXPORT_GENERATED", "REPORT", report.id,
                             after={"export": kind, "channel": "download", "bytes": len(body),
                                    "sha256": hashlib.sha256(body).hexdigest(), **(extra or {})},
                             actor=ctx.actor, actor_user_id=ctx.user_id)
    delivery_service.record(db, ctx.tenant_id, report.id, kind, "download", None, name, None, "DELIVERED", None,
                            ctx.actor)
    db.commit()
    return Response(body, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/{report_id}/export/annotated.xlsx")
def annotated_workbook(report_id: str, ctx: Context = Depends(require_reader), db: Session = Depends(get_db)):
    """The customer's own workbook with every claim-sheet cell coloured by
    result, a Review notes column, hover notes with the fix, an Issues sheet and
    a Review Summary. Source values are unchanged."""
    report = _complete(db, ctx, report_id)
    try:
        body = deliverables.annotated_workbook(db, report)
    except deliverables.SourceUnavailable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _download(db, ctx, report, "annotated_xlsx", f"{_stem(report)}_REVIEWED.xlsx", body)


@router.get("/{report_id}/export/corrected.xlsx")
def corrected_workbook(report_id: str, ctx: Context = Depends(require_reader), db: Session = Depends(get_db)):
    """A copy with only safe, reversible fixes applied, each on the Change Log
    sheet. Duplicates, arithmetic, reserves and ambiguous values are never changed."""
    report = _complete(db, ctx, report_id)
    try:
        body, changes = deliverables.corrected_workbook(db, report)
    except deliverables.SourceUnavailable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _download(db, ctx, report, "corrected_xlsx", f"{_stem(report)}_CORRECTED.xlsx", body,
                     {"changes": len(changes)})


@router.get("/{report_id}/query-letter")
def query_letter(report_id: str, ctx: Context = Depends(require_reader), db: Session = Depends(get_db)) -> dict:
    """A draft email to the sender: the findings only they can fix, grouped by
    issue, each with its sheet, cell and claim reference."""
    report = _complete(db, ctx, report_id)
    return deliverables.query_letter(db, report)


@router.get("/{report_id}/compare")
def month_on_month(report_id: str, previous_report_id: str | None = Query(default=None, max_length=36),
                   reserve_jump_pct: float = Query(default=50.0, ge=0, le=100000),
                   reserve_jump_min: float = Query(default=0.0, ge=0),
                   ctx: Context = Depends(require_reader), db: Session = Depends(get_db)) -> dict:
    """Month-on-month check against an earlier report: claims that vanished
    without closing, paid to date going down, reserves rising above a threshold."""
    current = _complete(db, ctx, report_id)
    if previous_report_id is None:  # default: the latest earlier processed report
        prev = (db.query(Report).filter(Report.tenant_id == ctx.tenant_id, Report.status == "COMPLETE",
                                        Report.id != current.id, Report.created_at <= current.created_at)
                .order_by(Report.created_at.desc()).first())
        if prev is None:
            raise HTTPException(status_code=409, detail="There is no earlier processed report to compare with.")
        previous_report_id = prev.id
    previous = _complete(db, ctx, previous_report_id)
    if previous.id == current.id:
        raise HTTPException(status_code=422, detail="Choose a different, earlier report to compare with.")
    return deliverables.month_on_month(db, current, previous, reserve_jump_pct, reserve_jump_min)


@router.get("/{report_id}/sheets/{sheet_id}/grid")
def sheet_grid(report_id: str, sheet_id: str, offset: int = Query(default=0, ge=0, le=2_000_000),
               limit: int = Query(default=100, ge=1, le=500), ctx: Context = Depends(require_reader),
               db: Session = Depends(get_db)) -> dict:
    """Inline preview of the source sheet, a page of rows at a time: each cell's
    original value, its review colour (ok / warn / err / grey) and the findings
    on it. Values are exactly as received."""
    report = _complete(db, ctx, report_id)
    sheet = get_sheet_or_404(db, ctx, report, sheet_id)
    try:
        page = grid_view.grid_page(db, report, sheet, offset, limit)
    except deliverables.SourceUnavailable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()  # the values cache, written on first use
    return page
