from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.templates import Template
from ..schemas.reports import TemplateCreateRequest, TemplateOut
from ..security.auth import Context, get_context, require_writer
from ..services import audit_service
from ..services.pipeline_service import FIELDS_BY_CODE

router = APIRouter(prefix="/api/v1/templates", tags=["templates"])


@router.get("", response_model=list[TemplateOut])
def list_templates(ctx: Context = Depends(get_context), db: Session = Depends(get_db)) -> list[TemplateOut]:
    rows = (db.query(Template).filter(Template.tenant_id == ctx.tenant_id)
            .order_by(Template.created_at.desc()).limit(500).all())
    return [TemplateOut.model_validate(t) for t in rows]


@router.post("", response_model=TemplateOut, status_code=201)
def create_template(body: TemplateCreateRequest, ctx: Context = Depends(require_writer),
                    db: Session = Depends(get_db)) -> TemplateOut:
    bad = [c for c in body.field_mappings.values() if c not in FIELDS_BY_CODE]
    if bad:
        raise HTTPException(status_code=422, detail="field_mappings values must be canonical field codes.")
    t = Template(tenant_id=ctx.tenant_id, name=body.name, sender_identifier=body.sender_identifier,
                 field_mappings={str(k)[:255]: v for k, v in body.field_mappings.items()},
                 is_standard=False, is_deletable=True, created_by=ctx.actor)
    db.add(t)
    db.flush()
    audit_service.log_action(db, ctx.tenant_id, None, "TEMPLATE_CREATED", "TEMPLATE", t.id,
                             after={"name": t.name}, actor=ctx.actor, actor_user_id=ctx.user_id)
    db.commit()
    return TemplateOut.model_validate(t)


@router.get("/{template_id}", response_model=TemplateOut)
def get_template(template_id: str, ctx: Context = Depends(get_context), db: Session = Depends(get_db)) -> TemplateOut:
    t = db.query(Template).filter(Template.id == template_id, Template.tenant_id == ctx.tenant_id).first()
    if t is None:
        raise HTTPException(status_code=404, detail="Template not found.")
    return TemplateOut.model_validate(t)
