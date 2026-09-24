"""Section 8 validation rules against the canonical DataFrame (fix spec
3.6/3.7: field-requiredness now lives entirely in schema.py's per-field
`requirement` tag, and arithmetic reconciliation has three outcomes, not
two)."""

from __future__ import annotations

import dataclasses

import datetime as dt
from dataclasses import dataclass

import pandas as pd

from . import ingest, schema
from .iso4217 import VALID_CURRENCY_CODES

EXCEPTION_COLUMNS = ["row_index", "claim_ref", "rule", "detail"]

# sheet_field_state: {sheet_name: {field_code: "alias" | "ai" | "unmapped"}}.
# A field UNMAPPED on a given sheet must never be treated as "present on
# that sheet's rows but blank" -- every check below excludes those rows
# from that field's denominator rather than counting them as failures.
SheetFieldState = dict[str, dict[str, str]]


NOT_EVALUABLE_DETAIL_COLUMNS = ["row_index", "claim_ref", "reason", "detail"]


@dataclass
class ValidationResult:
    exceptions: pd.DataFrame
    arithmetic_match_count: int
    arithmetic_mismatch_count: int
    arithmetic_not_evaluable_count: int
    # Kept separate from `exceptions` deliberately: a not-evaluable row is
    # not wrong data (it doesn't penalize the composite score the way an
    # exception does, see report.py), it's a row Truebind refuses to guess
    # about. This is the per-row "why" behind arithmetic_not_evaluable_count
    # -- without it, a user could see "Not evaluable: 10" with no way to
    # find which 10 rows or why, which is exactly the trust gap this exists
    # to close.
    not_evaluable_detail: pd.DataFrame


def add_row_findings(result: "ValidationResult", findings: list[tuple[int, str, str]]) -> "ValidationResult":
    """Append extra row-level findings (e.g. lazy schema failures) to a
    ValidationResult without touching its arithmetic counts."""
    if not findings:
        return result
    extra = pd.DataFrame([{"row_index": i, "claim_ref": None, "rule": r, "detail": d} for i, r, d in findings])
    exc = pd.concat([result.exceptions, extra], ignore_index=True) if not result.exceptions.empty else extra
    return dataclasses.replace(result, exceptions=exc)


def validate(df: pd.DataFrame, sheet_field_state: SheetFieldState | None = None) -> ValidationResult:
    """Returns one row per exception found in df (canonical DataFrame,
    columns = Section 3 field codes), plus the three-outcome arithmetic
    reconciliation counts (fix spec 3.7)."""
    sheet_field_state = sheet_field_state or {}
    exceptions: list[dict] = []

    def flag(idx, rule: str, detail: str) -> None:
        claim_ref = df.at[idx, schema.CLAIM_REF_CODE] if schema.CLAIM_REF_CODE in df.columns else None
        exceptions.append({
            "row_index": idx,
            "claim_ref": claim_ref if pd.notna(claim_ref) else None,
            "rule": rule,
            "detail": detail,
        })

    _check_mandatory_fields(df, flag, sheet_field_state)
    arith_counts = _check_arithmetic(df, flag, sheet_field_state)
    _check_dates(df, flag)
    _check_currency(df, flag)
    _check_status_enum(df, flag)

    return ValidationResult(
        exceptions=pd.DataFrame(exceptions, columns=EXCEPTION_COLUMNS),
        **arith_counts,
    )


def _field_unmapped_mask(df: pd.DataFrame, field_code: str, sheet_field_state: SheetFieldState) -> pd.Series:
    """True for rows whose source sheet never had a column mapped to
    field_code at all (as opposed to a column that mapped but is blank
    on that particular row)."""
    if not sheet_field_state or schema.SOURCE_SHEET_CODE not in df.columns:
        return pd.Series(False, index=df.index)

    def is_unmapped(sheet_name: object) -> bool:
        return sheet_field_state.get(sheet_name, {}).get(field_code) == "unmapped"

    return df[schema.SOURCE_SHEET_CODE].map(is_unmapped).fillna(False).astype(bool)


