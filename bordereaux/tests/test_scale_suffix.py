"""TB-003 regression: a header suffix like "(USD m)" carries a scale
multiplier, not just a currency code. Header normalisation used to strip
the whole parenthetical suffix for alias matching and simply discard its
meaning, so a column headed "Paid (USD m)" bound correctly but exported
a $36,686,000 claim as $36.69 -- a silent million-fold understatement."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import pandas as pd  # noqa: E402

from bordereaux.ingest import apply_mapping  # noqa: E402
from bordereaux.mapping import parse_currency_suffix, parse_scale_suffix  # noqa: E402
from bordereaux.iso4217 import VALID_CURRENCY_CODES  # noqa: E402

MAPPING = {
    "Claim Ref": "CR0104M", "Insured Name": "CR0035M",
    "Paid (USD m)": "CR0126CM", "Reserve (USD m)": "CR0130CM", "Incurred (USD m)": "CR0155CM",
}


def test_scale_and_currency_tokens_parse_out_of_a_combined_suffix() -> None:
    assert parse_scale_suffix("USD m") == 1_000_000.0
    assert parse_scale_suffix("EUR 000s") == 1_000.0
    assert parse_scale_suffix("GBP") is None
    assert parse_scale_suffix(None) is None

    assert parse_currency_suffix("USD m", VALID_CURRENCY_CODES) == "USD"
    assert parse_currency_suffix("GBP", VALID_CURRENCY_CODES) == "GBP"
    assert parse_currency_suffix("m", VALID_CURRENCY_CODES) is None
    print("OK: scale and currency tokens both parse out of a combined suffix")


def test_millions_suffixed_column_exports_at_full_magnitude() -> None:
    raw = pd.DataFrame({
        "Claim Ref": ["CLM-SCL-00001", "CLM-SCL-00002"],
        "Insured Name": ["Alice Ltd", "Bob Co"],
        "Paid (USD m)": ["12.5", "36.686"],
        "Reserve (USD m)": ["1.0", "2.0"],
        "Incurred (USD m)": ["13.5", "38.686"],
    }).astype("string")

    canonical = apply_mapping(raw, MAPPING, sheet_name="test")

    assert canonical.at[1, "CR0126CM"] == 36_686_000.0, (
        f"CLM-SCL-00002 must export at full magnitude, got {canonical.at[1, 'CR0126CM']}"
    )
    assert canonical.at[0, "CR0126CM"] == 12_500_000.0
    assert canonical.at[0, "CR0130CM"] == 1_000_000.0
    assert canonical.at[0, "CR0155CM"] == 13_500_000.0
    assert canonical.at[0, "CR0110CM"] == "USD", "currency must be inferred from the same suffix"
    print(f"OK: CLM-SCL-00002 exports as {canonical.at[1, 'CR0126CM']:,.0f} (was 36.686 before this fix)")


if __name__ == "__main__":
    test_scale_and_currency_tokens_parse_out_of_a_combined_suffix()
    test_millions_suffixed_column_exports_at_full_magnitude()
    print("\nScale-suffix regression tests PASSED.")
