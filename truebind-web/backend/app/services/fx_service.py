"""ECB euro foreign-exchange reference rates.

- refresh() loads the ECB XML feed (daily or the 90-day history) into
  fx_rates: units of each currency per 1 EUR, per ECB business day.
- rate_for() finds the rate on a date, or the latest ECB business day before
  it within LOOKBACK_DAYS (weekends and TARGET holidays have no fixing).
- convert() converts exactly (Decimal, cross rate through EUR, rounded half
  up to the cent) and always says which rate date it used. When a rate is
  missing it returns NOT_ASSESSED with the reason -- a conversion is never
  guessed or silently skipped.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import httpx
from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..models.channels import FxRate

log = logging.getLogger("truebind.fx")

LOOKBACK_DAYS = 7
_NS = "{http://www.ecb.int/vocabulary/2002-08-01/eurofxref}"
CENT = Decimal("0.01")


class FxFeedError(ValueError):
    pass


@dataclass(frozen=True)
class Conversion:
    status: str  # "OK" | "NOT_ASSESSED"
    amount: Decimal | None
    rate: Decimal | None
    rate_date: date | None
    reason: str | None = None
    source: str = "ECB euro reference rates"


def parse_feed(xml_bytes: bytes) -> dict[date, dict[str, Decimal]]:
    try:
        root = SafeET.fromstring(xml_bytes, forbid_dtd=True)
    except DefusedXmlException as exc:
        raise FxFeedError("unexpected DTD or entities in the ECB feed") from exc
    except SafeET.ParseError as exc:
        raise FxFeedError("the ECB feed is not valid XML") from exc
    out: dict[date, dict[str, Decimal]] = {}
    for day in root.iter(f"{_NS}Cube"):
        when = day.get("time")
        if not when:
            continue
        rates: dict[str, Decimal] = {}
        for cube in day:
            ccy, rate = cube.get("currency"), cube.get("rate")
            if not ccy or not rate or len(ccy) != 3:
                continue
            try:
                value = Decimal(rate)
            except InvalidOperation:
                continue
            if value > 0:
                rates[ccy.upper()] = value
        if rates:
            out[date.fromisoformat(when)] = rates
    if not out:
        raise FxFeedError("the ECB feed contained no rates")
    return out


def _fetch(url: str) -> bytes:
    r = httpx.get(url, timeout=30, follow_redirects=True)
    r.raise_for_status()
    return r.content


def refresh(db: Session, fetch: Callable[[str], bytes] | None = None) -> int:
    """Upsert the feed into fx_rates; returns the number of (day, currency) rows written."""
    feed = parse_feed((fetch or _fetch)(config.ECB_RATES_URL))
    written = 0
    for day, rates in feed.items():
        for ccy, rate in rates.items():
            existing = db.get(FxRate, (day, ccy))
            if existing is None:
                db.add(FxRate(rate_date=day, currency=ccy, rate=rate, source="ECB"))
                written += 1
            elif existing.rate != rate:
                existing.rate = rate
                written += 1
    db.commit()
    log.info("ECB rates refreshed: %d rows over %d days", written, len(feed))
    return written


def rate_for(db: Session, currency: str, on: date) -> tuple[Decimal, date] | None:
    ccy = currency.upper()
    if ccy == "EUR":
        return Decimal(1), on
    row = db.execute(
        select(FxRate)
        .where(FxRate.currency == ccy, FxRate.rate_date <= on, FxRate.rate_date >= on - timedelta(days=LOOKBACK_DAYS))
        .order_by(FxRate.rate_date.desc())
        .limit(1)
    ).scalar_one_or_none()
    return (Decimal(row.rate), row.rate_date) if row else None


def convert(db: Session, amount: Decimal, from_ccy: str, to_ccy: str, on: date) -> Conversion:
    src, dst = from_ccy.upper(), to_ccy.upper()
    if src == dst:
        return Conversion("OK", amount.quantize(CENT, rounding=ROUND_HALF_UP), Decimal(1), on)
    a, b = rate_for(db, src, on), rate_for(db, dst, on)
    missing = [c for c, r in ((src, a), (dst, b)) if r is None]
    if missing or a is None or b is None:
        return Conversion(
            "NOT_ASSESSED",
            None,
            None,
            None,
            f"No ECB reference rate for {', '.join(missing)} on or within {LOOKBACK_DAYS} days before "
            f"{on.isoformat()}.",
        )
    rate = b[0] / a[0]
    rate_date = min(a[1], b[1])
    return Conversion("OK", (amount * rate).quantize(CENT, rounding=ROUND_HALF_UP), rate, rate_date)
