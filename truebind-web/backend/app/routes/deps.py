from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..config import UPLOAD_DIR
from ..models.reports import Report, Sheet


def get_report_or_404(db: Session, report_id: str) -> Report:
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    return report


def get_sheet_or_404(db: Session, report_id: str, sheet_name: str) -> Sheet:
    sheet = db.query(Sheet).filter_by(report_id=report_id, sheet_name=sheet_name).first()
    if sheet is None:
        raise HTTPException(status_code=404, detail=f"Sheet {sheet_name!r} not found on report {report_id}")
    return sheet


def stored_upload_dir(report_id: str) -> Path:
    return UPLOAD_DIR / report_id


def stored_upload_path(report: Report) -> Path:
    return stored_upload_dir(report.id) / report.file_name
