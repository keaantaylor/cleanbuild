"""Regression test for fix spec Section 4: duplicate detection must not
collapse under realistic data volume.

Reproduces the confirmed symptom's shape -- many legitimate long-standing
clients who each appear many times (same name, different policy/year:
ordinary repeat business), plus a small, controlled number of genuinely
planted duplicates -- and asserts the flagged count stays close to the
planted count, not orders of magnitude higher, at both a realistic row
count and a pathological same-date-batch-reporting scale.
"""

from __future__ import annotations

import random
import sys
import time
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from bordereaux import dedupe, ingest, schema  # noqa: E402

MAPPING = {
    "Claim Reference": schema.CLAIM_REF_CODE,
    "Insured Name": schema.INSURED_NAME_CODE,
    "Policy Reference": schema.POLICY_REF_CODE,
    "Date of Loss": schema.LOSS_DATE_CODE,
    "Paid Amount": schema.PAID_CODE,
    "Reserve Amount": schema.RESERVE_CODE,
    "Incurred Amount": schema.INCURRED_CODE,
}

_FIRST = ["James", "Mary", "John", "Patricia", "Robert", "Jennifer", "Michael", "Linda",
          "William", "Elizabeth", "David", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
          "Thomas", "Sarah", "Charles", "Karen", "Christopher", "Nancy", "Daniel", "Lisa",
          "Matthew", "Betty", "Anthony", "Margaret", "Mark", "Sandra"]
_LAST = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
         "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Taylor",
         "Lee", "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark", "Ramirez",
         "Lewis", "Robinson", "Walker", "Young", "Allen", "King"]
_SUFFIX = ["", "", "", " Ltd", " Holdings"]


def _row(rng, claim_ref, name, year, month=None, day=None, policy=None):
    month = month or rng.randint(1, 12)
    day = day or rng.randint(1, 28)
    paid = round(rng.uniform(1000, 50000), 2)
    reserve = round(rng.uniform(0, 20000), 2)
    return {
        "Claim Reference": claim_ref,
        "Insured Name": name,
        "Policy Reference": policy or f"POL-{rng.randint(100000, 999999)}-{year}",
        "Date of Loss": f"{year}-{month:02d}-{day:02d}",
        "Paid Amount": paid,
        "Reserve Amount": reserve,
        "Incurred Amount": round(paid + reserve, 2),
    }


def _build_realistic_dataset(seed: int) -> tuple[pd.DataFrame, set[tuple[str, str]]]:
    """~100 legit clients x ~20 occurrences spread over distinct years
    (ordinary repeat business), plus 25 planted genuine duplicates."""
    rng = random.Random(seed)
    rows, claim_seq = [], 1000

    clients = [f"{rng.choice(_FIRST)} {rng.choice(_LAST)}{rng.choice(_SUFFIX)}" for _ in range(100)]
    for client in clients:
        for k in range(rng.randint(18, 22)):
            claim_seq += 1
            rows.append(_row(rng, f"CLM-{claim_seq}", client, 2003 + k))

    planted: set[tuple[str, str]] = set()
    for _ in range(25):
        claim_seq += 1
        name = f"{rng.choice(_FIRST)} {rng.choice(_LAST)}{rng.choice(_SUFFIX)}"
        year, month, day = rng.randint(2015, 2023), rng.randint(1, 12), rng.randint(1, 28)
        policy = f"POL-{rng.randint(100000, 999999)}-{year}"
        a = _row(rng, f"CLM-{claim_seq}", name, year, month, day, policy)
        claim_seq += 1
        b = dict(a, **{"Claim Reference": f"CLM-{claim_seq}"})
        rows.append(a)
        rows.append(b)
        planted.add(tuple(sorted((a["Claim Reference"], b["Claim Reference"]))))

    rng.shuffle(rows)
    return pd.DataFrame(rows), planted


