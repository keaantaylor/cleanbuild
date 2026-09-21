"""Section 8 validation rules against the canonical DataFrame (fix spec
3.6/3.7: field-requiredness now lives entirely in schema.py's per-field
`requirement` tag, and arithmetic reconciliation has three outcomes, not
two)."""

from __future__ import annotations

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


def _check_mandatory_fields(df: pd.DataFrame, flag, sheet_field_state: SheetFieldState) -> None:
    for code in schema.REQUIRED_CODES:
        spec = schema.FIELDS_BY_CODE[code]
        missing = df[code].isna() & ~_field_unmapped_mask(df, code, sheet_field_state)
        for idx in df.index[missing]:
            flag(idx, "missing_mandatory_field", f"{code} ({spec.name}) is missing")

    if len(schema.CONDITIONAL_PAIR_CODES) == 2:
        code_a, code_b = schema.CONDITIONAL_PAIR_CODES
        both_missing = df[code_a].isna() & df[code_b].isna()
        both_unmapped = (
            _field_unmapped_mask(df, code_a, sheet_field_state)
            & _field_unmapped_mask(df, code_b, sheet_field_state)
        )
        for idx in df.index[both_missing & ~both_unmapped]:
            flag(idx, "missing_mandatory_field",
                 "both indemnity paid and indemnity reserve are missing; at least one is required")


def _check_arithmetic(df: pd.DataFrame, flag, sheet_field_state: SheetFieldState) -> dict:
    paid = df[schema.PAID_CODE]
    reserve = df[schema.RESERVE_CODE]
    incurred = df[schema.INCURRED_CODE]

    # A cell that HAD text but couldn't be parsed as a number (a stray
    # symbol, an inconsistent format even after currency/thousands-
    # separator normalization) is never treated the same as a cell that
    # was simply empty: an unparseable value must never be silently
    # coerced to zero in a financial reconciliation. ingest.apply_mapping
    # tracks this per decimal field; a sheet whose mapping never ran this
    # column through that path (e.g. a legacy caller) has no tracking
    # column, so default to "nothing was unparseable" rather than raising.
    paid_unparseable = df.get(ingest.unparseable_flag_column(schema.PAID_CODE), pd.Series(False, index=df.index))
    reserve_unparseable = df.get(ingest.unparseable_flag_column(schema.RESERVE_CODE), pd.Series(False, index=df.index))
    incurred_unparseable = df.get(ingest.unparseable_flag_column(schema.INCURRED_CODE), pd.Series(False, index=df.index))
    any_unparseable = paid_unparseable | reserve_unparseable | incurred_unparseable

    incurred_unmapped = _field_unmapped_mask(df, schema.INCURRED_CODE, sheet_field_state)
    paid_unmapped = _field_unmapped_mask(df, schema.PAID_CODE, sheet_field_state)
    reserve_unmapped = _field_unmapped_mask(df, schema.RESERVE_CODE, sheet_field_state)
    paid_and_reserve_unmapped = paid_unmapped & reserve_unmapped

    unmapped = incurred_unmapped | paid_and_reserve_unmapped
    has_inputs = incurred.notna() & (paid.notna() | reserve.notna())
    computable = has_inputs & ~unmapped & ~any_unparseable
    not_evaluable = ~computable

    expected = paid.fillna(0) + reserve.fillna(0)
    diff = (incurred - expected).abs()
    mismatch = computable & (diff > schema.ARITHMETIC_TOLERANCE)
    match = computable & ~mismatch

    for idx in df.index[mismatch]:
        flag(idx, "arithmetic_mismatch",
             f"incurred={incurred.at[idx]} but paid+reserve={expected.at[idx]}")

    not_evaluable_rows: list[dict] = []
    claim_ref_col = schema.CLAIM_REF_CODE
    for idx in df.index[not_evaluable]:
        claim_ref = df.at[idx, claim_ref_col] if claim_ref_col in df.columns else None
        claim_ref = claim_ref if pd.notna(claim_ref) else None
        if incurred_unparseable.at[idx]:
            reason = "incurred_unparseable"
            detail = "Total incurred contains a value that could not be parsed as a number"
        elif paid_unparseable.at[idx]:
            reason = "paid_unparseable"
            detail = "Indemnity paid contains a value that could not be parsed as a number"
        elif reserve_unparseable.at[idx]:
            reason = "reserve_unparseable"
            detail = "Indemnity reserve contains a value that could not be parsed as a number"
        elif incurred_unmapped.at[idx]:
            reason = "incurred_unmapped"
            detail = "Total incurred was never mapped to a column on this sheet"
        elif paid_and_reserve_unmapped.at[idx]:
            reason = "paid_and_reserve_unmapped"
            detail = "Both indemnity paid and indemnity reserve were never mapped to a column on this sheet"
        elif pd.isna(incurred.at[idx]):
            reason = "incurred_blank"
            detail = "Total incurred is blank on this row"
        else:
            reason = "paid_and_reserve_blank"
            detail = "Both indemnity paid and indemnity reserve are blank or unparseable on this row"
        not_evaluable_rows.append({"row_index": idx, "claim_ref": claim_ref, "reason": reason, "detail": detail})

    return {
        "arithmetic_match_count": int(match.sum()),
        "arithmetic_mismatch_count": int(mismatch.sum()),
        "arithmetic_not_evaluable_count": int(not_evaluable.sum()),
        "not_evaluable_detail": pd.DataFrame(not_evaluable_rows, columns=NOT_EVALUABLE_DETAIL_COLUMNS),
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
