"""Deterministic reconciliation: totals vs detail, cross-sheet, previous submission."""

from __future__ import annotations

import pandas as pd

from bordereaux import reconcile
from bordereaux import schema as S
from bordereaux.ingest import ExcludedRow


def _rows(sheet: str, refs, incurred, rows, period=None, paid=None, prev_paid=None, ccy="GBP") -> pd.DataFrame:
    n = len(refs)
    return pd.DataFrame({S.CLAIM_REF_CODE: refs, S.INCURRED_CODE: incurred, S.CURRENCY_CODE: [ccy] * n,
                         S.SOURCE_SHEET_CODE: [sheet] * n, "_source_row": rows,
                         S.PERIOD_CODE: [period] * n, S.PAID_TD_CODE: paid or [None] * n,
                         S.PREV_PAID_CODE: prev_paid or [None] * n})


def test_parse_amount_reads_accounting_forms_and_refuses_text():
    assert reconcile.parse_amount("1,234.50") == 1234.5
    assert reconcile.parse_amount("(1,234.50)") == -1234.5
    assert reconcile.parse_amount("1234.5-") == -1234.5
    assert reconcile.parse_amount("£ 12") == 12.0
    assert reconcile.parse_amount("Total") is None and reconcile.parse_amount("") is None


def test_total_line_that_disagrees_with_its_rows_is_flagged_on_the_total_cell():
    df = _rows("Claims", ["A", "B", "C"], [100.0, 200.0, 300.0], [2, 3, 4])
    total = ExcludedRow("Claims", 5, "subtotal", "total", values={"Incurred": "610.00"})
    out = reconcile.totals_vs_detail(df, [total], {"Claims": {"Incurred": S.INCURRED_CODE}})
    assert len(out) == 1
    f = out.iloc[0]
    assert f["rule"] == "totals_mismatch" and f["at_row"] == 5 and f["field_code"] == S.INCURRED_CODE
    assert f["expected"] == 600.0 and f["actual"] == 610.0 and "difference 10.00" in f["detail"]


def test_total_that_matches_section_or_grand_total_passes():
    df = _rows("Claims", ["A", "B", "C", "D"], [100.0, 200.0, 50.0, 50.0], [2, 3, 5, 6])
    sub = ExcludedRow("Claims", 4, "subtotal", "", values={"Incurred": "300"})
    grand = ExcludedRow("Claims", 7, "subtotal", "", values={"Incurred": "400"})  # all rows above
    out = reconcile.totals_vs_detail(df, [sub, grand], {"Claims": {"Incurred": S.INCURRED_CODE}})
    assert out.empty


def test_same_claim_and_period_on_two_sheets_with_different_amounts():
    df = pd.concat([_rows("March", ["C1", "C2"], [500.0, 80.0], [2, 3], period="2026-03"),
                    _rows("Copy", ["C1", "C2"], [520.0, 80.0], [2, 3], period="2026-03")], ignore_index=True)
    out = reconcile.cross_sheet_conflicts(df)
    assert len(out) == 1
    f = out.iloc[0]
    assert f["rule"] == "cross_sheet_conflict" and f["row_index"] == 2 and f["expected"] == 500.0 and f["actual"] == 520.0
    # Different periods are development, not a conflict.
    df2 = pd.concat([_rows("Feb", ["C1"], [500.0], [2], period="2026-02"),
                     _rows("Mar", ["C1"], [520.0], [2], period="2026-03")], ignore_index=True)
    assert reconcile.cross_sheet_conflicts(df2).empty


def test_previous_submission_paid_decrease_and_rollforward_break():
    prev = _rows("Feb", ["C1", "C2", "C3"], [0, 0, 0], [2, 3, 4], paid=[1000.0, 500.0, 300.0])
    cur = _rows("Mar", ["C1", "c2 ", "C3"], [0, 0, 0], [2, 3, 4], paid=[900.0, 600.0, 300.0],
                prev_paid=[1000.0, 450.0, 300.0])
    out = reconcile.against_previous(cur, prev, "previous submission 'Feb.xlsx'")
    got = {(r["rule"], r["claim_ref"]) for r in out.to_dict("records")}
    assert got == {("paid_decreased", "C1"), ("rollforward_break", "c2 ")}
    dec = out[out["rule"] == "paid_decreased"].iloc[0]
    assert dec["expected"] == 1000.0 and dec["actual"] == 900.0 and "sheet 'Feb' row 2" in dec["detail"]


def test_previous_submission_skips_claims_reported_in_another_currency():
    prev = _rows("Feb", ["C1"], [0], [2], paid=[1000.0], ccy="USD")
    cur = _rows("Mar", ["C1"], [0], [2], paid=[800.0], ccy="EUR")
    assert reconcile.against_previous(cur, prev, "prev").empty