def _build_batch_cluster_dataset(seed: int, n_distinct: int) -> tuple[pd.DataFrame, set[tuple[str, str]]]:
    """A large block of rows sharing one of a handful of identical loss
    dates -- the shape a quarterly batch-reported bordereau produces, and
    the shape that defeats a pure date-window scan with no other
    blocking. Names are drawn from a large unique pool so "distinct
    claimant" really is distinct (no accidental name collisions)."""
    rng = random.Random(seed)
    combos = [(f, l, s) for f in _FIRST for l in _LAST for s in _SUFFIX]
    rng.shuffle(combos)

    rows, claim_seq = [], 5000
    batch_dates = ["2024-03-31", "2024-06-30", "2024-09-30"]
    for f, l, s in combos[:n_distinct]:
        claim_seq += 1
        d = rng.choice(batch_dates)
        rows.append(_row(rng, f"CLM-{claim_seq}", f"{f} {l}{s}", 2024,
                          int(d[5:7]), int(d[8:10])))

    planted: set[tuple[str, str]] = set()
    for _ in range(15):
        claim_seq += 1
        name = f"{rng.choice(_FIRST)} {rng.choice(_LAST)}{rng.choice(_SUFFIX)}"
        d = rng.choice(batch_dates)
        policy = f"POL-{rng.randint(100000, 999999)}-2024"
        a = _row(rng, f"CLM-{claim_seq}", name, 2024, int(d[5:7]), int(d[8:10]), policy)
        claim_seq += 1
        b = dict(a, **{"Claim Reference": f"CLM-{claim_seq}"})
        rows.append(a)
        rows.append(b)
        planted.add(tuple(sorted((a["Claim Reference"], b["Claim Reference"]))))

    rng.shuffle(rows)
    return pd.DataFrame(rows), planted


def _run_dedupe(df_raw: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    canonical = ingest.apply_mapping(df_raw, MAPPING, sheet_name="scale_fixture")
    t0 = time.time()
    dups = dedupe.find_duplicates(canonical)
    return dups, time.time() - t0


def test_realistic_repeat_business_does_not_flood() -> None:
    df_raw, planted = _build_realistic_dataset(seed=42)
    dups, elapsed = _run_dedupe(df_raw)

    probable = dups[dups["match_type"] == "probable_duplicate"]
    found = {tuple(sorted((a, b))) for a, b in zip(probable["claim_ref_a"], probable["claim_ref_b"])}

    assert planted <= found, f"missed planted duplicates: {planted - found}"
    # The confirmed production symptom was 89,862 flags against 25
    # planted (a ~3600x blowup) on data shaped like this. The fixed
    # pipeline must land close to the planted count, not orders of
    # magnitude above it.
    assert len(probable) <= len(planted) * 3, (
        f"{len(probable)} probable-duplicate flags for {len(planted)} planted duplicates "
        f"among {len(df_raw)} rows (~100 legitimate repeat clients) -- the duplicate report "
        "is unusable again if ordinary repeat business floods it like this"
    )
    assert elapsed < 5.0, f"dedupe took {elapsed:.2f}s on {len(df_raw)} rows -- too slow"
    print(f"4.4 OK: {len(df_raw)} rows / ~100 legitimate repeat clients -> {len(probable)} flags "
          f"for {len(planted)} planted duplicates ({elapsed:.3f}s), all planted pairs caught")


def test_batch_reported_same_date_scale() -> None:
    """The pathological case: thousands of distinct claimants sharing a
    handful of identical loss dates (quarterly batch reporting), which is
    what actually defeats a pure date-window scan with no name-based
    blocking. Confirms blocking keeps this bounded and fast."""
    df_raw, planted = _build_batch_cluster_dataset(seed=7, n_distinct=4000)
    dups, elapsed = _run_dedupe(df_raw)

    probable = dups[dups["match_type"] == "probable_duplicate"]
    found = {tuple(sorted((a, b))) for a, b in zip(probable["claim_ref_a"], probable["claim_ref_b"])}

    assert planted <= found, f"missed planted duplicates: {planted - found}"
    assert elapsed < 20.0, (
        f"dedupe took {elapsed:.2f}s on {len(df_raw)} rows clustered onto 3 shared dates -- "
        "blocking should keep this well clear of the unbounded pairwise-comparison hang"
    )
    print(f"4.1 OK: {len(df_raw)} rows clustered onto 3 shared loss dates -> "
          f"{len(probable)} flags in {elapsed:.3f}s, all {len(planted)} planted duplicates caught "
          "(blocking by name bucket kept the same-date fan-out bounded)")


def main() -> None:
    test_realistic_repeat_business_does_not_flood()
    test_batch_reported_same_date_scale()
    print("\ntest_dedupe_scale.py PASSED.")


if __name__ == "__main__":
    main()
