from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.reports import ReportOut
from ..services import persistence_service, pipeline_service
from .deps import stored_upload_dir

router = APIRouter(prefix="/api/v1/reports", tags=["upload"])

ALLOWED_SUFFIXES = (".xlsx", ".xlsm", ".xls", ".csv")


@router.post("/upload", response_model=ReportOut)
async def upload_report(file: UploadFile, db: Session = Depends(get_db)) -> ReportOut:
    if not file.filename or not file.filename.lower().endswith(ALLOWED_SUFFIXES):
        raise HTTPException(status_code=400, detail=f"Unsupported file type; expected one of {ALLOWED_SUFFIXES}")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    # Report id is generated on insert, so we stage under a temp name and
    # rename once we have it -- avoids a two-phase-commit-shaped race.
    sheets = None
    import tempfile
    from pathlib import Path

    with tempfile.NamedTemporaryFile(suffix=Path(file.filename).suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        sheets = pipeline_service.load_workbook(tmp_path)
    except Exception as exc:  # noqa: BLE001 -- surfaced to the caller, not swallowed
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=f"Could not read the uploaded file: {exc}") from exc

    proposals = pipeline_service.propose_mapping_for_workbook(sheets)

    report = persistence_service.create_report_from_upload(
        db, file_name=file.filename, file_size_bytes=len(content), sheets=sheets, proposals=proposals,
    )

    dest_dir = stored_upload_dir(report.id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / report.file_name
    tmp_path.replace(dest_path)

    return ReportOut.model_validate(report)
