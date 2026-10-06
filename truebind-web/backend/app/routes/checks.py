"""Check modules on a report, their findings, and binders.

GET    /api/v1/reports/{id}/checks                         every module's latest run and coverage (data:read)
POST   /api/v1/reports/{id}/checks/{module}/run            run one module again (data:write, audited)
GET    /api/v1/reports/{id}/checks/findings                findings, filterable, paginated (data:read)
PATCH  /api/v1/reports/{id}/checks/findings/{finding_id}   confirm or dismiss with a note (data:write, audited)
PUT    /api/v1/reports/{id}/binder                         assign or clear the binder; re-runs the binder check
GET    /api/v1/binders   POST /api/v1/binders   DELETE /api/v1/binders/{binder_id}
Amounts are decimal strings with an ISO 4217 currency -- never floats.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from ..checks import LABELS, REGISTRY
from ..checks.base import ISO_4217
from ..database import get_db
from ..models._util import utcnow
from ..models.modules import Binder, Finding, ModuleRun
from ..models.reports import Report
from ..schemas.reports import Page
from ..security.auth import Context, require_reader, require_writer
from ..services import audit_service, module_service
from .deps import Paging, get_report_or_404

router = APIRouter(prefix="/api/v1", tags=["checks"])
_SEV = case(
    (Finding.severity == "CRITICAL", 0), (Finding.severity == "HIGH", 1), (Finding.severity == "MEDIUM", 2), else_=3
)


class RuleOut(BaseModel):
    code: str
    label: str
    assessed: int
    not_assessed: int
    reasons: list[str]


class ModuleRunOut(BaseModel):
    module: str
    label: str
    state: str  # ASSESSED | PARTIAL | NOT_ASSESSED | NOT_RUN
    reason: str | None
    rules: list[RuleOut]
    finding_count: int
    open_count: int
    ran_at: datetime | None
    ran_by: str | None
    coverage_statement: str
    exposure: dict[str, str] = Field(default_factory=dict)  # FAIL amounts per ISO currency, never summed across
    unpriced_findings: int = 0  # FAIL findings with an amount but no stated currency


class FindingOut(BaseModel):
    id: str
    module: str
    rule_code: str
    status: str
    severity: str
    title: str
    explanation: str
    sheet_name: str | None
    row_number: int | None
    field_code: str | None
    source_column: str | None
    claim_row_id: str | None
    claim_reference: str | None
    amount: str | None
    currency: str | None
    evidence: dict[str, Any] | None
    disposition: str
    disposition_note: str | None
    disposed_by: str | None
    disposed_at: datetime | None


class DispositionIn(BaseModel):
    disposition: Literal["OPEN", "CONFIRMED", "DISMISSED"]
    note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _dismiss_needs_reason(self) -> DispositionIn:
        if self.disposition == "DISMISSED" and not (self.note or "").strip():
            raise ValueError("Dismissing a finding needs a note saying why.")
        return self


class BinderIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    umr: str | None = Field(default=None, max_length=64)
    coverholder: str | None = Field(default=None, max_length=200)
    inception_date: date
    expiry_date: date
    currencies: list[str] = Field(default_factory=list, max_length=50)
    limit_currency: str
    claims_authority: Decimal | None = Field(default=None, ge=0, max_digits=16, decimal_places=2)
    aggregate_limit: Decimal | None = Field(default=None, ge=0, max_digits=16, decimal_places=2)

    @field_validator("currencies")
    @classmethod
    def _iso_list(cls, v: list[str]) -> list[str]:
        out = sorted({c.strip().upper() for c in v})
        bad = [c for c in out if c not in ISO_4217]
        if bad:
            raise ValueError(f"not ISO 4217 currency codes: {', '.join(bad)}")
        return out

    @field_validator("limit_currency")
    @classmethod
    def _iso(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in ISO_4217:
            raise ValueError("limit_currency must be an ISO 4217 currency code")
        return v

    @model_validator(mode="after")
    def _period(self) -> BinderIn:
        if self.expiry_date < self.inception_date:
            raise ValueError("expiry_date must not be before inception_date")
        return self


class BinderOut(BaseModel):
    id: str
    name: str
    umr: str | None
    coverholder: str | None
    inception_date: date
    expiry_date: date
    currencies: list[str]
    limit_currency: str
    claims_authority: str | None
    aggregate_limit: str | None
    created_at: datetime
    created_by: str


class AssignBinderIn(BaseModel):
    binder_id: str | None = Field(default=None, max_length=36)


def coverage_statement(label: str, state: str, rules: list[dict[str, Any]], reason: str | None) -> str:
    if state == "NOT_RUN":
        return f"{label} has not run on this report yet."
    if state == "NOT_ASSESSED":
        return f"{label} was not assessed: {(reason or 'no reason recorded').rstrip('.')}."
    parts = [
        f"{r['label']}: {r['assessed']} assessed"
        + (f", {r['not_assessed']} not assessed ({'; '.join(r['reasons'])})" if r["not_assessed"] else "")
        for r in rules
    ]
    return f"{label} — " + ". ".join(parts) + "."


def _run_out(db: Session, report: Report, module: str, run: ModuleRun | None) -> ModuleRunOut:
    label = LABELS[module]
    if run is None:
        return ModuleRunOut(
            module=module,
            label=label,
            state="NOT_RUN",
            reason=None,
            rules=[],
            finding_count=0,
            open_count=0,
            ran_at=None,
            ran_by=None,
            coverage_statement=coverage_statement(label, "NOT_RUN", [], None),
        )
    open_count = (
        db.query(func.count(Finding.id))
        .filter(
            Finding.report_id == report.id,
            Finding.tenant_id == report.tenant_id,
            Finding.module == module,
            Finding.disposition == "OPEN",
        )
        .scalar()
        or 0
    )
    exposure: dict[str, Decimal] = {}
    unpriced = 0
    for amount, ccy in db.query(Finding.amount, Finding.currency).filter(
        Finding.report_id == report.id,
        Finding.tenant_id == report.tenant_id,
        Finding.module == module,
        Finding.status == "FAIL",
        Finding.disposition != "DISMISSED",
        Finding.amount.is_not(None),
    ):
        if ccy and amount is not None:
            exposure[ccy] = exposure.get(ccy, Decimal(0)) + amount
        else:
            unpriced += 1
    return ModuleRunOut(
        module=module,
        label=label,
        exposure={c: str(v) for c, v in sorted(exposure.items())},
        unpriced_findings=unpriced,
        state=run.state,
        reason=run.reason,
        rules=[RuleOut(**r) for r in run.rules],
        finding_count=run.finding_count,
        open_count=open_count,
        ran_at=run.ran_at,
        ran_by=run.ran_by,
        coverage_statement=coverage_statement(label, run.state, run.rules, run.reason),
    )


def finding_out(f: Finding) -> FindingOut:
    return FindingOut(
        id=f.id,
        module=f.module,
        rule_code=f.rule_code,
        status=f.status,
        severity=f.severity,
        title=f.title,
        explanation=f.explanation,
        sheet_name=f.sheet_name,
        row_number=f.row_number,
        field_code=f.field_code,
        source_column=f.source_column,
        claim_row_id=f.claim_row_id,
        claim_reference=f.claim_reference,
        amount=str(f.amount) if f.amount is not None else None,
        currency=f.currency,
        evidence=f.evidence,
        disposition=f.disposition,
        disposition_note=f.disposition_note,
        disposed_by=f.disposed_by,
        disposed_at=f.disposed_at,
    )


def _module_or_404(module: str) -> str:
    if module not in REGISTRY:
        raise HTTPException(status_code=404, detail="Unknown check module.")
    return module


def _require_complete(report: Report) -> None:
    if report.status != "COMPLETE":
        raise HTTPException(status_code=409, detail="Checks run on a processed report.")


@router.get("/reports/{report_id}/checks", response_model=list[ModuleRunOut])
def list_checks(
    report_id: str, ctx: Context = Depends(require_reader), db: Session = Depends(get_db)
) -> list[ModuleRunOut]:
    report = get_report_or_404(db, ctx, report_id)
    runs = {
        r.module: r
        for r in db.query(ModuleRun).filter(ModuleRun.report_id == report.id, ModuleRun.tenant_id == ctx.tenant_id)
    }
    return [_run_out(db, report, m, runs.get(m)) for m in REGISTRY]


@router.post("/reports/{report_id}/checks/{module}/run", response_model=ModuleRunOut)
def run_check(
    report_id: str, module: str, ctx: Context = Depends(require_writer), db: Session = Depends(get_db)
) -> ModuleRunOut:
    report = get_report_or_404(db, ctx, report_id)
    _module_or_404(module)
    _require_complete(report)
    run = module_service.run_module(db, report, module, actor=ctx.actor, actor_user_id=ctx.user_id)
    db.commit()
    return _run_out(db, report, module, run)


@router.get("/reports/{report_id}/checks/findings", response_model=Page[FindingOut])
def list_findings(
    report_id: str,
    module: str | None = Query(default=None, max_length=32),
    status: str | None = Query(default=None, pattern="^(FAIL|REVIEW)$"),
    disposition: str | None = Query(default=None, pattern="^(OPEN|CONFIRMED|DISMISSED)$"),
    paging: Paging = Depends(),
    ctx: Context = Depends(require_reader),
    db: Session = Depends(get_db),
) -> Page[FindingOut]:
    report = get_report_or_404(db, ctx, report_id)
    q = db.query(Finding).filter(Finding.report_id == report.id, Finding.tenant_id == ctx.tenant_id)
    if module:
        q = q.filter(Finding.module == _module_or_404(module))
    if status:
        q = q.filter(Finding.status == status)
    if disposition:
        q = q.filter(Finding.disposition == disposition)
    total = q.with_entities(func.count(Finding.id)).scalar() or 0
    rows = (
        q.order_by(_SEV, Finding.module, Finding.sheet_name, Finding.row_number, Finding.rule_code)
        .limit(paging.limit)
        .offset(paging.offset)
        .all()
    )
    return Page(items=[finding_out(f) for f in rows], total=total, limit=paging.limit, offset=paging.offset)


@router.patch("/reports/{report_id}/checks/findings/{finding_id}", response_model=FindingOut)
def dispose_finding(
    report_id: str,
    finding_id: str,
    body: DispositionIn,
    ctx: Context = Depends(require_writer),
    db: Session = Depends(get_db),
) -> FindingOut:
    report = get_report_or_404(db, ctx, report_id)
    f = (
        db.query(Finding)
        .filter(Finding.id == finding_id, Finding.report_id == report.id, Finding.tenant_id == ctx.tenant_id)
        .first()
    )
    if f is None:
        raise HTTPException(status_code=404, detail="Finding not found.")
    before = {"disposition": f.disposition, "note": f.disposition_note}
    f.disposition, f.disposition_note = body.disposition, (body.note or "").strip() or None
    f.disposed_by, f.disposed_at = (ctx.actor, utcnow()) if body.disposition != "OPEN" else (None, None)
    audit_service.log_action(
        db,
        ctx.tenant_id,
        report.id,
        "FINDING_DISPOSED",
        "FINDING",
        f.id,
        before=before,
        after={"disposition": f.disposition, "note": f.disposition_note},
        actor=ctx.actor,
        actor_user_id=ctx.user_id,
    )
    db.commit()
    return finding_out(f)


def _binder_out(b: Binder) -> BinderOut:
    c = module_service.binder_config(b)
    return BinderOut(**c, created_at=b.created_at, created_by=b.created_by)


def _binder_or_404(db: Session, ctx: Context, binder_id: str) -> Binder:
    b = db.query(Binder).filter(Binder.id == binder_id, Binder.tenant_id == ctx.tenant_id).first()
    if b is None:
        raise HTTPException(status_code=404, detail="Binder not found.")
    return b


@router.put("/reports/{report_id}/binder", response_model=list[ModuleRunOut])
def assign_binder(
    report_id: str, body: AssignBinderIn, ctx: Context = Depends(require_writer), db: Session = Depends(get_db)
) -> list[ModuleRunOut]:
    report = get_report_or_404(db, ctx, report_id)
    if body.binder_id is not None:
        _binder_or_404(db, ctx, body.binder_id)
    before = {"binder_id": report.binder_id}
    report.binder_id = body.binder_id
    audit_service.log_action(
        db,
        ctx.tenant_id,
        report.id,
        "REPORT_BINDER_ASSIGNED",
        "REPORT",
        report.id,
        before=before,
        after={"binder_id": report.binder_id},
        actor=ctx.actor,
        actor_user_id=ctx.user_id,
    )
    if report.status == "COMPLETE":
        module_service.run_module(db, report, "binder", actor=ctx.actor, actor_user_id=ctx.user_id)
    db.commit()
    return list_checks(report_id, ctx, db)


@router.get("/binders", response_model=list[BinderOut])
def list_binders(ctx: Context = Depends(require_reader), db: Session = Depends(get_db)) -> list[BinderOut]:
    rows = (
        db.query(Binder).filter(Binder.tenant_id == ctx.tenant_id).order_by(Binder.inception_date.desc(), Binder.name)
    )
    return [_binder_out(b) for b in rows]


@router.post("/binders", response_model=BinderOut, status_code=201)
def create_binder(body: BinderIn, ctx: Context = Depends(require_writer), db: Session = Depends(get_db)) -> BinderOut:
    b = Binder(tenant_id=ctx.tenant_id, created_by=ctx.actor[:255], **body.model_dump())
    db.add(b)
    db.flush()
    out = _binder_out(b)
    audit_service.log_action(
        db,
        ctx.tenant_id,
        None,
        "BINDER_CREATED",
        "BINDER",
        b.id,
        after=out.model_dump(mode="json"),
        actor=ctx.actor,
        actor_user_id=ctx.user_id,
    )
    db.commit()
    return out


@router.delete("/binders/{binder_id}", status_code=204)
def delete_binder(binder_id: str, ctx: Context = Depends(require_writer), db: Session = Depends(get_db)) -> Response:
    b = _binder_or_404(db, ctx, binder_id)
    in_use = db.query(func.count(Report.id)).filter(Report.binder_id == b.id, Report.tenant_id == ctx.tenant_id)
    if (in_use.scalar() or 0) > 0:
        raise HTTPException(status_code=409, detail="Reports are assigned to this binder; reassign them first.")
    audit_service.log_action(
        db,
        ctx.tenant_id,
        None,
        "BINDER_DELETED",
        "BINDER",
        b.id,
        before=_binder_out(b).model_dump(mode="json"),
        actor=ctx.actor,
        actor_user_id=ctx.user_id,
    )
    db.delete(b)
    db.commit()
    return Response(status_code=204)
