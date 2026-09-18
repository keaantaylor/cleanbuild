"""Regression test for fix spec Section 3:

3.1: monetary text with a currency symbol and/or thousands separators (in
either convention) must parse instead of silently becoming blank.

3.2: arithmetic reconciliation must classify a row as NOT EVALUABLE --
never MATCH or MISMATCH -- whenever any of paid/reserve/incurred is
missing, blank, or failed to parse. A blank value must never be treated
as zero.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from bordereaux import ingest, schema, validation  # noqa: E402

MAPPING = {
    "Claim Reference": schema.CLAIM_REF_CODE,
    "Insured Name": schema.INSURED_NAME_CODE,
    "Paid Amount": schema.PAID_CODE,
    "Reserve Amount": schema.RESERVE_CODE,
    "Incurred Amount": schema.INCURRED_CODE,
}


def test_currency_symbol_and_separator_parsing() -> None:
    raw = pd.DataFrame({
        "Claim Reference": ["C1", "C2", "C3", "C4", "C5", "C6"],
        "Insured Name": ["A", "B", "C", "D", "E", "F"],
        # comma-thousands / period-decimal (US/UK convention)
        "Paid Amount": ["€900,000.00", "£1,234.56", "$45,000", "1.234,56", "(500.00)", None],
        "Reserve Amount": ["100000", "0", "0", "0", "0", "0"],
        "Incurred Amount": ["1000000", "1234.56", "45000", "1234.56", "-500", "0"],
    })
    canonical = ingest.apply_mapping(raw, MAPPING, sheet_name="s")
    paid = canonical[schema.PAID_CODE]

    assert paid.iloc[0] == 900000.00, f"'€900,000.00' should parse to 900000.0, got {paid.iloc[0]}"
    assert paid.iloc[1] == 1234.56, f"'£1,234.56' should parse to 1234.56, got {paid.iloc[1]}"
    assert paid.iloc[2] == 45000.0, f"'$45,000' should parse to 45000.0, got {paid.iloc[2]}"
    assert paid.iloc[3] == 1234.56, f"'1.234,56' (EU convention) should parse to 1234.56, got {paid.iloc[3]}"
    assert paid.iloc[4] == -500.00, f"'(500.00)' should parse to -500.0, got {paid.iloc[4]}"
    assert pd.isna(paid.iloc[5]), "a genuinely blank cell must stay blank, not become 0"
    print("3.1 OK: currency symbols (€/£/$) and both thousands-separator conventions "
          "(1,234.56 and 1.234,56) all parse correctly; a genuinely blank cell stays blank")


def test_unparseable_paid_is_not_evaluable_not_mismatch() -> None:
    raw = pd.DataFrame({
        "Claim Reference": ["C1", "C2", "C3"],
        "Insured Name": ["A", "B", "C"],
        # C1: paid is genuine unparseable garbage (not a currency-symbol
        # case fixed by 3.1 -- simulates a residual ingestion failure).
        # C2: paid is genuinely blank. C3: a normal fully-reconciled row.
        "Paid Amount": ["not a number", None, "1000"],
        "Reserve Amount": ["500", "500", "500"],
        "Incurred Amount": ["999999", "999999", "1500"],
    })
    canonical = ingest.apply_mapping(raw, MAPPING, sheet_name="s")
    result = validation.validate(canonical)

    mismatch_refs = set(result.exceptions.loc[result.exceptions["rule"] == "arithmetic_mismatch", "claim_ref"])
    assert "C1" not in mismatch_refs, (
        "a row whose Paid Amount failed to parse must never be reported as an arithmetic "
        "mismatch -- that mislabels an ingestion failure as a business-data problem"
    )
    assert "C2" not in mismatch_refs, "a row with a genuinely blank Paid Amount must not be a mismatch either"
    assert result.arithmetic_not_evaluable_count == 2, (
        f"expected exactly 2 not-evaluable rows (C1, C2), got {result.arithmetic_not_evaluable_count}"
    )
    assert result.arithmetic_match_count == 1 and result.arithmetic_mismatch_count == 0
    print("3.2 OK: rows with an unparseable or blank Paid Amount are classified NOT_EVALUABLE "
          "(never silently substituted with 0 to produce a false arithmetic_mismatch); "
          "the one fully-populated, reconciling row still reports MATCH")


def main() -> None:
    test_currency_symbol_and_separator_parsing()
    test_unparseable_paid_is_not_evaluable_not_mismatch()
    print("\ntest_amount_parsing.py PASSED.")


if __name__ == "__main__":
    main()
