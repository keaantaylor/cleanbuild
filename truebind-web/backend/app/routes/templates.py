from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.templates import Template
from ..schemas.reports import TemplateCreateRequest, TemplateOut

router = APIRouter(prefix="/api/v1/templates", tags=["templates"])


@router.get("", response_model=list[TemplateOut])
def list_templates(db: Session = Depends(get_db)) -> list[TemplateOut]:
    return [TemplateOut.model_validate(t) for t in db.query(Template).order_by(Template.created_at.desc()).all()]


@router.post("", response_model=TemplateOut)
def create_template(body: TemplateCreateRequest, db: Session = Depends(get_db)) -> TemplateOut:
    template = Template(**body.model_dump(), is_standard=False, is_deletable=True)
    db.add(template)
    db.commit()
    db.refresh(template)
    return TemplateOut.model_validate(template)


@router.get("/{template_id}", response_model=TemplateOut)
def get_template(template_id: str, db: Session = Depends(get_db)) -> TemplateOut:
    template = db.get(Template, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail=f"Template {template_id} not found")
    return TemplateOut.model_validate(template)
