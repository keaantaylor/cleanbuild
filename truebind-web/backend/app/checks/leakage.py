"""P4 Leakage & overpayment: money that should not have left, or should not be held.

Rules (each needs its fields mapped on the sheet, else NOT_ASSESSED):
- LKG_DUPLICATE_PAYMENT     the same payment (claim, reporting period and
  amount paid this month) appears on two rows: the second is paid twice.
- LKG_NEGATIVE_RESERVE      an outstanding indemnity reserve below zero.
- LKG_CLOSED_WITH_RESERVE   a closed claim still holding a reserve.
- LKG_PAID_AFTER_CLOSURE    a claim reported closed in one period shows more
  paid to date in a later period (REVIEW: reopened, or paid after closure).
- LKG_PAID_DECREASED        cumulative paid to date went down between periods
  (REVIEW: a recovery or refund should be reported, not netted silently).
Periods are compared only when they can be read (YYYY-MM, Mon YYYY, Q1 2024,
...); an unreadable period is NOT_ASSESSED, never guessed.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from itertools import pairwise

from .base import (
    CheckInput,
    FindingDraft,
    ModuleResult,
    RowView,
    RuleCoverage,
    field_label,
    finish,
    iso_currency,
    money,
    norm_ref,
)

REF, STATUS, PAID_TD, PAID_M, RESERVE, PERIOD = "CR0104M", "CR0105CM", "TB_PAID_TD", "CR0126CM", "CR0130CM", "TB_PERIOD"
_CLOSED = {"closed", "close", "settled", "finalised", "finalized", "closed - paid", "closed-paid", "cl"}
_QUARTER = re.compile(r"^(?:q([1-4])[\s/-]*(\d{4})|(\d{4})[\s/-]*q([1-4]))$", re.IGNORECASE)
_FORMATS = ("%Y-%m", "%Y/%m", "%m/%Y", "%m-%Y", "%b %Y", "%B %Y", "%b-%Y", "%b-%y", "%Y%m", "%Y-%m-%d", "%d/%m/%Y")


def is_closed(status: str | None) -> bool:
    return (status or "").strip().lower() in _CLOSED


def period_key(value: str | None) -> tuple[int, int] | None:
    """(year, month) of a reporting period, or None when it cannot be read.
    A quarter sorts by its last month."""
    text = (value or "").strip()
    if not text:
        return None
    q = _QUARTER.match(text)
    if q:
        quarter, year = (q.group(1), q.group(2)) if q.group(1) else (q.group(4), q.group(3))
        return int(year), int(quarter) * 3
    for fmt in _FORMATS:
        try:
            d = datetime.strptime(text, fmt)  # noqa: DTZ007 -- a period label, not an instant
        except ValueError:
            continue
        return d.year, d.month
    return None


def _rules() -> list[RuleCoverage]:
    return [
        RuleCoverage("LKG_DUPLICATE_PAYMENT", "Each payment reported once"),
        RuleCoverage("LKG_NEGATIVE_RESERVE", "Reserves not negative"),
        RuleCoverage("LKG_CLOSED_WITH_RESERVE", "Closed claims hold no reserve"),
        RuleCoverage("LKG_PAID_AFTER_CLOSURE", "No payments after closure"),
        RuleCoverage("LKG_PAID_DECREASED", "Paid to date never goes down"),
    ]


def run(inp: CheckInput) -> ModuleResult:
    rules = _rules()
    dup_r, neg_r, closed_r, after_r, dec_r = rules
    findings: list[FindingDraft] = []

    def fd(
        row: RowView,
        rule: str,
        status: str,
        severity: str,
        title: str,
        text: str,
        code: str,
        amount: Decimal | None = None,
        **evidence: object,
    ) -> None:
        sheet = inp.sheets[row.sheet_name]
        findings.append(
            FindingDraft(
                rule,
                status,
                severity,
                title,
                text,
                row.sheet_name,
                row.row_number,
                code,
                sheet.mapped.get(code),
                row.claim_row_id,
                row.claim_reference,
                amount,
                iso_currency(row.currency) if amount is not None else None,
                {k: str(v) for k, v in evidence.items()},
            )
        )

    seen_payment: dict[tuple[str, str, Decimal], RowView] = {}
    history: dict[str, list[tuple[tuple[int, int], RowView]]] = defaultdict(list)
    for row in inp.rows:
        sheet = inp.sheets[row.sheet_name]
        ccy = iso_currency(row.currency)
        ref = norm_ref(row.claim_reference)

        # -- duplicate payment
        missing = sheet.missing((REF, PERIOD, PAID_M))
        if missing:
            dup_r.skip(1, f"{', '.join(field_label(c) for c in missing)} not mapped on sheet '{sheet.name}'")
        elif not ref or not (row.reporting_period or "").strip() or row.paid_this_month is None:
            dup_r.skip(1, "claim reference, reporting period or paid this month is blank")
        else:
            dup_r.assessed += 1
            if row.paid_this_month > 0:
                key = (ref, row.reporting_period.strip().upper(), row.paid_this_month)  # type: ignore[union-attr]
                first = seen_payment.get(key)
                if first is None:
                    seen_payment[key] = row
                else:
                    where = f"sheet '{first.sheet_name}' row {first.row_number}"
                    fd(
                        row,
                        "LKG_DUPLICATE_PAYMENT",
                        "FAIL",
                        "HIGH",
                        "Payment reported twice",
                        f"The payment of {money(row.paid_this_month, ccy)} on claim {row.claim_reference} for period "
                        f"{row.reporting_period} is already reported on {where}. Counted twice, it overstates paid "
                        f"claims by this amount.",
                        PAID_M,
                        row.paid_this_month,
                        first_sheet=first.sheet_name,
                        first_row=first.row_number,
                    )

        # -- negative reserve
        if RESERVE not in sheet.mapped:
            neg_r.skip(1, f"{field_label(RESERVE)} not mapped on sheet '{sheet.name}'")
        elif row.reserve_amount is None:
            neg_r.skip(1, "reserve is blank")
        else:
            neg_r.assessed += 1
            if row.reserve_amount < 0:
                fd(
                    row,
                    "LKG_NEGATIVE_RESERVE",
                    "FAIL",
                    "HIGH",
                    "Negative reserve",
                    f"The outstanding reserve is {money(row.reserve_amount, ccy)}. A reserve cannot be negative: "
                    f"it usually hides an overpayment or a recovery netted off the reserve.",
                    RESERVE,
                    -row.reserve_amount,
                    reserve=row.reserve_amount,
                )

        # -- closed with reserve
        missing = sheet.missing((STATUS, RESERVE))
        if missing:
            closed_r.skip(1, f"{', '.join(field_label(c) for c in missing)} not mapped on sheet '{sheet.name}'")
        elif not (row.claim_status or "").strip() or row.reserve_amount is None:
            closed_r.skip(1, "claim status or reserve is blank")
        else:
            closed_r.assessed += 1
            if is_closed(row.claim_status) and row.reserve_amount > 0:
                fd(
                    row,
                    "LKG_CLOSED_WITH_RESERVE",
                    "FAIL",
                    "MEDIUM",
                    "Closed claim still holds a reserve",
                    f"The claim is '{row.claim_status}' but still holds a reserve of "
                    f"{money(row.reserve_amount, ccy)}, which overstates incurred and ties up capacity.",
                    RESERVE,
                    row.reserve_amount,
                    claim_status=row.claim_status,
                )

        # -- collect history for the period rules
        missing = sheet.missing((REF, PERIOD, PAID_TD))
        pk = period_key(row.reporting_period)
        if missing:
            reason = f"{', '.join(field_label(c) for c in missing)} not mapped on sheet '{sheet.name}'"
            after_r.skip(1, reason)
            dec_r.skip(1, reason)
        elif not ref or row.paid_amount is None or pk is None:
            reason = "claim reference or paid to date is blank, or the reporting period cannot be read"
            after_r.skip(1, reason)
            dec_r.skip(1, reason)
        else:
            history[ref].append((pk, row))

    for rows in history.values():
        rows.sort(key=lambda x: (x[0], x[1].row_number or 0))
        after_r.assessed += len(rows)
        dec_r.assessed += len(rows)
        closed_at: RowView | None = None
        for (pk, prev), (nk, cur) in pairwise(rows):
            if pk == nk:
                continue
            ccy = iso_currency(cur.currency)
            assert prev.paid_amount is not None and cur.paid_amount is not None  # noqa: S101 -- filtered above
            if is_closed(prev.claim_status):
                closed_at = prev
            if closed_at is not None and cur.paid_amount > (closed_at.paid_amount or Decimal(0)):
                extra = cur.paid_amount - (closed_at.paid_amount or Decimal(0))
                fd(
                    cur,
                    "LKG_PAID_AFTER_CLOSURE",
                    "REVIEW",
                    "MEDIUM",
                    "Paid after the claim was closed",
                    f"Claim {cur.claim_reference} was reported '{closed_at.claim_status}' in period "
                    f"{closed_at.reporting_period}, yet paid to date rose by {money(extra, ccy)} by period "
                    f"{cur.reporting_period}. Check it was properly reopened.",
                    PAID_TD,
                    extra,
                    closed_period=closed_at.reporting_period,
                    closed_paid=closed_at.paid_amount,
                    later_paid=cur.paid_amount,
                )
            if cur.paid_amount < prev.paid_amount:
                drop = prev.paid_amount - cur.paid_amount
                fd(
                    cur,
                    "LKG_PAID_DECREASED",
                    "REVIEW",
                    "MEDIUM",
                    "Paid to date went down",
                    f"Paid to date on claim {cur.claim_reference} fell from {money(prev.paid_amount, ccy)} in period "
                    f"{prev.reporting_period} to {money(cur.paid_amount, ccy)} in {cur.reporting_period}. A recovery "
                    f"or refund should be reported as such.",
                    PAID_TD,
                    drop,
                    previous_period=prev.reporting_period,
                    previous_paid=prev.paid_amount,
                )
    return finish(rules, findings, None)