def _mapped_mask(df: pd.DataFrame, field_code: str, sheet_field_state: SheetFieldState) -> pd.Series:
    """True where this row's source sheet had a column bound to field_code.
    Without sheet_field_state (legacy single-DataFrame callers), a field
    counts as mapped only if its column carries at least one value or one
    unparseable cell -- an all-empty column is treated as unmapped, which is
    the conservative reading (it can only make a check NOT_EVALUABLE, never
    silently turn a missing component into zero)."""
    if sheet_field_state and schema.SOURCE_SHEET_CODE in df.columns:
        return ~_field_unmapped_mask(df, field_code, sheet_field_state)
    if field_code not in df.columns:
        return pd.Series(False, index=df.index)
    has_value = bool(df[field_code].notna().any())
    flag = ingest.unparseable_flag_column(field_code)
    has_unparseable = bool(df[flag].any()) if flag in df.columns else False
    return pd.Series(has_value or has_unparseable, index=df.index)


def _check_mandatory_fields(df: pd.DataFrame, flag, sheet_field_state: SheetFieldState) -> None:
    for code in schema.REQUIRED_CODES:
        spec = schema.FIELDS_BY_CODE[code]
        missing = df[code].isna() & ~_field_unmapped_mask(df, code, sheet_field_state)
        for idx in df.index[missing]:
            flag(idx, "missing_mandatory_field", f"{code} ({spec.name}) is missing")

    # Conditional pair: at least one paid component or the reserve must be present.
    pair_codes = (*schema.PAID_COMPONENT_CODES, schema.RESERVE_CODE)
    all_missing = pd.Series(True, index=df.index)
    all_unmapped = pd.Series(True, index=df.index)
    for code in pair_codes:
        all_missing &= df[code].isna()
        all_unmapped &= ~_mapped_mask(df, code, sheet_field_state)
    for idx in df.index[all_missing & ~all_unmapped]:
        flag(idx, "missing_mandatory_field",
             "no indemnity paid figure and no indemnity reserve present; at least one is required")


_SHORT = {
    schema.PAID_TD_CODE: "paid", schema.PAID_MONTH_CODE: "paid_this_month", schema.PREV_PAID_CODE: "previously_paid",
    schema.RESERVE_CODE: "reserve", schema.INCURRED_CODE: "incurred", schema.INCURRED_IND_CODE: "incurred_indemnity",
    schema.FEES_PAID_MONTH_CODE: "fees_paid_this_month", schema.FEES_PREV_PAID_CODE: "fees_previously_paid",
    schema.FEES_RESERVE_CODE: "fees_reserve", schema.FEES_PAID_TD_CODE: "fees_paid_to_date",
}


def _fmt(v) -> str:
    return "blank" if pd.isna(v) else f"{float(v):,.2f}"


