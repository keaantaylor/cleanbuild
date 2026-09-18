from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db, get_session_factory
from ..models.reports import Mapping, Report, Sheet
from ..schemas.reports import MappingConfirmRequest, MappingFieldOut, ReportOut, SheetOut
from ..services import persistence_service, pipeline_service
from .deps import get_report_or_404, get_sheet_or_404, stored_upload_path

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/reports", tags=["mapping"])


@router.get("/{report_id}/sheets", response_model=list[SheetOut])
def list_sheets(report_id: str, db: Session = Depends(get_db)) -> list[SheetOut]:
    get_report_or_404(db, report_id)
    sheets = db.query(Sheet).filter_by(report_id=report_id).order_by(Sheet.sheet_index).all()
    return [SheetOut.model_validate(s) for s in sheets]


def _load_raw_sheet(report_id: str, report, sheet_name: str):
    sheets = pipeline_service.load_workbook(stored_upload_path(report))
    for s in sheets:
        if s.sheet_name == sheet_name:
            return s
    raise HTTPException(status_code=404, detail=f"Sheet {sheet_name!r} not found in source file")


@router.get("/{report_id}/sheets/{sheet_name}/headers", response_model=list[str])
def get_sheet_headers(report_id: str, sheet_name: str, db: Session = Depends(get_db)) -> list[str]:
    """Raw column headers as detected in the source file -- what the
    mapping-confirmation screen's per-field picker offers, so a human
    corrects a mapping by choosing a real column rather than typing a
    name that silently fails to match anything at ingest time."""
    report = get_report_or_404(db, report_id)
    get_sheet_or_404(db, report_id, sheet_name)
    raw_sheet = _load_raw_sheet(report_id, report, sheet_name)
    return list(raw_sheet.raw.columns)


@router.get("/{report_id}/sheets/{sheet_name}/mapping", response_model=list[MappingFieldOut])
def get_sheet_mapping(report_id: str, sheet_name: str, db: Session = Depends(get_db)) -> list[MappingFieldOut]:
    report = get_report_or_404(db, report_id)
    sheet = get_sheet_or_404(db, report_id, sheet_name)
    if sheet.status == "SKIPPED":
        raise HTTPException(status_code=400, detail=f"Sheet {sheet_name!r} was skipped: {sheet.skip_reason}")

    raw_sheet = _load_raw_sheet(report_id, report, sheet_name)
    mappings = db.query(Mapping).filter_by(sheet_id=sheet.id).all()

    out = []
    for m in mappings:
        out.append(MappingFieldOut(
            field_code=m.field_code,
            field_name=m.field_name,
            source_column=m.source_column,
            mapping_state=m.mapping_state,
            confidence_score=m.confidence_score,
            sample_values=pipeline_service.sample_values(raw_sheet.raw, m.source_column) if m.source_column else [],
            confirmed=m.confirmed_at is not None,
        ))
    return out


@router.post("/{report_id}/sheets/{sheet_name}/mapping/confirm", response_model=SheetOut)
def confirm_sheet_mapping(
    report_id: str, sheet_name: str, body: MappingConfirmRequest, db: Session = Depends(get_db),
) -> SheetOut:
    report = get_report_or_404(db, report_id)
    sheet = get_sheet_or_404(db, report_id, sheet_name)
    if sheet.status == "SKIPPED":
        raise HTTPException(status_code=400, detail=f"Sheet {sheet_name!r} was skipped, cannot confirm a mapping")

    actor = body.actor or "web_user"
    persistence_service.confirm_sheet_mapping(db, report, sheet, body.mappings, actor)
    db.refresh(sheet)

    remaining = db.query(Sheet).filter_by(report_id=report_id, status="PENDING_CONFIRMATION").count()
    report.status = "READY_FOR_REVIEW" if remaining == 0 else "PENDING_MAPPING"
    db.commit()

    return SheetOut.model_validate(sheet)


def _run_pipeline_in_background(report_id: str, upload_path) -> None:
    """Fix spec Section 6.2: the actual ingest/mapping/validate/dedupe/
    report run -- the heavy, O(sheets x rows) part of a request that
    previously ran synchronously inside the /process handler and could
    block the whole backend process for large files (the confirmed
    ~10-minute-hang symptom, during which unrelated pages also failed to
    load). Runs on FastAPI's background-task threadpool, off the request
    thread, with its own DB session (a session isn't safe to share across
    threads). Every phase transition is committed immediately so GET
    /reports/{id} -- which the frontend polls -- always reflects real,
    current progress, never a stale snapshot from before the background
    task started."""
    session_factory = get_session_factory()
    db = session_factory()
    try:
        report = db.get(Report, report_id)
        if report is None:
            return

        def _phase(name: str) -> None:
            report.processing_phase = name
            db.commit()

        _phase("loading workbook")
        sheets = pipeline_service.load_workbook(upload_path)

        _phase("proposing mapping")
        proposals = pipeline_service.propose_mapping_for_workbook(sheets)

        db_sheets = db.query(Sheet).filter_by(report_id=report_id).all()
        sheet_id_by_name = {s.sheet_name: s.id for s in db_sheets}
        confirmed_mappings = {
            s.sheet_name: persistence_service.confirmed_mapping_for_sheet(db, s)
            for s in db_sheets if s.status == "CONFIRMED"
        }

        _phase("validating and deduplicating")
        result = pipeline_service.run_workbook_pipeline(
            sheets, confirmed_mappings, proposals, source_name=report.file_name,
        )

        _phase("persisting results")
        persistence_service.persist_pipeline_result(db, report, sheets, result, sheet_id_by_name)
        report.processing_phase = None
        db.commit()
    except Exception as exc:  # noqa: BLE001 -- must never leave the report stuck at PROCESSING
        logger.exception("Background pipeline run failed for report %s", report_id)
        db.rollback()
        report = db.get(Report, report_id)
        if report is not None:
            report.status = "FAILED"
            report.processing_phase = None
            report.processing_error = f"{exc.__class__.__name__}: {exc}"
            db.commit()
    finally:
        db.close()


@router.post("/{report_id}/process", response_model=ReportOut, status_code=202)
def process_report(report_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)) -> ReportOut:
    report = get_report_or_404(db, report_id)
    pending = db.query(Sheet).filter_by(report_id=report_id, status="PENDING_CONFIRMATION").count()
    if pending:
        raise HTTPException(status_code=400, detail=f"{pending} sheet(s) still need mapping confirmation")

    report.status = "PROCESSING"
    report.processing_phase = "queued"
    report.processing_error = None
    db.commit()
    db.refresh(report)

    background_tasks.add_task(_run_pipeline_in_background, report_id, stored_upload_path(report))
    return ReportOut.model_validate(report)
