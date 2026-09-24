"""Shared route helpers. Every lookup is scoped to the caller's tenant: an id
from another tenant is indistinguishable from an id that does not exist
(404, never 403), so ids cannot be probed across tenants."""

from __future__ import annotations

from fastapi import HTTPException, Query
from sqlalchemy.orm import Session

from ..models.jobs import Job
from ..models.reports import Report, Sheet
from ..schemas.reports import JobOut, ReportOut
from ..security.auth import Context


def get_report_or_404(db: Session, ctx: Context, report_id: str) -> Report:
    report = db.query(Report).filter(Report.id == report_id, Report.tenant_id == ctx.tenant_id).first()
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found.")
    return report


def get_sheet_or_404(db: Session, ctx: Context, report: Report, sheet_id: str) -> Sheet:
    sheet = (db.query(Sheet)
             .filter(Sheet.id == sheet_id, Sheet.report_id == report.id, Sheet.tenant_id == ctx.tenant_id).first())
    if sheet is None:
        raise HTTPException(status_code=404, detail="Sheet not found.")
    return sheet


def latest_job(db: Session, report_id: str) -> Job | None:
    return db.query(Job).filter(Job.report_id == report_id).order_by(Job.created_at.desc()).first()


def report_out(db: Session, report: Report) -> ReportOut:
    out = ReportOut.model_validate(report)
    job = latest_job(db, report.id)
    out.job = JobOut.model_validate(job) if job is not None else None
    return out


class Paging:
    def __init__(self, limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0, le=10_000_000)):
        self.limit, self.offset = limit, offset
