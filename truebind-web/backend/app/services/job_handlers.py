"""What a job actually does. Runs inside the isolated worker child process
(app/worker.py) -- or inline in tests -- with its own DB session bound to
the job's tenant.

INGEST : stored file -> parse (hard limits) -> propose mapping (AI capped per
         report, headers only) -> persist sheets/mappings -> WAITING_FOR_REVIEW
PROCESS: stored file -> parse -> confirmed mapping from the DB (no second AI
         call) -> validate / dedupe / reconcile -> replace results -> COMPLETE

Every failure is classified into a stable code and a customer-safe message;
internal detail (exception text, traceback) goes to jobs.error_detail and the
log only, never to an API response."""

from __future__ import annotations

import logging
import resource
import traceback
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from bordereaux import mapping as mapping_mod
from bordereaux.ingest import MappingConflictError, ReadLimits, WorkbookLimitError
from bordereaux.pipeline import SheetMappingProposal

from ..config import AI_MAX_CALLS_PER_REPORT, MAX_CELLS, MAX_ROWS, MAX_SHEETS
from ..database import set_tenant
from ..models.jobs import Job
from ..models.reports import Report, Sheet
from . import job_service, persistence_service, pipeline_service, report_state
from .storage import store

log = logging.getLogger("truebind.jobs")

LIMITS = ReadLimits(max_sheets=MAX_SHEETS, max_rows_total=MAX_ROWS, max_cells_total=MAX_CELLS)


@dataclass
class JobFailure(Exception):
    code: str
    message: str  # customer-safe
    retryable: bool = False
    detail: str = ""


def _classify(exc: BaseException) -> JobFailure:
    if isinstance(exc, JobFailure):
        return exc
    detail = "".join(traceback.format_exception(exc))[-4000:]
    if isinstance(exc, WorkbookLimitError):
        return JobFailure("file_too_large", f"The file exceeds a processing limit: {exc}", False, detail)
    if isinstance(exc, MappingConflictError):
        return JobFailure("mapping_conflict", "Two columns are mapped to the same field. Review the mapping.",
                          False, detail)
    if isinstance(exc, MemoryError):
        return JobFailure("resource_limit", "The file needed more memory than a single job is allowed.",
                          False, detail)
    if isinstance(exc, OperationalError):
        return JobFailure("temporary_error", "A temporary error interrupted processing. It will be retried.",
                          True, detail)
    if isinstance(exc, FileNotFoundError):
        return JobFailure("source_missing", "The uploaded file is no longer available. Upload it again.",
                          False, detail)
    return JobFailure("internal_error", "Processing failed unexpectedly. The team has the details.", True, detail)


def _peak_rss_mb() -> float:
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)


def _load(db: Session, job: Job) -> tuple[Report, Path]:
    report = db.get(Report, job.report_id)
    if report is None or report.tenant_id != job.tenant_id:
        raise JobFailure("report_missing", "The report no longer exists.")
    if not report.storage_key:
        raise JobFailure("source_missing", "The uploaded file is no longer available. Upload it again.")
    return report, store.local_path(report.storage_key)


def _parse(path: Path, report: Report):
    try:
        return pipeline_service.load_workbook(path, source_stem=Path(report.file_name).stem, limits=LIMITS)
    except (WorkbookLimitError, MemoryError):
        raise
    except Exception as exc:  # noqa: BLE001 -- any parser failure is "unreadable", never a crash
        raise JobFailure("unreadable_file", "The file could not be read as a spreadsheet. Check it opens in "
                         "Excel and is not password-protected.", False,
                         "".join(traceback.format_exception(exc))[-4000:]) from exc


def propose_with_ai_cap(sheets) -> tuple[list[SheetMappingProposal], dict]:
    """Alias stage for every sheet; the AI stage only while the per-report
    call budget lasts (AI_MAX_CALLS_PER_REPORT). One mapper instance, so the
    model/timeouts are fixed for the whole report."""
    mapper = mapping_mod.ClaudeAIMapper() if mapping_mod.ai_mapping_available() else None
    calls, tokens_in, tokens_out, capped, model = 0, 0, 0, False, None
    proposals = []
    for s in sheets:
        if s.skipped:
            continue
        budget_left = calls < AI_MAX_CALLS_PER_REPORT
        if not budget_left:
            capped = True
        m = mapping_mod.build_mapping(list(s.raw.columns), ai_mapper=mapper if budget_left else None,
                                      use_ai=budget_left and mapper is not None)
        if m.ai_attempted:
            calls += 1
            model = m.ai_model or model
            usage = m.ai_usage or {}
            tokens_in += int(usage.get("input_tokens") or 0)
            tokens_out += int(usage.get("output_tokens") or 0)
        proposals.append(SheetMappingProposal(s, m))
    meta = {"ai_available": mapper is not None, "ai_calls": calls, "ai_model": model, "ai_capped": capped,
            "ai_input_tokens": tokens_in, "ai_output_tokens": tokens_out,
            "ai_data_sent": "column header text only (no cell values)" if calls else "none"}
    return proposals, meta