def _check_arithmetic(df: pd.DataFrame, flag, sheet_field_state: SheetFieldState) -> dict:
    """Deterministic incurred reconciliation per Lloyd's CRS v5.2.

    paid_to_date (indemnity) := TB_PAID_TD if mapped,
                                else CR0126 (this month) + CR0128 (previously paid) if BOTH mapped,
                                else NOT_EVALUABLE (a this-month figure alone is never treated as
                                cumulative -- that would silently omit previously-paid amounts).
    indemnity incurred check  : CR0134 == paid_to_date + CR0130                     (if CR0134 mapped)
    total incurred check      : CR0155 == paid_to_date + CR0130 + fees              (if CR0155 mapped)
        fees := fees paid to date + CR0131 (fee reserve, nil if not reported), where
                fees paid to date := TB_FEES_PAID_TD if mapped, else CR0127 + CR0129 if both mapped;
                NOT_EVALUABLE if only one of CR0127/CR0129 is mapped (and no paid-to-date column);
                when no fee column exists the check runs indemnity-only and every result says so
                (v5.2 CR0155 includes fees; a file that reports none can only be checked as nil-fee).
    Within a row, a mapped-but-blank component counts as nil-reported (0), as before; an
    unparseable cell or a row mixing currencies across amount columns is NOT_EVALUABLE."""
    idx = df.index
    S = schema

    def mapped(code):
        return _mapped_mask(df, code, sheet_field_state)

    def unparseable(code):
        c = ingest.unparseable_flag_column(code)
        return df[c].astype(bool) if c in df.columns else pd.Series(False, index=idx)

    val = {c: df[c] for c in S.MONETARY_CODES}
    m = {c: mapped(c) for c in S.MONETARY_CODES}
    unp = {c: unparseable(c) for c in S.MONETARY_CODES}
    mixed_ccy = df["_mixed_currency"].astype(bool) if "_mixed_currency" in df.columns else pd.Series(False, index=idx)

    use_td = m[S.PAID_TD_CODE]
    use_components = ~use_td & m[S.PAID_MONTH_CODE] & m[S.PREV_PAID_CODE]
    paid_basis_missing = ~use_td & ~use_components & (m[S.PAID_MONTH_CODE] | m[S.PREV_PAID_CODE])
    paid_td = pd.Series(pd.NA, index=idx, dtype="Float64")
    paid_td = paid_td.mask(use_td, val[S.PAID_TD_CODE])
    comp_sum = val[S.PAID_MONTH_CODE].fillna(0) + val[S.PREV_PAID_CODE].fillna(0)
    comp_any = val[S.PAID_MONTH_CODE].notna() | val[S.PREV_PAID_CODE].notna()
    paid_td = paid_td.mask(use_components & comp_any, comp_sum)
    paid_mapped = use_td | use_components
    reserve = val[S.RESERVE_CODE]

    use_fee_td = m[S.FEES_PAID_TD_CODE]
    use_fee_comp = ~use_fee_td & m[S.FEES_PAID_MONTH_CODE] & m[S.FEES_PREV_PAID_CODE]
    fees_partial = ~use_fee_td & (m[S.FEES_PAID_MONTH_CODE] ^ m[S.FEES_PREV_PAID_CODE])
    fees_all = use_fee_td | use_fee_comp | m[S.FEES_RESERVE_CODE]  # some fee basis reported
    fee_paid = (val[S.FEES_PAID_TD_CODE].fillna(0).where(use_fee_td, 0)
                + (val[S.FEES_PAID_MONTH_CODE].fillna(0) + val[S.FEES_PREV_PAID_CODE].fillna(0)).where(use_fee_comp, 0))
    fee_sum = fee_paid + val[S.FEES_RESERVE_CODE].fillna(0).where(m[S.FEES_RESERVE_CODE], 0)

    paid_components_used = (*S.PAID_COMPONENT_CODES, S.RESERVE_CODE)
    any_unparseable = pd.Series(False, index=idx)
    for c in S.MONETARY_CODES:
        any_unparseable |= unp[c]

    targets = []  # (code, label, includes_fees)
    if bool(m[S.INCURRED_IND_CODE].any()):
        targets.append((S.INCURRED_IND_CODE, "total incurred (indemnity)", False))
    targets.append((S.INCURRED_CODE, "total incurred", True))

    status = pd.Series("", index=idx, dtype="object")  # "", MATCH, MISMATCH, NE
    reason = pd.Series("", index=idx, dtype="object")
    detail_ne = pd.Series("", index=idx, dtype="object")
    evaluated_any = pd.Series(False, index=idx)

    for code, label, includes_fees in targets:
        tgt = val[code]
        tgt_mapped = m[code]
        rows_for_target = tgt_mapped
        if not rows_for_target.any():
            continue
        exp = paid_td.fillna(0) + reserve.fillna(0)
        if includes_fees:
            exp = exp + fee_sum.where(fees_all, 0)
        has_inputs = tgt.notna() & (paid_td.notna() | reserve.notna())
        ne = pd.Series(False, index=idx)
        r = pd.Series("", index=idx, dtype="object")
        d = pd.Series("", index=idx, dtype="object")

        def mark(mask, rsn, text):
            new = mask & ~ne
            r.loc[new] = rsn
            d.loc[new] = text
            return ne | mask

        for uc in (code, *S.PAID_COMPONENT_CODES, S.RESERVE_CODE, *(S.ALL_FEE_CODES if includes_fees else ())):
            ne = mark(unp[uc], f"{_SHORT[uc]}_unparseable",
                      f"{S.FIELDS_BY_CODE[uc].name} contains a value that could not be parsed as a number")
        ne = mark(any_unparseable, "amount_unparseable", "An amount cell could not be parsed as a number")
        ne = mark(mixed_ccy, "mixed_currency_columns",
                  "Amount columns on this sheet declare different currencies; they cannot be added")
        ne = mark(paid_basis_missing, "previously_paid_unmapped",
                  "Only one of paid-this-month (CR0126) / previously-paid (CR0128) is mapped; "
                  "paid to date cannot be established without both (or a paid-to-date column)")
        ne = mark(~paid_mapped & ~m[S.RESERVE_CODE], "paid_and_reserve_unmapped",
                  "Neither a paid figure nor the indemnity reserve was mapped on this sheet")
        if includes_fees:
            ne = mark(fees_partial, "fees_partially_mapped",
                      "Only one of fees paid this month (CR0127) / previously paid (CR0129) is mapped and "
                      "there is no fees-paid-to-date column; total incurred includes fees, so it cannot "
                      "be reconciled")
        ne = mark(tgt.isna(), f"{_SHORT[code]}_blank", f"{label} is blank on this row")
        ne = mark(~has_inputs, "paid_and_reserve_blank", "Paid and reserve are both blank on this row")
        ne = ne & rows_for_target
        computable = rows_for_target & ~ne
        diff = (tgt - exp).abs()
        mism = computable & (diff > S.ARITHMETIC_TOLERANCE)
        for i in idx[mism]:
            parts = []
            if use_td.at[i]:
                parts.append(f"paid to date {_fmt(val[S.PAID_TD_CODE].at[i])}")
            else:
                parts.append(f"paid this month {_fmt(val[S.PAID_MONTH_CODE].at[i])} + previously paid "
                             f"{_fmt(val[S.PREV_PAID_CODE].at[i])}")
            parts.append(f"reserve {_fmt(reserve.at[i])}")
            fee_note = ""
            if includes_fees:
                if fees_all.at[i]:
                    parts.append(f"fees {_fmt(fee_sum.at[i])}")
                else:
                    fee_note = " (no fee columns in this file: checked as nil fees; if the total includes fees the difference may be fees)"
            flag(i, "arithmetic_mismatch",
                 f"{label}={_fmt(tgt.at[i])} but " + " + ".join(parts) + f" = {_fmt(exp.at[i])}{fee_note}")
        # Combine per row: any mismatch wins; else match if evaluated; else keep first NE reason.
        status = status.mask(mism, "MISMATCH")
        status = status.mask(computable & ~mism & (status == ""), "MATCH")
        first_ne = ne & (reason == "")
        reason = reason.mask(first_ne, r)
        detail_ne = detail_ne.mask(first_ne, d)
        evaluated_any |= rows_for_target

    # Rows where no incurred column exists at all.
    no_target = ~evaluated_any
    reason = reason.mask(no_target & (reason == ""), "incurred_unmapped")
    detail_ne = detail_ne.mask(no_target & (detail_ne == ""), "No total incurred column was mapped on this sheet")
    # A row that matched one target but was not evaluable for another is still a match.
    final_ne = (status == "")
    match = status == "MATCH"
    mismatch = status == "MISMATCH"

    # Consistency: paid-to-date vs its components, when all three are mapped.
    both = use_td & m[S.PAID_MONTH_CODE] & m[S.PREV_PAID_CODE] & val[S.PAID_TD_CODE].notna() & comp_any & ~any_unparseable
    bad = both & ((val[S.PAID_TD_CODE] - comp_sum).abs() > S.ARITHMETIC_TOLERANCE)
    for i in idx[bad]:
        flag(i, "arithmetic_mismatch",
             f"paid to date={_fmt(val[S.PAID_TD_CODE].at[i])} but paid this month "
             f"{_fmt(val[S.PAID_MONTH_CODE].at[i])} + previously paid {_fmt(val[S.PREV_PAID_CODE].at[i])} "
             f"= {_fmt(comp_sum.at[i])}")

    claim_ref_col = schema.CLAIM_REF_CODE
    rows = []
    for i in idx[final_ne & ~bad]:
        cr = df.at[i, claim_ref_col] if claim_ref_col in df.columns else None
        rows.append({"row_index": i, "claim_ref": cr if pd.notna(cr) else None,
                     "reason": reason.at[i] or "not_evaluable", "detail": detail_ne.at[i] or "Not evaluable"})
    # Every row lands in exactly one outcome.
    mismatch_rows = mismatch | bad
    match_rows = match & ~bad
    ne_rows = final_ne & ~bad
    return {
        "arithmetic_match_count": int(match_rows.sum()),
        "arithmetic_mismatch_count": int(mismatch_rows.sum()),
        "arithmetic_not_evaluable_count": int(ne_rows.sum()),
        "not_evaluable_detail": pd.DataFrame(rows, columns=NOT_EVALUABLE_DETAIL_COLUMNS),
    }


