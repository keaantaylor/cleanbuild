from __future__ import annotations

import shutil

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.reports import Report
from ..schemas.reports import ExcludedRowOut, ReportOut, ReportSummaryOut
from ..services import audit_service, export_service, persistence_service
from .deps import get_report_or_404, stored_upload_dir

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


@router.get("", response_model=list[ReportOut])
def list_reports(db: Session = Depends(get_db)) -> list[ReportOut]:
    reports = db.query(Report).order_by(Report.created_at.desc()).all()
    return [ReportOut.model_validate(r) for r in reports]


@router.get("/{report_id}", response_model=ReportOut)
def get_report(report_id: str, db: Session = Depends(get_db)) -> ReportOut:
    return ReportOut.model_validate(get_report_or_404(db, report_id))


@router.get("/{report_id}/summary", response_model=ReportSummaryOut)
def get_report_summary(report_id: str, db: Session = Depends(get_db)) -> ReportSummaryOut:
    report = get_report_or_404(db, report_id)
    summary = persistence_service.compute_report_summary(db, report)
    return ReportSummaryOut(report=ReportOut.model_validate(report), **summary)


@router.get("/{report_id}/excluded-rows", response_model=list[ExcludedRowOut])
def list_excluded_rows(report_id: str, db: Session = Depends(get_db)) -> list[ExcludedRowOut]:
    get_report_or_404(db, report_id)
    return [ExcludedRowOut.model_validate(er) for er in persistence_service.list_excluded_rows(db, report_id)]


@router.delete("/{report_id}", status_code=204)
def delete_report(report_id: str, db: Session = Depends(get_db)) -> Response:
    report = get_report_or_404(db, report_id)
    db.delete(report)
    db.commit()
    shutil.rmtree(stored_upload_dir(report_id), ignore_errors=True)
    return Response(status_code=204)


@router.get("/{report_id}/export/audit-csv")
def export_audit_csv(report_id: str, db: Session = Depends(get_db)) -> Response:
    report = get_report_or_404(db, report_id)
    csv_text = export_service.audit_log_csv(db, report_id)
    audit_service.log_action(db, report.id, "EXPORT_GENERATED", "REPORT", report.id,
                              after={"export": "audit-csv"})
    db.commit()
    return Response(content=csv_text, media_type="text/csv",
                     headers={"Content-Disposition": f'attachment; filename="{report_id}_audit.csv"'})


@router.get("/{report_id}/export/by-status")
def export_by_status_csv(report_id: str, db: Session = Depends(get_db)) -> Response:
    report = get_report_or_404(db, report_id)
    csv_text = export_service.claims_by_status_csv(db, report_id)
    audit_service.log_action(db, report.id, "EXPORT_GENERATED", "REPORT", report.id,
                              after={"export": "by-status-csv"})
    db.commit()
    return Response(content=csv_text, media_type="text/csv",
                     headers={"Content-Disposition": f'attachment; filename="{report_id}_by_status.csv"'})
