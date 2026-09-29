"""P1.6 -- money is Decimal with an ISO 4217 currency, never float.

Acceptance:
- every money column is NUMERIC(18,2) (exact on PostgreSQL) through the
  Money type; nothing money-like is declared Float any more;
- values are normalised to 2 dp (ROUND_HALF_UP) once, at the boundary, from
  whatever the engine produced (float artefacts like 0.1 + 0.2 disappear);
  NaN / infinity / non-numbers are stored as NULL, never as a number;
- reading returns Decimal; SQL aggregation of money stays exact;
- each persisted claim row keeps its currency;
- the golden regression is unaffected (verify's golden step).
"""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Any

import pytest
from app.database import Base
from app.models.leakage import LeakageFlag
from app.models.money import Money, to_money
from app.models.reports import ClaimRow, ValidationResult
from conftest import IS_PG, Api, xlsx_bytes
from sqlalchemy import Float, inspect, text
from sqlalchemy.orm import Session

MONEY_COLUMNS = {
    ClaimRow: {
        "paid_amount",
        "paid_this_month",
        "previously_paid",
        "reserve_amount",
        "fees_paid_this_month",
        "fees_previously_paid",
        "fees_reserve",
        "fees_paid_to_date",
        "incurred_indemnity",
        "incurred_amount",
    },
    ValidationResult: {"delta"},
    LeakageFlag: {"amount_exposure"},
}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (0.1 + 0.2, Decimal("0.30")),
        (1234.565, Decimal("1234.57")),
        (Decimal("1234.565"), Decimal("1234.57")),
        (-0.005, Decimal("-0.01")),
        ("1500", Decimal("1500.00")),
        (7, Decimal("7.00")),
        (None, None),
        (math.nan, None),
        (math.inf, None),
        ("not money", None),
    ],
)
def test_to_money_normalises_once(raw: Any, expected: Decimal | None) -> None:
    got = to_money(raw)
    assert got == expected
    if got is not None:
        assert got.as_tuple().exponent == -2


def test_every_money_column_uses_the_money_type() -> None:
    for model, names in MONEY_COLUMNS.items():
        cols = {c.name: c for c in inspect(model).columns}
        for name in names:
            assert isinstance(cols[name].type, Money), f"{model.__name__}.{name}"
    offenders = [
        f"{t.name}.{c.name}"
        for t in Base.metadata.sorted_tables
        for c in t.columns
        if isinstance(c.type, Float)
        and any(w in c.name for w in ("amount", "paid", "reserve", "incurred", "fee", "delta"))
    ]
    assert not offenders, f"money-like Float columns: {offenders}"


def test_persisted_amounts_are_exact_decimals(api: Api, db: Session) -> None:
    rows: list[list[Any]] = [
        [
            "Claim Reference",
            "Insured Name",
            "Date of Loss",
            "Claim Status",
            "Currency",
            "Paid to Date",
            "Outstanding Reserve",
            "Total Incurred",
        ],
        ["M-1", "Alpha", "2024-01-15", "Open", "EUR", 0.1, 0.2, 0.3],
        ["M-2", "Beta", "2024-01-16", "Open", "USD", 1234.565, 10, 1244.565],
        ["M-3", "Gamma", "2024-01-17", "Open", "GBP", "1,000.10", "2,000.20", "3,000.30"],
    ]
    rid, _ = api.full_run("money.xlsx", xlsx_bytes(rows))
    got = {r.claim_reference: r for r in db.query(ClaimRow).filter_by(report_id=rid)}
    assert got["M-1"].paid_amount == Decimal("0.10") and got["M-1"].incurred_amount == Decimal("0.30")
    assert isinstance(got["M-1"].paid_amount, Decimal)
    assert got["M-2"].paid_amount == Decimal("1234.57")
    assert got["M-3"].incurred_amount == Decimal("3000.30")
    assert {r.currency for r in got.values()} == {"EUR", "USD", "GBP"}
    claims = api.get(f"/api/v1/reports/{rid}/claims").json()["items"]
    m1 = next(c for c in claims if c["claim_reference"] == "M-1")
    assert m1["paid_amount"] == 0.1 and m1["incurred_amount"] == 0.3, "API carries the exact 2-dp value"


def test_money_aggregation_is_exact(api: Api) -> None:
    header = [
        "Claim Reference",
        "Insured Name",
        "Date of Loss",
        "Claim Status",
        "Currency",
        "Paid to Date",
        "Outstanding Reserve",
        "Total Incurred",
    ]
    # Ten rows that do not reconcile (incurred 0.10 != 0.10 + 0.05, beyond the 0.01 tolerance).
    rows: list[list[Any]] = [header] + [
        [f"A-{i}", f"Ins {i}", "2024-01-15", "Open", "EUR", 0.1, 0.05, 0.1] for i in range(10)
    ]
    rid, _ = api.full_run("agg.xlsx", xlsx_bytes(rows))
    r = api.post(f"/api/v1/reports/{rid}/exceptions/summary")
    assert r.status_code in (200, 201, 202), r.text
    agg = api.get(f"/api/v1/reports/{rid}/exceptions/summary").json()["aggregate"]
    eur = next(m for m in agg["total_value_at_stake"] if m["currency"] == "EUR")
    assert Decimal(str(eur["amount"])) == Decimal("1.00"), eur


@pytest.mark.skipif(not IS_PG, reason="column types are exact NUMERIC on PostgreSQL")
def test_postgres_columns_are_numeric_18_2(db: Session) -> None:
    rows = db.execute(
        text(
            "SELECT table_name, column_name, data_type, numeric_precision, numeric_scale "
            "FROM information_schema.columns WHERE table_schema = 'public' "
            "AND table_name IN ('claim_rows', 'validation_results', 'leakage_flags')"
        )
    ).all()
    types = {(t, c): (d, p, s) for t, c, d, p, s in rows}
    for model, names in MONEY_COLUMNS.items():
        for name in names:
            assert types[(model.__tablename__, name)] == ("numeric", 18, 2), (model.__tablename__, name)
