"""Regression test for Section 4: duplicate detection must not collapse
under realistic data volume. Reproduces the reported shape -- many
legitimate long-standing clients, each with several claims under
distinct policies/years (ordinary repeat business, not duplicates), plus
a small number of genuinely planted duplicates (same name, same policy,
near-identical date) -- and asserts the flagged count stays close to the
planted count, not orders of magnitude higher, and that it completes
quickly (blocking should make this roughly linear, not quadratic)."""

from __future__ import annotations

import random
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import pandas as pd  # noqa: E402

from bordereaux import schema  # noqa: E402
from bordereaux.dedupe import find_duplicates  # noqa: E402

_FIRST_WORDS = ["Northfield", "Bluewater", "Harrington", "Silverline", "Oakridge", "Meridian",
                "Castlebay", "Redstone", "Fairview", "Ashworth", "Kingsley", "Brightmoor",
                "Thornbury", "Westgate", "Ironwood", "Sandpiper", "Greenhaven", "Lockwood",
                "Marlowe", "Pemberton", "Rosewood", "Stonebridge", "Underwood", "Whitfield", "Yardley"]
_SECOND_WORDS = ["Shipping", "Logistics", "Freight", "Trading", "Holdings", "Marine", "Transport", "Industries"]
_SUFFIXES = ["Ltd", "Group", "Inc", "PLC", "Co"]


def _client_name(c: int) -> str:
    first = _FIRST_WORDS[c % len(_FIRST_WORDS)]
    second = _SECOND_WORDS[(c // len(_FIRST_WORDS)) % len(_SECOND_WORDS)]
    suffix = _SUFFIXES[c % len(_SUFFIXES)]
    return f"{first} {second} {suffix}"


def _build_realistic_repeat_business_frame(n_clients: int, occurrences: int, n_planted: int, seed: int) -> tuple[pd.DataFrame, int]:
    """n_clients legitimate repeat clients, each with `occurrences` claims
    under DISTINCT policy references (ordinary renewal/multi-policy
    business -- never the same policy twice), plus n_planted genuine
    duplicates (same name, same policy, loss date +1 day)."""
    rng = random.Random(seed)
    base_date = pd.Timestamp("2022-01-01")
    rows: list[dict] = []
    counter = 1
    for c in range(n_clients):
        name = _client_name(c)
        for occ in range(occurrences):
            rows.append({
                schema.CLAIM_REF_CODE: f"C{counter:07d}",
                schema.INSURED_NAME_CODE: name,
                schema.POLICY_REF_CODE: f"POL-{c:04d}-{occ:02d}",
                schema.LOSS_DATE_CODE: base_date + pd.Timedelta(days=rng.randint(0, 900)),
                schema.PAID_CODE: 1000.0, schema.RESERVE_CODE: 500.0, schema.INCURRED_CODE: 1500.0,
                schema.SOURCE_SHEET_CODE: "Sheet1",
            })
            counter += 1

    planted_indices = rng.sample(range(len(rows)), n_planted)
    for i in planted_indices:
        src = rows[i]
        rows.append({
            schema.CLAIM_REF_CODE: f"C{counter:07d}",
            schema.INSURED_NAME_CODE: src[schema.INSURED_NAME_CODE],
            schema.POLICY_REF_CODE: src[schema.POLICY_REF_CODE],
            schema.LOSS_DATE_CODE: src[schema.LOSS_DATE_CODE] + pd.Timedelta(days=1),
            schema.PAID_CODE: 1000.0, schema.RESERVE_CODE: 500.0, schema.INCURRED_CODE: 1500.0,
            schema.SOURCE_SHEET_CODE: "Sheet1",
        })
        counter += 1

    df = pd.DataFrame(rows)
    for code in (schema.CLAIM_REF_CODE, schema.INSURED_NAME_CODE, schema.POLICY_REF_CODE, schema.SOURCE_SHEET_CODE):
        df[code] = df[code].astype("string")
    df[schema.LOSS_DATE_CODE] = pd.to_datetime(df[schema.LOSS_DATE_CODE])
    for f in schema.FIELDS:
        if f.code not in df.columns:
            df[f.code] = pd.NA
    return df, n_planted


def test_repeat_business_does_not_flood_probable_duplicates() -> None:
    df, n_planted = _build_realistic_repeat_business_frame(n_clients=100, occurrences=20, n_planted=25, seed=42)

    start = time.time()
    dupes = find_duplicates(df)
    elapsed = time.time() - start

    flagged = dupes[dupes["match_type"] == "probable_duplicate"]
    assert len(flagged) <= n_planted * 2, (
        f"flagged count ({len(flagged)}) should stay close to the planted count ({n_planted}), "
        f"not balloon from ordinary repeat business with different policy references"
    )

    # every flagged pair must involve at least one of the planted rows -- zero false positives
    # from the 100 legitimate repeat clients, whose claims all use distinct policy references.
    base_row_count = 100 * 20
    planted_claim_refs = set(df.iloc[base_row_count:][schema.CLAIM_REF_CODE])
    false_positive_pairs = sum(
        1 for _, row in flagged.iterrows()
        if row["claim_ref_a"] not in planted_claim_refs and row["claim_ref_b"] not in planted_claim_refs
    )
    assert false_positive_pairs == 0, (
        f"{false_positive_pairs} flagged pair(s) involved only legitimate repeat-business rows "
        f"(different policy references) -- these must never be flagged as probable duplicates"
    )
    assert elapsed < 5.0, f"dedupe over {len(df)} rows took {elapsed:.2f}s -- blocking should keep this fast"
    print(f"OK: {len(df)} rows ({100} clients x 20 legit occurrences + {n_planted} planted) -> "
          f"{len(flagged)} flagged (0 false positives), {elapsed:.3f}s")


if __name__ == "__main__":
    test_repeat_business_does_not_flood_probable_duplicates()
    print("\nDedupe-at-scale regression test PASSED.")
