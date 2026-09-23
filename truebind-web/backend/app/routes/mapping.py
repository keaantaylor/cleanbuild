from __future__ import annotations

import logging
import threading
import traceback
from pathlib import Path
from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, sessionmaker

from ..database import get_db, get_session_factory
from ..models.reports import Mapping, Report, Sheet
from ..schemas.reports import MappingConfirmRequest, MappingFieldOut, ReportOut, SheetOut
from ..services import persistence_service, pipeline_service
from .deps import get_report_or_404, get_sheet_or_404, stored_upload_path

router = APIRouter(prefix="/api/v1/reports", tags=["mapping"])
logger = logging.getLogger("truebind.pipeline")


def _sheet_out(db: Session, sheet: Sheet) -> SheetOut:
    return SheetOut(
        id=sheet.id, sheet_name=sheet.sheet_name, sheet_index=sheet.sheet_index,
        header_row_index=sheet.header_row_index, row_count=sheet.row_count,
        status=sheet.status, skip_reason=sheet.skip_reason,
        **persistence_service.sheet_out_fields(db, sheet),
    )


@router.get("/{report_id}/sheets", response_model=list[SheetOut])
def list_sheets(report_id: str, db: Session = Depends(get_db)) -> list[SheetOut]:
    get_report_or_404(db, report_id)
    sheets = db.query(Sheet).filter_by(report_id=report_id).order_by(Sheet.sheet_index).all()
    return [_sheet_out(db, s) for s in sheets]


def _load_raw_sheet(report_id: str, report, sheet_name: str):
    # Perf fix: this used to call pipeline_service.load_workbook() fresh
    # on every call -- re-reading and re-parsing the entire workbook from
    # disk just to answer one sheet's question. Measured on a
    # 20-sheet/26,000-row file: 3.4s per call x 19 sheets = 64.7s spent on
    # nothing but redundant re-reads during mapping confirmation alone,
    # the dominant cost of the whole upload flow. The cache is keyed by
    # report_id and the underlying file is immutable once uploaded, so
    # there is no staleness risk.
    sheets = pipeline_service.load_workbook_cached(
        report_id, stored_upload_path(report), source_stem=Path(report.file_name).stem,
    )
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

    return _sheet_out(db, sheet)


@router.post("/{report_id}/process", response_model=ReportOut, status_code=202)
def process_report(
    report_id: str,
    db: Session = Depends(get_db),
    session_factory: sessionmaker = Depends(get_session_factory),
) -> ReportOut:
    """Section 6: a multi-thousand-row workbook previously ran the whole
    ingest/mapping/validation/dedupe/persist pipeline inline on the
    request thread -- profiling an 8,000-row single-sheet file showed
    this holding the HTTP connection open for ~10s, with no feedback to
    the browser in the meantime and a hard timeout risk on anything
    larger. The pipeline now runs on a background thread with its own DB
    session (the request-scoped one is closed the instant this handler
    returns); the caller gets the report back immediately at PROCESSING
    and polls GET /{report_id} until it flips to COMPLETE or FAILED."""
    report = get_report_or_404(db, report_id)
    if report.status == "PROCESSING":
        raise HTTPException(status_code=409, detail="Report is already processing")
    pending = db.query(Sheet).filter_by(report_id=report_id, status="PENDING_CONFIRMATION").count()
    if pending:
        raise HTTPException(status_code=400, detail=f"{pending} sheet(s) still need mapping confirmation")

    db_sheets = db.query(Sheet).filter_by(report_id=report_id).all()
    sheet_id_by_name = {s.sheet_name: s.id for s in db_sheets}
    confirmed_mappings = {
        s.sheet_name: persistence_service.confirmed_mapping_for_sheet(db, s)
        for s in db_sheets if s.status == "CONFIRMED"
    }
    upload_path = stored_upload_path(report)
    file_name = report.file_name

    report.status = "PROCESSING"
    report.processing_error = None
    db.commit()
    db.refresh(report)

    thread = threading.Thread(
        target=_run_pipeline_job,
        args=(session_factory, report_id, upload_path, file_name, confirmed_mappings, sheet_id_by_name),
        daemon=True,
    )
    thread.start()

    return ReportOut.model_validate(report)


