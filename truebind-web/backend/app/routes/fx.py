"""ECB reference rates and exact conversion.

GET  /api/v1/fx/rates?on=YYYY-MM-DD                        rates per EUR in force on that date (data:read)
GET  /api/v1/fx/convert?amount=&from_ccy=&to_ccy=&on=      exact conversion or NOT_ASSESSED (data:read)
POST /api/v1/fx/refresh                                    load the ECB feed now (org:manage, audited)
Amounts and rates are decimal strings -- never binary floats.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.channels import FxRate
from ..security.auth import Context, require, require_reader
from ..security.permissions import Permission
from ..services import audit_service, fx_service

router = APIRouter(prefix="/api/v1/fx", tags=["fx"])
_org_manage = require(Permission.ORG_MANAGE)
_CCY = r"^[A-Za-z]{3}$"


class RatesOut(BaseModel):
    requested: date
    rate_date: date | None
    base: str
    rates: dict[str, str]
    source: str


class ConversionOut(BaseModel):
    status: str
    amount: str | None
    currency: str
    rate: str | None
    rate_date: date | None
    reason: str | None
    source: str


class RefreshOut(BaseModel):
    rows_written: int
    latest_rate_date: date | None


@router.get("/rates", response_model=RatesOut)
def rates(on: date = Query(default_factory=date.today), ctx: Context = Depends(require_reader),
          db: Session = Depends(get_db)) -> RatesOut:  # fmt: skip
    latest = db.execute(select(func.max(FxRate.rate_date)).where(FxRate.rate_date <= on)).scalar()
    rows = db.execute(select(FxRate).where(FxRate.rate_date == latest)).scalars().all() if latest else []
    return RatesOut(
        requested=on,
        rate_date=latest,
        base="EUR",
        rates={r.currency: str(r.rate) for r in rows},
        source="ECB euro reference rates",
    )


@router.get("/convert", response_model=ConversionOut)
def convert(
    amount: str = Query(max_length=32),
    from_ccy: str = Query(pattern=_CCY),
    to_ccy: str = Query(pattern=_CCY),
    on: date = Query(default_factory=date.today),
    ctx: Context = Depends(require_reader),
    db: Session = Depends(get_db),
) -> ConversionOut:
    try:
        value = Decimal(amount)
    except InvalidOperation as exc:
        raise HTTPException(status_code=422, detail="amount must be a decimal number") from exc
    if not value.is_finite():
        raise HTTPException(status_code=422, detail="amount must be a decimal number")
    c = fx_service.convert(db, value, from_ccy, to_ccy, on)
    return ConversionOut(
        status=c.status,
        amount=str(c.amount) if c.amount is not None else None,
        currency=to_ccy.upper(),
        rate=str(c.rate) if c.rate is not None else None,
        rate_date=c.rate_date,
        reason=c.reason,
        source=c.source,
    )


@router.post("/refresh", response_model=RefreshOut)
def refresh(ctx: Context = Depends(_org_manage), db: Session = Depends(get_db)) -> RefreshOut:
    try:
        written = fx_service.refresh(db)
    except (fx_service.FxFeedError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=502, detail="The ECB rate feed could not be loaded. Try again later.") from exc
    latest = db.execute(select(func.max(FxRate.rate_date))).scalar()
    audit_service.log_action(
        db, ctx.tenant_id, None, "FX_RATES_REFRESHED", "FX_RATES", "ECB",
        after={"rows_written": written, "latest": latest.isoformat() if latest else None},
        actor=ctx.actor, actor_user_id=ctx.user_id,
    )  # fmt: skip
    db.commit()
    return RefreshOut(rows_written=written, latest_rate_date=latest)
