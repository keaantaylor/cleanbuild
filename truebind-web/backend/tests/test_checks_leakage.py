"""P4 -- leakage & overpayment rules at their edges.

(The precision/recall proof on a planted file is fixtures/golden/leakage.)

Acceptance:
- reporting periods are read in the usual forms (2024-01, Jan 2024, Q1 2024,
  202401, 31/01/2024); anything else is NOT_ASSESSED, never guessed;
- "closed" is read from the usual status words only;
- a payment after closure is REVIEW with the extra paid as the amount; the
  same period twice is not compared; a decrease is REVIEW with the drop;
- blank inputs are counted as not assessed; exposure is per currency and
  dismissed findings leave it.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from app.checks import leakage
from app.checks.base import CheckInput, RowView, SheetView
from conftest import Api, xlsx_bytes

ALL = {c: c for c in ("CR0104M", "CR0105CM", "TB_PAID_TD", "CR0126CM", "CR0130CM", "TB_PERIOD")}


@pytest.mark.parametrize(
    ("text", "key"),
    [("2024-01", (2024, 1)), ("Jan 2024", (2024, 1)), ("January 2024", (2024, 1)), ("Q1 2024", (2024, 3)),
     ("2024 Q4", (2024, 12)), ("202402", (2024, 2)), ("31/01/2024", (2024, 1)), ("2024-03-31", (2024, 3)),
     ("sometime", None), ("", None), (None, None)],
)  # fmt: skip
def test_periods_are_read_or_refused(text: str | None, key: tuple[int, int] | None) -> None:
    assert leakage.period_key(text) == key


def test_closed_words() -> None:
    assert leakage.is_closed(" Closed ") and leakage.is_closed("settled") and leakage.is_closed("Finalised")
    assert not leakage.is_closed("Re-opened") and not leakage.is_closed("Open") and not leakage.is_closed(None)


def _row(n: int, **kw: Any) -> RowView:
    base: dict[str, Any] = {"claim_reference": "C-1", "currency": "GBP"}
    return RowView(str(n), "S", n, **{**base, **kw})


def _run(rows: list[RowView], mapped: dict[str, str] | None = None) -> Any:
    return leakage.run(CheckInput("r", {"S": SheetView("S", mapped if mapped is not None else ALL)}, rows))


def test_history_rules() -> None:
    rows = [
        _row(2, reporting_period="2024-01", paid_amount=Decimal(100), claim_status="Closed"),
        _row(3, reporting_period="2024-01", paid_amount=Decimal(100), claim_status="Closed"),  # same period
        _row(4, reporting_period="Feb 2024", paid_amount=Decimal(130), claim_status="Reopened"),
        _row(5, reporting_period="2024-03", paid_amount=Decimal(90), claim_status="Open"),
    ]
    result = _run(rows)
    got = [(f.rule_code, f.row_number, f.status, f.amount) for f in result.findings]
    assert got == [
        ("LKG_PAID_AFTER_CLOSURE", 4, "REVIEW", Decimal(30)),
        ("LKG_PAID_DECREASED", 5, "REVIEW", Decimal(40)),
    ]
    assert "was reported 'Closed' in period 2024-01" in result.findings[0].explanation


def test_blank_and_unmapped_inputs_are_not_assessed() -> None:
    result = _run([_row(2, reporting_period="whenever", paid_amount=Decimal(1), reserve_amount=None)])
    reasons = {r.code: (r.assessed, r.not_assessed, r.reasons) for r in result.rules}
    assert reasons["LKG_NEGATIVE_RESERVE"] == (0, 1, ["reserve is blank"])
    assert reasons["LKG_PAID_DECREASED"][:2] == (0, 1) and "cannot be read" in reasons["LKG_PAID_DECREASED"][2][0]
    assert result.state == "NOT_ASSESSED"
    none = _run([_row(2)], mapped={})
    assert none.state == "NOT_ASSESSED" and "Claim reference" in (none.reason or "")


def test_exposure_is_per_currency_and_dismissals_leave_it(api: Api) -> None:
    header = ["Claim Reference", "Insured Name", "Claim Status", "Currency", "Outstanding Reserve"]
    rows: list[list[Any]] = [header, ["A-1", "X", "Closed", "GBP", 100], ["A-2", "Y", "Closed", "EUR", 50],
            ["A-3", "Z", "Closed", "GBP", 25]]  # fmt: skip
    rid, _ = api.full_run("l.xlsx", xlsx_bytes(rows))
    run = next(r for r in api.get(f"/api/v1/reports/{rid}/checks").json() if r["module"] == "leakage")
    assert run["exposure"] == {"EUR": "50.00", "GBP": "125.00"} and run["state"] == "PARTIAL"
    f = next(x for x in api.get(f"/api/v1/reports/{rid}/checks/findings").json()["items"] if x["amount"] == "25.00")
    api.patch(f"/api/v1/reports/{rid}/checks/findings/{f['id']}", json={"disposition": "DISMISSED", "note": "released"})
    run = next(r for r in api.get(f"/api/v1/reports/{rid}/checks").json() if r["module"] == "leakage")
    assert run["exposure"] == {"EUR": "50.00", "GBP": "100.00"}
