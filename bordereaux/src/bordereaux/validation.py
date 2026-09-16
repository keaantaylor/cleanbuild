"""Section 8 validation rules against the canonical DataFrame."""

from __future__ import annotations

import datetime as dt

import pandas as pd

from . import schema
from .iso4217 import VALID_CURRENCY_CODES

EXCEPTION_COLUMNS = ["row_index", "claim_ref", "rule", "detail"]


def validate(df: pd.DataFrame) -> pd.DataFrame:
    """Returns one row per exception found in df (canonical DataFrame,
    columns = Section 3 field codes)."""
    exceptions: list[dict] = []

    def flag(idx, rule: str, detail: str) -> None:
        claim_ref = df.at[idx, schema.CLAIM_REF_CODE] if schema.CLAIM_REF_CODE in df.columns else None
        exceptions.append({
            "row_index": idx,
            "claim_ref": claim_ref if pd.notna(claim_ref) else None,
            "rule": rule,
            "detail": detail,
        })

    _check_mandatory_fields(df, flag)
    _check_arithmetic(df, flag)
    _check_dates(df, flag)
    _check_currency(df, flag)
    _check_status_enum(df, flag)

    return pd.DataFrame(exceptions, columns=EXCEPTION_COLUMNS)


def _check_mandatory_fields(df: pd.DataFrame, flag) -> None:
    for code in schema.REQUIRED_CODES:
        spec = schema.FIELDS_BY_CODE[code]
        for idx in df.index[df[code].isna()]:
            flag(idx, "missing_mandatory_field", f"{code} ({spec.name}) is missing")

    both_missing = df[schema.PAID_CODE].isna() & df[schema.RESERVE_CODE].isna()
    for idx in df.index[both_missing]:
        flag(idx, "missing_mandatory_field",
             "both indemnity paid and indemnity reserve are missing; at least one is required")


def _check_arithmetic(df: pd.DataFrame, flag) -> None:
    paid = df[schema.PAID_CODE]
    reserve = df[schema.RESERVE_CODE]
    incurred = df[schema.INCURRED_CODE]

    computable = incurred.notna() & (paid.notna() | reserve.notna())
    expected = paid.fillna(0) + reserve.fillna(0)
    diff = (incurred - expected).abs()
    bad = computable & (diff > schema.ARITHMETIC_TOLERANCE)

    for idx in df.index[bad]:
        flag(idx, "arithmetic_mismatch",
             f"incurred={incurred.at[idx]} but paid+reserve={expected.at[idx]}")


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
