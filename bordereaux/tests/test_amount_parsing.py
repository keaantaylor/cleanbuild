"""Regression tests for Section 3: monetary parsing must strip currency
symbols and handle both thousands-separator conventions instead of
giving up, AND a value that still can't be parsed after that must make
its row NOT_EVALUABLE for arithmetic reconciliation -- never silently
substituted with zero, which previously turned a parsing failure into a
fake "arithmetic mismatch"."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import pandas as pd  # noqa: E402

from bordereaux.ingest import _parse_amount_cell, apply_mapping  # noqa: E402
from bordereaux.validation import validate  # noqa: E402

MAPPING = {
    "Claim Ref": "CR0104M", "Insured Name": "CR0035M",
    "Paid Amount": "CR0126CM", "Reserve Amount": "CR0130CM", "Incurred Amount": "CR0155CM",
}
SHEET_STATE = {"test": {"CR0126CM": "alias", "CR0130CM": "alias", "CR0155CM": "alias"}}


def test_currency_symbols_and_both_thousands_conventions() -> None:
    cases = {
        "€900,000.00": 900000.00,
        "£1,234.56": 1234.56,
        "$500.00": 500.00,
        "1.234,56": 1234.56,   # European: '.' thousands, ',' decimal
        "1,234.56": 1234.56,   # US: ',' thousands, '.' decimal
        "(500.00)": -500.00,   # accounting negative
        "  1000  ": 1000.00,
        "1,000": 1000.00,      # ambiguous comma, 3 leading digits -> thousands
        "1234,56": 1234.56,    # ambiguous comma, 2 trailing digits -> decimal
    }
    for text, expected in cases.items():
        got = _parse_amount_cell(text)
        assert got == expected, f"{text!r} parsed to {got}, expected {expected}"
    assert _parse_amount_cell("") is None
    assert _parse_amount_cell("TBC") is None
    print(f"OK: {len(cases)} currency/thousands-separator formats parse correctly")


def test_unparseable_value_is_not_evaluable_never_zero() -> None:
    raw = pd.DataFrame({
        "Claim Ref": ["C1", "C2"],
        "Insured Name": ["Alice", "Bob"],
        "Paid Amount": ["TBC", "100.00"],       # row 0: genuinely unparseable text
        "Reserve Amount": ["50.00", "25.00"],
        "Incurred Amount": ["950000.00", "125.00"],  # deliberately NOT paid+reserve, to prove
    }).astype("string")                                # it's not silently scored as a "mismatch" either

    canonical = apply_mapping(raw, MAPPING, sheet_name="test")
    assert pd.isna(canonical.at[0, "CR0126CM"]), "an unparseable cell must not silently become a number"
    assert canonical.at[0, "_unparseable_CR0126CM"], "the unparseable flag must be set for row 0"
    assert not canonical.at[1, "_unparseable_CR0126CM"], "a normally-parsing row must not be flagged"

    result = validate(canonical, sheet_field_state=SHEET_STATE)
    assert result.exceptions.empty, (
        f"an unparseable value must never be silently treated as 0 and flagged as a mismatch, "
        f"got {result.exceptions.to_dict('records')}"
    )
    assert result.arithmetic_mismatch_count == 0
    assert result.arithmetic_not_evaluable_count == 1
    assert result.arithmetic_match_count == 1  # row 1 (100+25=125) still reconciles normally

    detail = result.not_evaluable_detail
    assert len(detail) == 1
    assert detail.iloc[0]["reason"] == "paid_unparseable"
    assert detail.iloc[0]["row_index"] == 0
    print("OK: unparseable Paid Amount -> not evaluable, never a false arithmetic mismatch")


def test_forensic_report_currency_and_european_format_figures() -> None:
    """The exact figures from the forensic report -- currency-symbol and
    European-format (dot-thousands, comma-decimal) values, including
    symbol+European-format combined, which the general cases above don't
    exercise explicitly."""
    cases = {
        "€227,122.35": 227122.35,
        "£227,122.35": 227122.35,
        "$227,122.35": 227122.35,
        "227,122.35": 227122.35,
        "478.776,12": 478776.12,
        "€478.776,12": 478776.12,
        "£478.776,12": 478776.12,
    }
    for text, expected in cases.items():
        got = _parse_amount_cell(text)
        assert got == expected, f"{text!r} parsed to {got}, expected {expected}"
    print(f"OK: {len(cases)} forensic-report currency/European-format figures parse correctly")


def test_single_row_all_three_amounts_european_format() -> None:
    """Reproduces the reported CLM-P0-00031 shape: a row whose paid,
    reserve AND incurred are all European-format (comma-decimal) text.
    Each field is parsed from its own source column independently, so
    this locks in that all three resolve correctly rather than one
    unparseable convention blanking the whole row."""
    raw = pd.DataFrame({
        "Claim Ref": ["CLM-P0-00031"], "Insured Name": ["Test Insured"],
        "Paid Amount": ["478.776,12"], "Reserve Amount": ["100.000,00"], "Incurred Amount": ["578.776,12"],
    }).astype("string")
    canonical = apply_mapping(raw, MAPPING, sheet_name="test")
    assert canonical.at[0, "CR0126CM"] == 478776.12
    assert canonical.at[0, "CR0130CM"] == 100000.00
    assert canonical.at[0, "CR0155CM"] == 578776.12
    assert not canonical.at[0, "_unparseable_CR0126CM"]
    assert not canonical.at[0, "_unparseable_CR0130CM"]
    assert not canonical.at[0, "_unparseable_CR0155CM"]
    print("OK: CLM-P0-00031-style row (all-European-format paid/reserve/incurred) parses fully, nothing blank")


def test_genuinely_blank_paid_still_computable_as_zero() -> None:
    """A cell that's simply empty (no text at all) is the established
    "$0 / not yet reported" bordereau convention, distinct from a cell
    that had text but failed to parse -- this must be unaffected by the
    Section 3 fix."""
    raw = pd.DataFrame({
        "Claim Ref": ["C1"], "Insured Name": ["Alice"],
        "Paid Amount": [""], "Reserve Amount": ["100.00"], "Incurred Amount": ["100.00"],
    }).astype("string")
    canonical = apply_mapping(raw, MAPPING, sheet_name="test")
    result = validate(canonical, sheet_field_state=SHEET_STATE)
    assert result.arithmetic_match_count == 1, "blank paid (implicit $0) + reserve == incurred should still reconcile"
    assert result.arithmetic_not_evaluable_count == 0
    print("OK: a genuinely blank cell is still treated as the existing $0 convention, not flagged as unparseable")


if __name__ == "__main__":
    test_currency_symbols_and_both_thousands_conventions()
    test_forensic_report_currency_and_european_format_figures()
    test_single_row_all_three_amounts_european_format()
    test_unparseable_value_is_not_evaluable_never_zero()
    test_genuinely_blank_paid_still_computable_as_zero()
    print("\nAmount-parsing regression tests PASSED.")
