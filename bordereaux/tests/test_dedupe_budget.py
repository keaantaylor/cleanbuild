"""P1.7: the probable-duplicate check is bounded, and says so when it is not run.

Pairwise fuzzy comparison inside a name block is quadratic in the rows that
share a block and a loss-date window. A file where every insured name
shares a prefix and every loss date falls in one month (e.g. 50,000 rows of
"Insured N" in March) would need ~10^8 comparisons -- the job would run for
tens of minutes. The engine counts the candidate pairs first (cheap,
vectorised) and, above a fixed budget, does not run the check at all and
reports it as NOT ASSESSED with the reason, in coverage: never a silent
"0 probable duplicates".

Acceptance:
- the candidate-pair count equals what the pairwise loop would examine;
- over budget: no probable-duplicate records, check reported not assessed
  with the counts in the reason, exact duplicates still reported, fast;
- within budget: identical results to before (assessed, same records);
- the workbook pipeline carries the not-assessed check into coverage, the
  coverage line and the score's reliability.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from bordereaux import dedupe, report, schema  # noqa: E402


def _frame(names: list[str], dates: list[str], refs: list[str] | None = None) -> pd.DataFrame:
    n = len(names)
    df = pd.DataFrame(
        {
            schema.CLAIM_REF_CODE: refs or [f"C{i:06d}" for i in range(n)],
            schema.INSURED_NAME_CODE: names,
            schema.LOSS_DATE_CODE: pd.to_datetime(dates, format="ISO8601"),
            schema.SOURCE_SHEET_CODE: ["Sheet1"] * n,
        }
    )
    for code in (schema.CLAIM_REF_CODE, schema.INSURED_NAME_CODE, schema.SOURCE_SHEET_CODE):
        df[code] = df[code].astype("string")
    for f in schema.FIELDS:
        if f.code not in df.columns:
            df[f.code] = pd.NA
    return df


def _brute_force_candidate_pairs(df: pd.DataFrame) -> int:
    """The pairs the comparison loop visits, counted the slow, obvious way."""
    sub = df[df[schema.INSURED_NAME_CODE].notna() & df[schema.LOSS_DATE_CODE].notna()]
    keys = sub[schema.INSURED_NAME_CODE].astype(str).map(dedupe._block_key)
    total = 0
    for _, idx in sub.groupby(keys, sort=False).groups.items():
        dates = sorted(sub.loc[idx, schema.LOSS_DATE_CODE].tolist())
        for i in range(len(dates)):
            for j in range(i + 1, len(dates)):
                if (dates[j] - dates[i]).days > dedupe.ADJACENT_DAYS:
                    break
                total += 1
    return total


def test_candidate_pair_count_matches_the_comparison_loop() -> None:
    names = ["Alpha Ltd", "Alpha Ltd", "Alpine Co", "Beta Inc", "Beta Inc", "Beta Inc", "Gamma", None]
    dates = [
        "2024-01-01",
        "2024-01-04 23:00",
        "2024-01-05",
        "2024-02-01",
        "2024-02-02",
        "2024-02-09",
        "2024-03-01",
        "2024-03-01",
    ]
    df = _frame(names, dates)  # type: ignore[arg-type]
    # "al": 01-01/01-04 23:00 (3 whole days) and 01-04 23:00/01-05; "be": 02-01/02-02

    assert dedupe.probable_candidate_pairs(df) == _brute_force_candidate_pairs(df) == 2 + 1


def test_over_budget_is_not_assessed_not_silently_clean(monkeypatch: pytest.MonkeyPatch) -> None:
    n = 3000
    names = [f"Insured {i % 97}" for i in range(n)]  # one block ("in"), 97 near-identical names
    dates = [f"2024-03-{i % 28 + 1:02d}" for i in range(n)]  # one month
    refs = [f"C{i:06d}" for i in range(n)]
    refs[1] = refs[0]  # one exact resubmission, still reported
    df = _frame(names, dates, refs)
    monkeypatch.setattr(dedupe, "MAX_PROBABLE_CANDIDATE_PAIRS", 100_000)

    t0 = time.perf_counter()
    dups, check = dedupe.find_duplicates_assessed(df)
    elapsed = time.perf_counter() - t0

    pairs = dedupe.probable_candidate_pairs(df)
    assert pairs > 100_000
    assert check.assessed is False and check.candidate_pairs == pairs
    assert check.reason is not None and f"{pairs:,}" in check.reason and "100,000" in check.reason
    assert (dups["match_type"] == "probable_duplicate").sum() == 0
    assert (dups["match_type"] == "exact_duplicate").sum() == 1
    assert elapsed < 5.0, f"the budget check itself must be cheap ({elapsed:.2f}s)"


def test_within_budget_is_assessed_and_unchanged() -> None:
    names = ["Fairwind Shipping Group", "FAIRWIND SHIPPING GROUP", "Harbour Freight Ltd"]
    df = _frame(names, ["2024-01-10", "2024-01-11", "2024-01-11"])
    df[schema.INCURRED_CODE] = pd.array([1500.0, 1500.0, 900.0], dtype="Float64")  # the corroborating signal
    dups, check = dedupe.find_duplicates_assessed(df)
    assert check.assessed is True and check.reason is None and check.candidate_pairs == 1
    probable = dups[dups["match_type"] == "probable_duplicate"]
    assert list(zip(probable["claim_ref_a"], probable["claim_ref_b"], strict=True)) == [("C000000", "C000001")]
    pd.testing.assert_frame_equal(dups, dedupe.find_duplicates(df))


def test_not_assessed_check_reaches_coverage_and_reliability() -> None:
    cov = report.WorkbookCoverage.single_sheet(10, "s.xlsx")
    assert cov.not_assessed_checks == []
    cov.not_assessed_checks.append(("probable_duplicates", "too many candidate pairs"))
    line = report._coverage_line(cov)
    assert "Not assessed: probable-duplicate check (too many candidate pairs)." in line
