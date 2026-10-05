"""Spreadsheet connectors: open a report's workbook in Excel or Google Sheets,
read edits back as proposed corrections, write the working copy back."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import connectors
from ..connectors import ConnectorError
from ..database import get_db
from ..models.connectors import ConnectorLink
from ..security.auth import Context, require_reader, require_writer
from ..services import connector_service, deliverables
from .deps import get_report_or_404

router = APIRouter(prefix="/api/v1", tags=["connectors"])


@router.get("/connectors")
def list_connectors(ctx: Context = Depends(require_reader)) -> dict:
    """Which providers this server is connected to. Never returns credentials."""
    return {"items": [{"key": p.key, "label": p.label, "open_label": p.open_label, "configured": p.configured()}
                      for p in connectors.PROVIDERS.values()]}


def _complete(db: Session, ctx: Context, report_id: str):
    report = get_report_or_404(db, ctx, report_id)
    if report.status != "COMPLETE":
        raise HTTPException(status_code=409, detail="Available once the report is processed.")
    return report


def _link(db: Session, ctx: Context, report_id: str, link_id: str) -> tuple:
    report = _complete(db, ctx, report_id)
    link = db.query(ConnectorLink).filter(ConnectorLink.id == link_id, ConnectorLink.report_id == report.id,
                                          ConnectorLink.tenant_id == ctx.tenant_id).first()
    if link is None:
        raise HTTPException(status_code=404, detail="Link not found.")
    return report, link


@router.get("/reports/{report_id}/connectors")
def report_links(report_id: str, ctx: Context = Depends(require_reader), db: Session = Depends(get_db)) -> dict:
    report = get_report_or_404(db, ctx, report_id)
    links = (db.query(ConnectorLink).filter(ConnectorLink.report_id == report.id, ConnectorLink.tenant_id == ctx.tenant_id)
             .order_by(ConnectorLink.created_at.desc()).all())
    return {"items": [connector_service.link_out(link) for link in links]}


@router.post("/reports/{report_id}/connectors/{provider}/open", status_code=201)
def open_in_provider(report_id: str, provider: str, ctx: Context = Depends(require_writer),
                     db: Session = Depends(get_db)) -> dict:
    report = _complete(db, ctx, report_id)
    try:
        link = connector_service.open_in(db, report, provider, ctx.actor, ctx.user_id)
    except connector_service.ConnectorUnavailable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (ConnectorError, deliverables.SourceUnavailable) as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    db.commit()
    return connector_service.link_out(link)


@router.post("/reports/{report_id}/connectors/links/{link_id}/pull")
def pull_edits(report_id: str, link_id: str, ctx: Context = Depends(require_writer),
               db: Session = Depends(get_db)) -> dict:
    """Read edits made in Excel / Google Sheets back as PROPOSED corrections,
    each under its execution policy. Nothing is applied here."""
    report, link = _link(db, ctx, report_id, link_id)
    try:
        out = connector_service.pull(db, report, link, ctx.actor, ctx.user_id)
    except connector_service.ConnectorUnavailable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ConnectorError as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    db.commit()
    return out


@router.post("/reports/{report_id}/connectors/links/{link_id}/push")
def push_working_copy(report_id: str, link_id: str, ctx: Context = Depends(require_writer),
                      db: Session = Depends(get_db)) -> dict:
    """Write the working copy (original + approved corrections) back to the
    remote file as a new version."""
    report, link = _link(db, ctx, report_id, link_id)
    try:
        connector_service.push(db, report, link, ctx.actor, ctx.user_id)
    except connector_service.ConnectorUnavailable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (ConnectorError, deliverables.SourceUnavailable) as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    db.commit()
    return connector_service.link_out(link)
