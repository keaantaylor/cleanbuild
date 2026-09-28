"""Shared steps for the golden module suites."""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

Key = tuple[str, str | None, int | None, str]


def load_key(folder: Path) -> dict[str, Any]:
    key: dict[str, Any] = json.loads((folder / "answer_key.json").read_text(encoding="utf-8"))
    return key


def seed_fx(db: Session, per_eur: dict[str, str], start: dt.date, end: dt.date) -> None:
    from app.models.channels import FxRate

    day = start
    while day <= end:
        db.add_all(FxRate(rate_date=day, currency=c, rate=Decimal(r), source="TEST") for c, r in per_eur.items())
        day += dt.timedelta(days=1)
    db.commit()


def process(api: Any, path: Path, before_confirm: Callable[[str], None] | None = None) -> str:
    """Upload, (optionally configure), confirm the proposed mapping as-is, process."""
    from backend_conftest import run_jobs

    rid: str = api.ingest(path.name, path.read_bytes())
    if before_confirm is not None:
        before_confirm(rid)
    api.confirm_all(rid)
    r = api.post(f"/api/v1/reports/{rid}/process")
    assert r.status_code == 202, r.text
    run_jobs()
    assert api.get(f"/api/v1/reports/{rid}").json()["status"] == "COMPLETE"
    return rid


def findings(api: Any, rid: str, module: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = api.get(
        f"/api/v1/reports/{rid}/checks/findings", params={"module": module, "limit": 1000}
    ).json()["items"]
    return items


def run_state(api: Any, rid: str, module: str) -> dict[str, Any]:
    runs: list[dict[str, Any]] = api.get(f"/api/v1/reports/{rid}/checks").json()
    return next(r for r in runs if r["module"] == module)


def score(found: list[dict[str, Any]], expected: list[dict[str, Any]]) -> tuple[float, float, set[Key], set[Key]]:
    got = {(f["rule_code"], f["sheet_name"], f["row_number"], f["status"]) for f in found}
    want = {(e["rule"], e["sheet"], e["row"], e["status"]) for e in expected}
    tp = got & want
    precision = len(tp) / len(got) if got else 1.0
    recall = len(tp) / len(want) if want else 1.0
    return precision, recall, got - want, want - got


def assert_amounts(found: list[dict[str, Any]], expected: list[dict[str, Any]]) -> None:
    by_key = {(f["rule_code"], f["sheet_name"], f["row_number"]): f for f in found}
    for e in expected:
        if "amount" in e:
            f = by_key[(e["rule"], e["sheet"], e["row"])]
            assert (f["amount"], f["currency"]) == (e["amount"], e["currency"]), (e, f)
