"""P3 Binder compliance: does the bordereau stay inside the binding authority?

Configuration: the Binder assigned to the report (period, permitted
currencies, per-claim settlement authority and aggregate limit, both in the
binder's limit currency). Rules:

- BND_LOSS_OUTSIDE_PERIOD  loss date before inception or after expiry
  (inclusive period). When the date column is ambiguous between day/month and
  month/day and only one reading is inside the period: REVIEW, never a guess.
- BND_CURRENCY_NOT_PERMITTED  settlement currency not on the binder.
- BND_OVER_AUTHORITY  total incurred above the claims settlement authority,
  converted at the ECB rate on the loss date when currencies differ.
- BND_AGGREGATE_EXCEEDED  indemnity paid to date across the report (latest
  cumulative figure per claim) above the aggregate limit.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Any

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
    not_assessed,
)

LOSS, CCY, INCURRED, PAID = "CR0119CM", "CR0110CM", "CR0155CM", "TB_PAID_TD"

# convert(amount, from_ccy, to_ccy, on) -> (converted | None, reason | None)
Converter = Callable[[Decimal, str, str, date], tuple[Decimal | None, str | None]]


def _swap(d: date) -> date | None:
    if d.day > 12 or d.day == d.month:
        return None
    try:
        return date(d.year, d.day, d.month)
    except ValueError:
        return None


def _rules() -> list[RuleCoverage]:
    return [
        RuleCoverage("BND_LOSS_OUTSIDE_PERIOD", "Loss date inside the binder period"),
        RuleCoverage("BND_CURRENCY_NOT_PERMITTED", "Settlement currency permitted by the binder"),
        RuleCoverage("BND_OVER_AUTHORITY", "Claim within the settlement authority"),
        RuleCoverage("BND_AGGREGATE_EXCEEDED", "Paid claims within the aggregate limit"),
    ]


def _convert(ctx: dict[str, Any], amount: Decimal, src: str, dst: str, on: date | None) -> tuple[Decimal | None, str]:
    if src == dst:
        return amount, ""
    fx: Converter | None = ctx.get("convert")
    if fx is None or on is None:
        return None, f"no exchange rate available to convert {src} to {dst}"
    value, reason = fx(amount, src, dst, on)
    return value, reason or ""


def run(inp: CheckInput) -> ModuleResult:
    rules = _rules()
    b = inp.config.get("binder")
    if not b:
        return not_assessed("No binder is assigned to this report, so binder compliance was not assessed.", rules)
    start, end = date.fromisoformat(b["inception_date"]), date.fromisoformat(b["expiry_date"])
    permitted = {c.upper() for c in b.get("currencies") or []}
    limit_ccy = b["limit_currency"]
    authority = Decimal(b["claims_authority"]) if b.get("claims_authority") is not None else None
    aggregate = Decimal(b["aggregate_limit"]) if b.get("aggregate_limit") is not None else None
    period_r, ccy_r, auth_r, agg_r = rules
    findings: list[FindingDraft] = []
    name = b["name"]

    def fd(row: RowView, rule: str, status: str, severity: str, title: str, text: str, code: str, **kw: Any) -> None:
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
                **kw,
            )
        )

    latest_paid: dict[str, tuple[RowView, Decimal, str]] = {}
    for row in inp.rows:
        sheet = inp.sheets[row.sheet_name]
        ccy = iso_currency(row.currency)

        # -- period
        if LOSS not in sheet.mapped:
            period_r.skip(1, f"{field_label(LOSS)} is not mapped on sheet '{sheet.name}'")
        elif row.date_of_loss is None:
            period_r.skip(1, "date of loss is blank or unreadable")
        else:
            period_r.assessed += 1
            d = row.date_of_loss
            inside = start <= d <= end
            alt = _swap(d) if sheet.mapped[LOSS] in sheet.ambiguous_date_columns else None
            if alt is not None and (start <= alt <= end) != inside:
                fd(
                    row,
                    "BND_LOSS_OUTSIDE_PERIOD",
                    "REVIEW",
                    "MEDIUM",
                    "Loss date is ambiguous",
                    f"The loss date could be {d:%d %B %Y} or {alt:%d %B %Y}: every date in this column reads both "
                    f"ways. One reading is inside the binder period ({start:%d %b %Y} to {end:%d %b %Y}) and one "
                    f"is not. Confirm the date order with the sender.",
                    LOSS,
                    evidence={"read_as": d.isoformat(), "alternative": alt.isoformat()},
                )
            elif not inside:
                side = (
                    f"before the binder incepted on {start:%d %B %Y}"
                    if d < start
                    else f"after the binder expired on {end:%d %B %Y}"
                )
                fd(
                    row,
                    "BND_LOSS_OUTSIDE_PERIOD",
                    "FAIL",
                    "HIGH",
                    "Loss date outside the binder period",
                    f"The loss date {d:%d %B %Y} is {side}, so this claim is not covered by binder '{name}'.",
                    LOSS,
                    evidence={"date_of_loss": d.isoformat(), "inception": start.isoformat(), "expiry": end.isoformat()},
                )

        # -- currency
        if not permitted:
            ccy_r.skip(1, "the binder lists no permitted currencies")
        elif CCY not in sheet.mapped:
            ccy_r.skip(1, f"{field_label(CCY)} is not mapped on sheet '{sheet.name}'")
        elif ccy is None:
            ccy_r.skip(1, "settlement currency is blank or not an ISO 4217 code")
        else:
            ccy_r.assessed += 1
            if ccy not in permitted:
                fd(
                    row,
                    "BND_CURRENCY_NOT_PERMITTED",
                    "FAIL",
                    "MEDIUM",
                    "Currency not permitted by the binder",
                    f"The claim is settled in {ccy}, but binder '{name}' permits only {', '.join(sorted(permitted))}.",
                    CCY,
                    evidence={"currency": ccy, "permitted": sorted(permitted)},
                )

        # -- settlement authority
        if authority is None:
            auth_r.skip(1, "the binder sets no claims settlement authority")
        elif sheet.missing((INCURRED, CCY)):
            missing = ", ".join(field_label(c) for c in sheet.missing((INCURRED, CCY)))
            auth_r.skip(1, f"{missing} not mapped on sheet '{sheet.name}'")
        elif row.incurred_amount is None or ccy is None:
            auth_r.skip(1, "total incurred or currency is blank")
        else:
            value, why = _convert(inp.context, row.incurred_amount, ccy, limit_ccy, row.date_of_loss)
            if value is None:
                auth_r.skip(1, why)
            else:
                auth_r.assessed += 1
                if value > authority:
                    conv = "" if ccy == limit_ccy else f" ({money(value, limit_ccy)} at the ECB rate)"
                    fd(
                        row,
                        "BND_OVER_AUTHORITY",
                        "FAIL",
                        "HIGH",
                        "Claim above the settlement authority",
                        f"Total incurred of {money(row.incurred_amount, ccy)}{conv} exceeds the claims settlement "
                        f"authority of {money(authority, limit_ccy)} under binder '{name}' by "
                        f"{money(value - authority, limit_ccy)}. The coverholder needed the insurer's agreement.",
                        INCURRED,
                        amount=value - authority,
                        currency=limit_ccy,
                        evidence={
                            "incurred": str(row.incurred_amount),
                            "incurred_currency": ccy,
                            "incurred_in_limit_currency": str(value),
                            "authority": str(authority),
                        },
                    )

        # -- aggregate (collect the latest cumulative paid per claim)
        if row.paid_amount is not None and ccy is not None and PAID in sheet.mapped:
            key = norm_ref(row.claim_reference) or f"row:{row.claim_row_id}"
            prev = latest_paid.get(key)
            if prev is None or row.paid_amount >= prev[1]:
                latest_paid[key] = (row, row.paid_amount, ccy)

    if aggregate is None:
        agg_r.skip(len(inp.rows), "the binder sets no aggregate limit")
    elif not latest_paid:
        agg_r.skip(len(inp.rows), f"{field_label(PAID)} or currency is not available")
    else:
        total, unconverted = Decimal(0), []
        for row, paid, ccy in latest_paid.values():
            value, why = _convert(inp.context, paid, ccy, limit_ccy, row.date_of_loss)
            if value is None:
                unconverted.append(why)
            else:
                total += value
                agg_r.assessed += 1
        if unconverted:
            agg_r.skip(len(unconverted), unconverted[0])
        if total > aggregate:
            lower = " at least" if unconverted else ""
            findings.append(
                FindingDraft(
                    "BND_AGGREGATE_EXCEEDED",
                    "FAIL",
                    "CRITICAL",
                    "Aggregate limit exceeded",
                    f"Indemnity paid to date across {len(latest_paid)} claims totals{lower} {money(total, limit_ccy)}, "
                    f"above the aggregate limit of {money(aggregate, limit_ccy)} under binder '{name}' by "
                    f"{money(total - aggregate, limit_ccy)}.",
                    field_code=PAID,
                    amount=total - aggregate,
                    currency=limit_ccy,
                    evidence={"paid_total": str(total), "aggregate_limit": str(aggregate), "claims": len(latest_paid)},
                )
            )
        elif unconverted:  # an incomplete total under the limit proves nothing
            agg_r.skip(agg_r.assessed, "the paid total is incomplete, so the aggregate limit could not be assessed")
            agg_r.assessed = 0
    return finish(rules, findings, {"binder": b})
