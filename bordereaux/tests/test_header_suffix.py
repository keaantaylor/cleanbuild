"""Regression test for fix spec Section 2: a trailing parenthetical unit/
currency suffix on a header (e.g. "Paid to Date (GBP)") must never prevent
that header from mapping to its field -- and when the sheet has no
separate Currency column, the suffix's currency hint should populate the
row's currency instead of being silently discarded.

Uses a full sheet (not a single row), with every monetary column carrying
a suffix, per the fix spec's explicit "not just one row" requirement.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from bordereaux import ingest, schema  # noqa: E402
from bordereaux.mapping import build_mapping  # noqa: E402

N_ROWS = 25


def _build_raw() -> pd.DataFrame:
    rows = []
    for i in range(N_ROWS):
        rows.append({
            "Claim Reference": f"CLM-{i:04d}",
            "Insured Name": f"Client {i}",
            "Date of Loss (local time)": "2024-03-01",
            "Paid to Date (GBP)": 1000.0 + i,
            "O/S Reserve (GBP)": 200.0 + i,
            "Total Incurred (GBP)": 1200.0 + 2 * i,
        })
    return pd.DataFrame(rows)


def main() -> None:
    raw = _build_raw()
    result = build_mapping(list(raw.columns))

    by_field = {s.field_code: s for s in result.suggestions if s.field_code}
    for code in (schema.CLAIM_REF_CODE, schema.INSURED_NAME_CODE, schema.LOSS_DATE_CODE,
                 schema.PAID_CODE, schema.RESERVE_CODE, schema.INCURRED_CODE):
        assert code in by_field, (
            f"{code} ({schema.FIELDS_BY_CODE[code].name}) failed to map -- "
            f"suggestions were: {[(s.source_column, s.field_code) for s in result.suggestions]}"
        )
    assert schema.CURRENCY_CODE not in by_field, "fixture has no separate Currency column"
    print("2.1 OK: every suffixed header (including 3 monetary columns all sharing the "
          "'(GBP)' suffix) mapped to its field despite the parenthetical suffix")

    mapping = {s.source_column: s.field_code for s in result.suggestions if s.field_code}
    canonical = ingest.apply_mapping(raw, mapping, sheet_name="suffix_fixture")

    assert len(canonical) == N_ROWS
    assert canonical[schema.PAID_CODE].notna().all(), "some Paid Amount rows failed to populate"
    assert canonical[schema.RESERVE_CODE].notna().all(), "some Reserve rows failed to populate"
    assert canonical[schema.INCURRED_CODE].notna().all(), "some Incurred rows failed to populate"
    for i in range(N_ROWS):
        assert canonical[schema.PAID_CODE].iloc[i] == 1000.0 + i
        assert canonical[schema.RESERVE_CODE].iloc[i] == 200.0 + i
        assert canonical[schema.INCURRED_CODE].iloc[i] == 1200.0 + 2 * i
    print(f"2.1 OK: all {N_ROWS}/{N_ROWS} rows' Paid/Reserve/Incurred values populated correctly "
          "(previously this class of header wiped every value on the sheet)")

    assert (canonical[schema.CURRENCY_CODE] == "GBP").all(), (
        "currency hint from the '(GBP)' header suffix was not backfilled onto every row"
    )
    print("2.2 OK: with no separate Currency column, the '(GBP)' hint found in the header "
          f"suffix was used to populate CURRENCY for all {N_ROWS} rows instead of being discarded")

    # A sheet that DOES have its own Currency column must keep it -- the
    # suffix hint must never override a real, mapped Currency column.
    raw2 = raw.copy()
    raw2["Settlement Currency"] = "EUR"
    result2 = build_mapping(list(raw2.columns))
    mapping2 = {s.source_column: s.field_code for s in result2.suggestions if s.field_code}
    canonical2 = ingest.apply_mapping(raw2, mapping2, sheet_name="suffix_fixture_with_ccy")
    assert (canonical2[schema.CURRENCY_CODE] == "EUR").all(), (
        "a real, mapped Currency column must win over a header-suffix hint, but got "
        f"{canonical2[schema.CURRENCY_CODE].unique().tolist()}"
    )
    print("2.2 OK: a real, mapped Currency column is never overridden by a header-suffix hint")

    print("\ntest_header_suffix.py PASSED.")


if __name__ == "__main__":
    main()