def _check_dates(df: pd.DataFrame, flag) -> None:
    today = pd.Timestamp(dt.date.today())
    loss = df[schema.LOSS_DATE_CODE]
    notified = df[schema.NOTIFIED_DATE_CODE]

    both_present = loss.notna() & notified.notna()
    order_bad = both_present & (loss > notified)
    for idx in df.index[order_bad]:
        flag(idx, "date_order",
             f"date of loss {loss.at[idx].date()} is after date first notified {notified.at[idx].date()}")

    for idx in df.index[loss.notna() & (loss > today)]:
        flag(idx, "date_in_future", f"date of loss {loss.at[idx].date()} is in the future")

    for idx in df.index[notified.notna() & (notified > today)]:
        flag(idx, "date_in_future", f"date first notified {notified.at[idx].date()} is in the future")


def _check_currency(df: pd.DataFrame, flag) -> None:
    currency = df[schema.CURRENCY_CODE]

    invalid = currency.notna() & ~currency.isin(VALID_CURRENCY_CODES)
    for idx in df.index[invalid]:
        flag(idx, "invalid_currency", f"{currency.at[idx]!r} is not a valid ISO 4217 code")

    ref = df[schema.CLAIM_REF_CODE]
    has_ref = ref.notna()
    if has_ref.any():
        nunique = df[has_ref].groupby(ref[has_ref])[schema.CURRENCY_CODE].nunique(dropna=True)
        inconsistent_refs = set(nunique[nunique > 1].index)
        if inconsistent_refs:
            for idx in df.index[has_ref & ref.isin(inconsistent_refs)]:
                flag(idx, "currency_inconsistency",
                     f"claim {ref.at[idx]} reported with more than one settlement currency")


def _check_status_enum(df: pd.DataFrame, flag) -> None:
    status = df[schema.STATUS_CODE]
    valid = set(schema.FIELDS_BY_CODE[schema.STATUS_CODE].enum_values)
    bad = status.notna() & ~status.isin(valid)
    for idx in df.index[bad]:
        flag(idx, "invalid_status", f"{status.at[idx]!r} is not one of {sorted(valid)}")
