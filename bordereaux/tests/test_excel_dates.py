"""Regression tests: Excel serial dates (a bare number, no date
formatting applied to the cell -- common in a CSV export, or a date
column pasted as values) must resolve to a real calendar date instead of
coming back NaT, without ever reinterpreting an ordinary reference
number living in some other, non-date-mapped column, and without
guessing a date from an implausibly small number."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import pandas as pd  # noqa: E402

from bordereaux.ingest import apply_mapping  # noqa: E402

MAPPING = {"Claim Ref": "CR0104M", "Insured Name": "CR0035M", "Date of Loss": "CR0119CM"}


def test_excel_serial_dates_resolve_to_correct_calendar_dates() -> None:
    # 44197 = 2021-01-01, 44926 = 2022-12-31, 25569 = 1970-01-01 -- well-known
    # reference points for the standard 1899-12-30 Excel epoch.
    raw = pd.DataFrame({
        "Claim Ref": ["C1", "C2", "C3"], "Insured Name": ["Alice", "Bob", "Carl"],
        "Date of Loss": ["44197", "44926", "25569"],
    }).astype("string")
    canonical = apply_mapping(raw, MAPPING, sheet_name="test")
    dates = canonical["CR0119CM"]
    assert dates.iloc[0] == pd.Timestamp("2021-01-01"), dates.tolist()
    assert dates.iloc[1] == pd.Timestamp("2022-12-31"), dates.tolist()
    assert dates.iloc[2] == pd.Timestamp("1970-01-01"), dates.tolist()
    print("OK: 3/3 Excel serial dates resolved to the correct calendar date")


def test_mixed_serial_and_formatted_dates_in_one_column() -> None:
    """A real bordereau column is rarely 100% one format -- some rows
    carry a real date string, others a bare serial left over from a CSV
    round-trip. Both must resolve in the same pass."""
    raw = pd.DataFrame({
        "Claim Ref": ["C1", "C2"], "Insured Name": ["Alice", "Bob"],
        "Date of Loss": ["44197", "2024-03-15"],
    }).astype("string")
    canonical = apply_mapping(raw, MAPPING, sheet_name="test")
    dates = canonical["CR0119CM"]
    assert dates.iloc[0] == pd.Timestamp("2021-01-01"), dates.tolist()
    assert dates.iloc[1] == pd.Timestamp("2024-03-15"), dates.tolist()
    print("OK: a mixed serial + formatted-string date column resolves both correctly")


def test_ordinary_numeric_identifiers_are_never_converted_to_dates() -> None:
    """A column that looks numeric but is mapped to a non-date field
    (claim reference) must never be reinterpreted as a date just because
    Excel-serial-date support now exists for date-mapped fields."""
    raw = pd.DataFrame({
        "Claim Ref": ["44197", "44926", "25569"],  # look exactly like the serials above
        "Insured Name": ["Alice", "Bob", "Carl"],
        "Date of Loss": ["2024-01-01", "2024-01-02", "2024-01-03"],
    }).astype("string")
    canonical = apply_mapping(raw, MAPPING, sheet_name="test")
    assert canonical["CR0104M"].tolist() == ["44197", "44926", "25569"], (
        f"a claim reference that looks like an Excel serial date must stay exactly as reported text, "
        f"got {canonical['CR0104M'].tolist()}"
    )
    print("OK: claim-reference-shaped numbers are never reinterpreted as dates")


def test_implausible_small_numbers_do_not_become_dates() -> None:
    """Even within a genuine date-mapped column, a tiny number (1, 12)
    stays unresolved rather than resolving to a wild pre-1902 date guess
    -- far more likely a data-entry error than a real serial."""
    raw = pd.DataFrame({
        "Claim Ref": ["C1", "C2"], "Insured Name": ["Alice", "Bob"],
        "Date of Loss": ["1", "12"],
    }).astype("string")
    canonical = apply_mapping(raw, MAPPING, sheet_name="test")
    assert canonical["CR0119CM"].isna().all(), (
        f"tiny numbers should not resolve to a wild guessed date, got {canonical['CR0119CM'].tolist()}"
    )
    print("OK: implausibly small numbers in a date column stay unresolved rather than guessing a date")


if __name__ == "__main__":
    test_excel_serial_dates_resolve_to_correct_calendar_dates()
    test_mixed_serial_and_formatted_dates_in_one_column()
    test_ordinary_numeric_identifiers_are_never_converted_to_dates()
    test_implausible_small_numbers_do_not_become_dates()
    print("\nExcel serial date regression tests PASSED.")
