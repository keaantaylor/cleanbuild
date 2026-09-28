"""Sanctions lists an organisation screens against (P5).

GET    /api/v1/sanctions/lists             loaded lists (data:read)
POST   /api/v1/sanctions/lists             load a list file: OFSI, OFAC SDN, EU, UN XML or a simple
                                           name CSV, recognised from its content (data:write, audited)
DELETE /api/v1/sanctions/lists/{list_id}   remove a list and its entries (data:write, audited)
Loading a list does not re-screen past reports: run the sanctions check again on a report
(Checks -> Run again) to screen it against the lists now loaded.
"""

from __future__ import annotations

import hashlib
from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy import insert
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.modules import SanctionsEntry, SanctionsList
from ..security.auth import Context, require_reader, require_writer
from ..security.file_guard import safe_display_name
from ..security.ratelimit import limiter
from ..services import audit_service, sanctions_lists

router = APIRouter(prefix="/api/v1/sanctions", tags=["sanctions"])
MAX_LIST_BYTES = 50 * 1024 * 1024
_BATCH = 5000


class SanctionsListOut(BaseModel):
    id: str
    name: str
    source: str
    file_name: str
    sha256: str
    entry_count: int
    uploaded_at: datetime
    uploaded_by: str


def _out(x: SanctionsList) -> SanctionsListOut:
    return SanctionsListOut(
        id=x.id,
        name=x.name,
        source=x.source,
        file_name=x.file_name,
        sha256=x.sha256,
        entry_count=x.entry_count,
        uploaded_at=x.uploaded_at,
        uploaded_by=x.uploaded_by,
    )


@router.get("/lists", response_model=list[SanctionsListOut])
def list_lists(ctx: Context = Depends(require_reader), db: Session = Depends(get_db)) -> list[SanctionsListOut]:
    rows = (
        db.query(SanctionsList)
        .filter(SanctionsList.tenant_id == ctx.tenant_id)
        .order_by(SanctionsList.uploaded_at.desc())
    )
    return [_out(x) for x in rows]


@router.post("/lists", response_model=SanctionsListOut, status_code=201)
def load_list(
    file: UploadFile,
    name: str = Form(min_length=1, max_length=200),
    ctx: Context = Depends(require_writer),
    db: Session = Depends(get_db),
) -> SanctionsListOut:
    limiter.check("sanctions-list", ctx.user_id, limit=30, window_s=3600)
    data = file.file.read(MAX_LIST_BYTES + 1)
    if len(data) > MAX_LIST_BYTES:
        raise HTTPException(status_code=413, detail="The list file is larger than 50 MB.")
    try:
        parsed = sanctions_lists.parse(data)
    except sanctions_lists.ListFormatError as exc:
        raise HTTPException(status_code=422, detail=f"The list could not be read: {exc}.") from exc
    item = SanctionsList(
        tenant_id=ctx.tenant_id,
        name=name.strip(),
        source=parsed.source,
        file_name=safe_display_name(file.filename),
        sha256=hashlib.sha256(data).hexdigest(),
        entry_count=len(parsed.entries),
        uploaded_by=ctx.actor[:255],
    )
    db.add(item)
    db.flush()
    rows = [
        {
            "tenant_id": ctx.tenant_id,
            "list_id": item.id,
            "reference": e.reference[:64],
            "name": e.name[:500],
            "kind": e.kind[:32],
        }
        for e in parsed.entries
    ]
    for i in range(0, len(rows), _BATCH):
        db.execute(insert(SanctionsEntry), rows[i : i + _BATCH])
    out = _out(item)
    audit_service.log_action(
        db,
        ctx.tenant_id,
        None,
        "SANCTIONS_LIST_LOADED",
        "SANCTIONS_LIST",
        item.id,
        after={"name": item.name, "source": item.source, "sha256": item.sha256, "entries": item.entry_count},
        actor=ctx.actor,
        actor_user_id=ctx.user_id,
    )
    db.commit()
    return out


@router.delete("/lists/{list_id}", status_code=204)
def delete_list(list_id: str, ctx: Context = Depends(require_writer), db: Session = Depends(get_db)) -> Response:
    item = db.query(SanctionsList).filter(SanctionsList.id == list_id, SanctionsList.tenant_id == ctx.tenant_id).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Sanctions list not found.")
    audit_service.log_action(
        db,
        ctx.tenant_id,
        None,
        "SANCTIONS_LIST_REMOVED",
        "SANCTIONS_LIST",
        item.id,
        before={"name": item.name, "source": item.source, "sha256": item.sha256, "entries": item.entry_count},
        actor=ctx.actor,
        actor_user_id=ctx.user_id,
    )
    db.query(SanctionsEntry).filter(
        SanctionsEntry.list_id == item.id, SanctionsEntry.tenant_id == ctx.tenant_id
    ).delete(synchronize_session=False)
    db.delete(item)
    db.commit()
    return Response(status_code=204)
