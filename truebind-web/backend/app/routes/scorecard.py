"""Coverholder / TPA scorecard (P6).

GET /api/v1/scorecard?since=YYYY-MM-DD   one row per sender over processed reports (data:read)
Metrics that have nothing to be computed from are null ("not assessed"), never zero.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..security.auth import Context, require_reader
from ..services import scorecard_service

router = APIRouter(prefix="/api/v1", tags=["scorecard"])


class SenderScore(BaseModel):
    sender: str
    reports: int
    rows: int
    first_report_at: datetime
    latest_report_at: datetime
    latest_grade: str | None
    latest_score: float | None
    average_score: float | None
    score_trend: list[float]
    exceptions_per_1000_rows: float | None
    resubmissions_per_1000_rows: float | None
    binder_breaches: int
    sanctions_open_matches: int
    leakage_exposure: dict[str, str]
    mapping_first_time_right_pct: float


class ScorecardOut(BaseModel):
    since: date | None
    senders: list[SenderScore]
    not_assessed: list[str]


@router.get("/scorecard", response_model=ScorecardOut)
def scorecard(
    since: date | None = Query(default=None), ctx: Context = Depends(require_reader), db: Session = Depends(get_db)
) -> ScorecardOut:
    start = datetime(since.year, since.month, since.day, tzinfo=UTC) if since else None
    rows = scorecard_service.build(db, ctx.tenant_id, start)
    return ScorecardOut(
        since=since,
        senders=[SenderScore(**r) for r in rows],
        not_assessed=[
            "Timeliness: submission deadlines per sender are not recorded yet, so on-time delivery is not scored."
        ],
    )