def run_ingest(db: Session, job: Job) -> dict:
    t0 = perf_counter()
    report, path = _load(db, job)
    job_service.set_stage(db, job, "parsing")
    sheets = _parse(path, report)
    t_parse = perf_counter() - t0
    job_service.set_stage(db, job, "proposing_mapping")
    proposals, ai_meta = propose_with_ai_cap(sheets)
    t_map = perf_counter() - t0 - t_parse
    job_service.set_stage(db, job, "saving")
    ai_meta["file_notes"] = (report.ingest_notes or {}).get("file_notes", [])
    persistence_service.persist_ingest(db, report, sheets, proposals, ai_meta)
    if not any(not s.skipped for s in sheets):
        # Nothing mappable at all: keep the per-sheet reasons (commit), then
        # fail clearly rather than wait for a review that cannot happen.
        db.commit()
        raise JobFailure("no_data", "No sheet in this file has a recognisable header row with data below it.")
    report_state.transition(db, report, "WAITING_FOR_REVIEW", reason="mapping proposed")
    return {"parse_s": round(t_parse, 2), "mapping_s": round(t_map, 2), "sheets": len(sheets),
            "rows": sum(len(s.raw) for s in sheets if not s.skipped), "peak_rss_mb": _peak_rss_mb(),
            "ai_calls": ai_meta["ai_calls"]}


def run_process(db: Session, job: Job) -> dict:
    t0 = perf_counter()
    report, path = _load(db, job)
    db_sheets = db.query(Sheet).filter_by(report_id=report.id).all()
    if any(s.status == "PENDING_CONFIRMATION" for s in db_sheets):
        raise JobFailure("mapping_not_confirmed", "Every sheet's mapping must be confirmed before processing.")
    job_service.set_stage(db, job, "parsing")
    sheets = _parse(path, report)
    t_parse = perf_counter() - t0
    job_service.set_stage(db, job, "validating")
    proposals = persistence_service.proposals_from_db(db, report, sheets)
    confirmed = {s.sheet_name: persistence_service.confirmed_mapping_for_sheet(db, s)
                 for s in db_sheets if s.status == "CONFIRMED"}
    result = pipeline_service.run_workbook_pipeline(sheets, confirmed, proposals, source_name=report.file_name)
    t_pipe = perf_counter() - t0 - t_parse
    job_service.set_stage(db, job, "saving")
    t = perf_counter()
    persistence_service.persist_pipeline_result(db, report, sheets, result, {s.sheet_name: s.id for s in db_sheets})
    t_persist = perf_counter() - t
    report_state.transition(db, report, "COMPLETE", reason="processed")
    return {"parse_s": round(t_parse, 2), "pipeline_s": round(t_pipe, 2), "persist_s": round(t_persist, 2),
            "stage_timings": {k: round(v, 2) for k, v in result.stage_timings.items()},
            "rows": int(len(result.canonical)), "peak_rss_mb": _peak_rss_mb()}


HANDLERS = {"INGEST": run_ingest, "PROCESS": run_process}


def execute(db: Session, job_id: str, tenant_id: str) -> None:
    """Run one claimed job to a terminal (or retry) state. Never raises."""
    set_tenant(db, tenant_id)
    job = db.get(Job, job_id)
    if job is None or job.status != "RUNNING":
        return
    try:
        metrics = HANDLERS[job.kind](db, job)
        job_service.finish(db, job, ok=True, metrics=metrics)
        log.info("job %s %s succeeded %s", job.id, job.kind, metrics)
    except BaseException as exc:  # noqa: BLE001 -- every outcome must be recorded
        failure = _classify(exc)
        log.warning("job %s %s failed: %s (%s)", job_id, getattr(job, "kind", "?"), failure.code,
                    failure.detail.splitlines()[-1] if failure.detail else "")
        try:
            db.rollback()
            set_tenant(db, tenant_id)
            job = db.get(Job, job_id)
            if job is not None and job.status == "RUNNING":
                job_service.finish(db, job, ok=False, code=failure.code, message=failure.message,
                                   detail=failure.detail, retryable=failure.retryable)
        except Exception:  # noqa: BLE001 -- the parent/reaper will still recover the job
            log.exception("job %s: could not record failure", job_id)
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
