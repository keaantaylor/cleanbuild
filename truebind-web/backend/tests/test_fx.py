"""P2.5 -- ECB euro reference rates and exact conversion.

Acceptance:
- the ECB XML feed (their real format) loads into fx_rates, idempotently;
  hostile XML (DTD / entities) and empty feeds are refused;
- conversions are exact Decimal cross rates through EUR, rounded half up to
  the cent, and state the rate date used;
- a date without a fixing (weekend/holiday) uses the latest earlier ECB day
  within 7 days; beyond that, or for an unknown currency, the result is
  NOT_ASSESSED with a reason -- never a guess;
- the API returns amounts and rates as decimal strings; refresh needs
  org:manage and is audited; a feed outage is a clean 502.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import httpx
import pytest
from app.models.audit import AuditLogEntry
from app.models.channels import FxRate
from app.services import fx_service
from conftest import PASSWORD, Api
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01" xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
  <gesmes:subject>Reference rates</gesmes:subject>
  <gesmes:Sender><gesmes:name>European Central Bank</gesmes:name></gesmes:Sender>
  <Cube>
    <Cube time="2026-09-25">
      <Cube currency="USD" rate="1.1700"/>
      <Cube currency="GBP" rate="0.8650"/>
      <Cube currency="JPY" rate="171.50"/>
    </Cube>
    <Cube time="2026-09-24">
      <Cube currency="USD" rate="1.1650"/>
      <Cube currency="GBP" rate="0.8600"/>
    </Cube>
  </Cube>
</gesmes:Envelope>"""


def _load(db: Session, feed: bytes = FEED) -> int:
    return fx_service.refresh(db, fetch=lambda url: feed)


def test_feed_loads_idempotently(db: Session) -> None:
    assert _load(db) == 5
    assert _load(db) == 0, "loading the same feed again writes nothing"
    assert db.get(FxRate, (date(2026, 9, 25), "GBP")).rate == Decimal("0.8650")  # type: ignore[union-attr]


@pytest.mark.parametrize(
    "feed",
    [
        b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><x>&a;</x>',
        b"<not-closed",
        b'<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01"/>',
    ],
)
def test_hostile_or_empty_feeds_are_refused(db: Session, feed: bytes) -> None:
    with pytest.raises(fx_service.FxFeedError):
        _load(db, feed)


def test_exact_cross_rate_conversion(db: Session) -> None:
    _load(db)
    c = fx_service.convert(db, Decimal("1000.00"), "GBP", "USD", date(2026, 9, 25))
    assert c.status == "OK" and c.rate_date == date(2026, 9, 25)
    assert c.amount == (Decimal("1000.00") * Decimal("1.1700") / Decimal("0.8650")).quantize(Decimal("0.01"))
    assert c.amount == Decimal("1352.60")
    eur = fx_service.convert(db, Decimal("100"), "EUR", "JPY", date(2026, 9, 25))
    assert eur.amount == Decimal("17150.00")
    same = fx_service.convert(db, Decimal("12.345"), "GBP", "GBP", date(2026, 9, 25))
    assert same.amount == Decimal("12.35"), "half up to the cent"


def test_weekend_uses_the_previous_fixing_and_says_so(db: Session) -> None:
    _load(db)
    c = fx_service.convert(db, Decimal("10"), "EUR", "USD", date(2026, 9, 27))  # a Sunday
    assert c.status == "OK" and c.rate_date == date(2026, 9, 25) and c.amount == Decimal("11.70")


def test_missing_rates_are_not_assessed(db: Session) -> None:
    _load(db)
    stale = fx_service.convert(db, Decimal("10"), "EUR", "USD", date(2026, 10, 30))
    assert stale.status == "NOT_ASSESSED" and stale.amount is None and "USD" in (stale.reason or "")
    unknown = fx_service.convert(db, Decimal("10"), "EUR", "XYZ", date(2026, 9, 25))
    assert unknown.status == "NOT_ASSESSED" and "XYZ" in (unknown.reason or "")
    only_24th = fx_service.convert(db, Decimal("10"), "EUR", "JPY", date(2026, 9, 24))
    assert only_24th.status == "NOT_ASSESSED", "no JPY fixing on or before the 24th"


def test_api_returns_decimal_strings(api: Api, db: Session) -> None:
    _load(db)
    r = api.get(
        "/api/v1/fx/convert", params={"amount": "1000.00", "from_ccy": "GBP", "to_ccy": "USD", "on": "2026-09-25"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["amount"] == "1352.60" and body["status"] == "OK" and isinstance(body["rate"], str)
    miss = api.get("/api/v1/fx/convert", params={"amount": "1", "from_ccy": "EUR", "to_ccy": "XYZ"}).json()
    assert miss["status"] == "NOT_ASSESSED" and miss["amount"] is None and miss["reason"]
    assert (
        api.get("/api/v1/fx/convert", params={"amount": "NaN", "from_ccy": "EUR", "to_ccy": "USD"}).status_code == 422
    )
    rates = api.get("/api/v1/fx/rates", params={"on": "2026-09-26"}).json()
    assert rates["rate_date"] == "2026-09-25" and rates["rates"]["GBP"] == "0.86500000"


def test_refresh_needs_org_manage_and_is_audited(api: Api, db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fx_service, "_fetch", lambda url: FEED)
    r = api.post("/api/v1/fx/refresh")
    assert r.status_code == 200 and r.json() == {"rows_written": 5, "latest_rate_date": "2026-09-25"}
    assert db.query(AuditLogEntry).filter_by(action_type="FX_RATES_REFRESHED").count() == 1

    def down(url: str) -> bytes:
        raise httpx.ConnectError("unreachable")

    monkeypatch.setattr(fx_service, "_fetch", down)
    assert api.post("/api/v1/fx/refresh").status_code == 502
    token = api.post("/api/v1/org/invitations", json={"email": "an@a.example", "role": "ANALYST"}).json()[
        "accept_token"
    ]
    analyst = TestClient(api.client.app)
    me = analyst.post(
        "/api/v1/auth/invitations/accept", json={"token": token, "display_name": "A", "password": PASSWORD}
    ).json()
    assert analyst.post("/api/v1/fx/refresh", headers={"X-CSRF-Token": me["csrf_token"]}).status_code == 403
