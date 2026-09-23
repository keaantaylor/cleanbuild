from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.reports import ReportOut
from ..services import persistence_service, pipeline_service
from .deps import stored_upload_dir

router = APIRouter(prefix="/api/v1/reports", tags=["upload"])

ALLOWED_SUFFIXES = (".xlsx", ".xlsm", ".xls", ".csv")
_CHUNK_SIZE = 1024 * 1024  # 1 MiB


@router.post("/upload", response_model=ReportOut)
async def upload_report(file: UploadFile, db: Session = Depends(get_db)) -> ReportOut:
    if not file.filename or not file.filename.lower().endswith(ALLOWED_SUFFIXES):
        raise HTTPException(status_code=400, detail=f"Unsupported file type; expected one of {ALLOWED_SUFFIXES}")

    # Section 6: streamed to disk in chunks rather than `await file.read()`
    # in one shot -- the old version held the entire upload in memory
    # twice over (once as UploadFile's own spooled buffer, once again in
    # `content`) before a single byte reached disk, which is exactly the
    # kind of thing that stops scaling long before the pipeline itself
    # does. Report id is generated on insert, so we still stage under a
    # temp name and rename once we have it -- avoids a two-phase-commit-
    # shaped race.
    with tempfile.NamedTemporaryFile(suffix=Path(file.filename).suffix, delete=False) as tmp:
        tmp_path = Path(tmp.name)
        file_size_bytes = 0
        while chunk := await file.read(_CHUNK_SIZE):
            tmp.write(chunk)
            file_size_bytes += len(chunk)

    if not file_size_bytes:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    try:
        # For a CSV, the implicit single sheet is named after the file
        # (see ingest.load_workbook_sheets). Reading from tmp_path here
        # but Path(file.filename).stem everywhere else the report is
        # ever re-read (mapping confirmation, /process) means the sheet
        # name recorded now must match what those later reads will use --
        # pass it explicitly rather than letting each read derive its own
        # name from whatever path it happens to be reading, which used to
        # silently diverge (a random temp filename here vs. the real
        # stored filename later) and break every CSV upload past this
        # point.
        sheets = pipeline_service.load_workbook(tmp_path, source_stem=Path(file.filename).stem)
    except Exception as exc:  # noqa: BLE001 -- surfaced to the caller, not swallowed
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=f"Could not read the uploaded file: {exc}") from exc

    proposals = pipeline_service.propose_mapping_for_workbook(sheets)

    report = persistence_service.create_report_from_upload(
        db, file_name=file.filename, file_size_bytes=file_size_bytes, sheets=sheets, proposals=proposals,
    )
    # The file was just read and parsed above; seed the mapping-
    # confirmation cache with that same result now that report.id exists,
    # so the first per-sheet GET doesn't re-read a file the process just
    # finished reading.
    pipeline_service.seed_workbook_cache(report.id, sheets)

    dest_dir = stored_upload_dir(report.id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / report.file_name
    tmp_path.replace(dest_path)

    return ReportOut.model_validate(report)
