"""Sheets, mapping review and the process request. The mapping screen is
served entirely from what ingest stored (headers, samples, proposals with
evidence) -- the API never re-reads the workbook."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.reports import Mapping, Report, Sheet
from ..schemas.reports import MappingConfirmRequest, MappingFieldOut, ReportOut, SheetMappingOut, SheetOut
from ..security.auth import Context, require_reader, require_writer
from ..models.identity import Tenant
from ..services import billing_service, idempotency, job_service, persistence_service
from ..services.pipeline_service import FIELDS, FIELDS_BY_CODE, REQUIRED_CODES
from .deps import get_report_or_404, get_sheet_or_404, report_out

router = APIRouter(prefix="/api/v1/reports", tags=["mapping"])

EDITABLE_STATUSES = ("WAITING_FOR_REVIEW", "COMPLETE", "FAILED")


def _sheet_out(sheet: Sheet, rows: list[Mapping]) -> SheetOut:
    status, mapped, total = persistence_service.sheet_mapping_status(sheet, rows)
    return SheetOut(
        id=sheet.id, sheet_name=sheet.sheet_name, sheet_index=sheet.sheet_index,
        header_row_index=sheet.header_row_index, row_count=sheet.row_count,
        source_column_count=sheet.source_column_count, status=sheet.status, skip_reason=sheet.skip_reason,
        hidden=sheet.hidden, notes=list(sheet.notes or []), trailing_blank_rows=sheet.trailing_blank_rows,
        mapping_status=status, fields_mapped=mapped, fields_total=total,
        needs_review=sum(1 for m in rows if m.review_state in ("REVIEW", "AMBIGUOUS")),
    )


def _mappings_by_sheet(db: Session, report: Report) -> dict[str, list[Mapping]]:
    out: dict[str, list[Mapping]] = {}
    for m in db.query(Mapping).filter(Mapping.report_id == report.id, Mapping.tenant_id == report.tenant_id):
        out.setdefault(m.sheet_id, []).append(m)
    return out


@router.get("/{report_id}/sheets", response_model=list[SheetOut])
def list_sheets(report_id: str, ctx: Context = Depends(require_reader), db: Session = Depends(get_db)) -> list[SheetOut]:
    report = get_report_or_404(db, ctx, report_id)
    by_sheet = _mappings_by_sheet(db, report)
    sheets = db.query(Sheet).filter(Sheet.report_id == report.id).order_by(Sheet.sheet_index).all()
    return [_sheet_out(s, by_sheet.get(s.id, [])) for s in sheets]


@router.get("/{report_id}/sheets/{sheet_id}/mapping", response_model=SheetMappingOut)
def get_sheet_mapping(report_id: str, sheet_id: str, ctx: Context = Depends(require_reader),
                      db: Session = Depends(get_db)) -> SheetMappingOut:
    report = get_report_or_404(db, ctx, report_id)
    sheet = get_sheet_or_404(db, ctx, report, sheet_id)
    rows = db.query(Mapping).filter(Mapping.sheet_id == sheet.id).all()
    by_code = {m.field_code: m for m in rows}
    samples = sheet.samples or {}
    fields = []
    for f in FIELDS:
        m = by_code.get(f.code)
        if m is None:
            continue
        fields.append(MappingFieldOut(
            field_code=f.code, field_name=f.name, required=f.code in REQUIRED_CODES,
            source_column=m.source_column, mapping_state=m.mapping_state, review_state=m.review_state,
            evidence=m.evidence, rule_version=m.rule_version, ai_model=m.ai_model,
            confidence_score=m.confidence_score,
            sample_values=samples.get(m.source_column, []) if m.source_column else [],
            confirmed=m.confirmed_at is not None,
        ))
    headers = [h for h in (sheet.headers or []) if not str(h).startswith("__blank_col_")]
    return SheetMappingOut(sheet=_sheet_out(sheet, rows), headers=headers, fields=fields)


@router.post("/{report_id}/sheets/{sheet_id}/mapping", response_model=SheetOut)
def confirm_sheet_mapping(report_id: str, sheet_id: str, body: MappingConfirmRequest,
                          ctx: Context = Depends(require_writer), db: Session = Depends(get_db)) -> SheetOut:
    report = get_report_or_404(db, ctx, report_id)
    sheet = get_sheet_or_404(db, ctx, report, sheet_id)
    if report.status not in EDITABLE_STATUSES or job_service.active_job(db, report.id) is not None:
        raise HTTPException(status_code=409, detail="The mapping cannot be changed while the report is being processed.")
    if sheet.status == "SKIPPED":
        raise HTTPException(status_code=409, detail="This sheet was skipped and has no mapping to confirm.")
    unknown = [c for c in body.mappings if c not in FIELDS_BY_CODE]
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown field code(s): {', '.join(sorted(unknown)[:5])}.")
    try:
        persistence_service.confirm_sheet_mapping(db, report, sheet, body.mappings, actor=ctx.actor,
                                                  actor_user_id=ctx.user_id)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    rows = db.query(Mapping).filter(Mapping.sheet_id == sheet.id).all()
    return _sheet_out(sheet, rows)


def _set_included(report_id: str, sheet_id: str, include: bool, ctx: Context, db: Session) -> SheetOut:
    report = get_report_or_404(db, ctx, report_id)
    sheet = get_sheet_or_404(db, ctx, report, sheet_id)
    if report.status not in EDITABLE_STATUSES or job_service.active_job(db, report.id) is not None:
        raise HTTPException(status_code=409, detail="Sheets cannot be changed while the report is being processed.")
    try:
        persistence_service.set_sheet_included(db, report, sheet, include, actor=ctx.actor,
                                               actor_user_id=ctx.user_id)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    rows = db.query(Mapping).filter(Mapping.sheet_id == sheet.id).all()
    return _sheet_out(sheet, rows)


@router.post("/{report_id}/sheets/{sheet_id}/include", response_model=SheetOut)
def include_sheet(report_id: str, sheet_id: str, ctx: Context = Depends(require_writer),
                  db: Session = Depends(get_db)) -> SheetOut:
    """"Include anyway": bring back a sheet auto-skipped as a non-claims tab.
    Its mapping then needs confirming like any other sheet."""
    return _set_included(report_id, sheet_id, True, ctx, db)


@router.post("/{report_id}/sheets/{sheet_id}/skip", response_model=SheetOut)
def skip_sheet(report_id: str, sheet_id: str, ctx: Context = Depends(require_writer),
               db: Session = Depends(get_db)) -> SheetOut:
    """Leave a sheet out of the health report (it can be included again)."""
    return _set_included(report_id, sheet_id, False, ctx, db)


@router.post("/{report_id}/process", response_model=ReportOut, status_code=202)
def process_report(report_id: str, idempotency_key: str | None = Header(default=None, alias=idempotency.HEADER),
                   ctx: Context = Depends(require_writer), db: Session = Depends(get_db)) -> ReportOut | JSONResponse:
    key = idempotency.validate_key(idempotency_key)
    report = get_report_or_404(db, ctx, report_id)
    idem = None
    if key is not None:
        claimed = idempotency.claim(db, tenant_id=ctx.tenant_id, user_id=ctx.user_id, scope="reports.process",
                                    key=key, request_fingerprint=idempotency.fingerprint(report.id))
        if isinstance(claimed, JSONResponse):
            return claimed
        idem = claimed
    if report.status not in EDITABLE_STATUSES:
        raise HTTPException(status_code=409, detail=f"A report in status {report.status} cannot be processed.")
    sheets = db.query(Sheet).filter(Sheet.report_id == report.id).all()
    if not sheets:
        raise HTTPException(status_code=409, detail="This report has no sheets to process.")
    pending = [s.sheet_name for s in sheets if s.status == "PENDING_CONFIRMATION"]
    if pending:
        raise HTTPException(status_code=409, detail=f"{len(pending)} sheet(s) still need their mapping confirmed.")
    if not any(s.status == "CONFIRMED" for s in sheets):
        raise HTTPException(status_code=409, detail="Every sheet is skipped. Include at least one claims sheet.")
    tenant = db.get(Tenant, ctx.tenant_id)
    if tenant is not None:
        try:
            billing_service.require_rows(db, tenant, sum(s.row_count or 0 for s in sheets if s.status == "CONFIRMED"))
        except billing_service.QuotaError as exc:
            raise HTTPException(status_code=402, detail=str(exc)) from exc
    try:
        job_service.enqueue(db, report, "PROCESS", actor=ctx.actor, actor_user_id=ctx.user_id)
    except job_service.JobConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    replay = idempotency.complete(idem, 202, report_out(db, report).model_dump(mode="json")) if idem else None
    db.commit()
    if replay is not None:
        return replay
    db.refresh(report)
    return report_out(db, report)