def _run_pipeline_job(
    session_factory: sessionmaker,
    report_id: str,
    upload_path: Path,
    file_name: str,
    confirmed_mappings: dict[str, dict[str, str]],
    sheet_id_by_name: dict[str, str],
) -> None:
    """Runs off the request thread; owns its own session for the same
    reason any background job does -- the request-scoped `Depends(get_db)`
    session is closed the moment the route handler returns, long before
    this finishes. Never left un-caught: an exception here would
    otherwise vanish into the thread and leave the report stuck at
    PROCESSING forever with no visible failure (exactly the silent-drop
    anti-pattern the rest of this round is fixing elsewhere).

    Per-stage wall-clock timings are logged with the report id so a slow
    or hung upload can be diagnosed from the actual bottleneck instead of
    guessed at -- see bordereaux.pipeline.run_workbook_pipeline's own
    stage_timings for the mapping/validation/dedupe/report split inside
    the "pipeline" stage logged here."""
    db = session_factory()
    stage = "startup"
    t_total = perf_counter()
    try:
        stage = "ingest"
        t = perf_counter()
        # Reuses the mapping-confirmation screen's cache entry when the
        # human confirmed at least one sheet's mapping (the common path)
        # -- this used to be a fourth-plus redundant full read of the same
        # file (once at upload, once per sheet during confirmation, again
        # here); now a cache hit unless nothing populated it yet.
        sheets = pipeline_service.load_workbook_cached(
            report_id, upload_path, source_stem=Path(file_name).stem,
        )
        t_ingest = perf_counter() - t

        stage = "mapping_proposal"
        t = perf_counter()
        proposals = pipeline_service.propose_mapping_for_workbook(sheets)
        t_mapping_proposal = perf_counter() - t

        stage = "pipeline"
        t = perf_counter()
        result = pipeline_service.run_workbook_pipeline(
            sheets, confirmed_mappings, proposals, source_name=file_name,
        )
        t_pipeline = perf_counter() - t

        stage = "persist"
        t = perf_counter()
        report = db.query(Report).filter_by(id=report_id).one()
        persistence_service.persist_pipeline_result(db, report, sheets, result, sheet_id_by_name)
        t_persist = perf_counter() - t

        logger.info(
            "report %s processed in %.2fs -- ingest=%.2fs mapping_proposal=%.2fs "
            "pipeline=%.2fs (mapping=%.2fs validation=%.2fs dedupe=%.2fs report=%.2fs) persist=%.2fs "
            "rows=%d sheets=%d",
            report_id, perf_counter() - t_total, t_ingest, t_mapping_proposal, t_pipeline,
            result.stage_timings.get("mapping", 0.0), result.stage_timings.get("validation", 0.0),
            result.stage_timings.get("dedupe", 0.0), result.stage_timings.get("report", 0.0),
            t_persist, len(result.canonical), len(sheets),
        )
    except Exception as exc:  # noqa: BLE001 -- must surface as FAILED, never vanish silently
        tb = traceback.format_exc()
        logger.error(
            "report %s FAILED at stage %r after %.2fs:\n%s",
            report_id, stage, perf_counter() - t_total, tb,
        )
        try:
            db.rollback()
            report = db.query(Report).filter_by(id=report_id).first()
            if report is not None:
                report.status = "FAILED"
                report.processing_error = f"{stage}: {exc}"
                db.commit()
        except Exception:  # noqa: BLE001 -- recording the failure must never itself hide the failure
            logger.error("report %s: could not record FAILED status after the above error:\n%s",
                         report_id, traceback.format_exc())
    finally:
        pipeline_service.evict_workbook_cache(report_id)
        db.close()
