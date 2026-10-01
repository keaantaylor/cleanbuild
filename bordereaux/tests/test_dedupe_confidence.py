"""Probable duplicates need corroboration and carry a confidence score."""

from __future__ import annotations

import pandas as pd

from bordereaux import dedupe, schema


def _df(rows):
    cols = [schema.CLAIM_REF_CODE, schema.INSURED_NAME_CODE, schema.LOSS_DATE_CODE, schema.POLICY_REF_CODE,
            schema.CURRENCY_CODE, schema.INCURRED_CODE, schema.PAID_TD_CODE, schema.RESERVE_CODE,
            schema.SOURCE_SHEET_CODE, schema.STATUS_CODE, schema.PERIOD_CODE]
    df = pd.DataFrame(rows, columns=cols)
    df[schema.LOSS_DATE_CODE] = pd.to_datetime(df[schema.LOSS_DATE_CODE])
    for c in schema.MONETARY_CODES:
        if c not in df.columns:
            df[c] = float("nan")
    return df


def _probable(df):
    d, _ = dedupe.find_duplicates_assessed(df)
    return d[d["match_type"] == "probable_duplicate"]


def test_same_loss_under_a_different_reference_is_caught():
    df = _df([
        ["CLM-100001", "Aoife Kelly", "2026-06-01", "1234567", "EUR", 5000.0, 2000.0, 3000.0, "S", "open", "2026-07"],
        ["CLM-200077", "Aoife Kelly", "2026-06-02", "1234567", "EUR", 5000.0, 2000.0, 3000.0, "S", "open", "2026-07"],
    ])
    p = _probable(df)
    assert len(p) == 1 and p.iloc[0]["confidence"] >= dedupe.PROBABLE_MIN_CONFIDENCE
    assert "policy references match" in p.iloc[0]["detail"]


def test_transposed_reference_is_caught_without_a_policy_match():
    df = _df([
        ["CLM-100123", "Sean Byrne", "2026-06-01", None, "EUR", 7000.0, 7000.0, 0.0, "S", "open", "2026-07"],
        ["CLM-100132", "Sean Byrne", "2026-06-01", None, "EUR", 7100.0, 7100.0, 0.0, "S", "open", "2026-07"],
    ])
    p = _probable(df)
    assert len(p) == 1 and "transposition" in p.iloc[0]["detail"]


def test_common_name_near_date_alone_is_not_a_duplicate():
    df = _df([
        ["CLM-100001", "Sean Kelly", "2026-06-01", "1111111", "EUR", 5000.0, 5000.0, 0.0, "S", "open", "2026-07"],
        ["CLM-300555", "Sean Kelly", "2026-06-03", "9999999", "EUR", 41000.0, 1000.0, 40000.0, "S", "open", "2026-07"],
    ])
    assert _probable(df).empty


def test_different_currencies_are_never_paired():
    df = _df([
        ["CLM-100001", "Niamh Ryan", "2026-06-01", "1234567", "EUR", 5000.0, 5000.0, 0.0, "S", "open", "2026-07"],
        ["CLM-900001", "Niamh Ryan", "2026-06-01", "1234567", "GBP", 5000.0, 5000.0, 0.0, "S", "open", "2026-07"],
    ])
    assert _probable(df).empty
