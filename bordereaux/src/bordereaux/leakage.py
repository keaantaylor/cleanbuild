"""Truebind 2.1: payment-leakage detector.

Industry benchmarks put claims leakage at 5-10% of total claim payments
(~$67bn/year in the US alone); duplicate-payment detection is the
highest-confidence entry point into reducing it. This extends the
existing claim-record duplicate detector (dedupe.py) into a distinct
lens: same payee/insured (normalized) + same-or-near-identical *payment
amount* + an overlapping/adjacent date window -> a probable duplicate
*payment*, not just a duplicate claim record.

Tri-state discipline, never collapsed to a boolean:
  CERTAIN  -- exact claim reference match (the same claim, paid twice)
  PROBABLE -- name + amount + date match within the tight window,
              different claim reference
  POSSIBLE -- same payee, amount within tolerance, date outside the tight
              window but within the wider one

All thresholds live in DEFAULT_CONFIG, not hardcoded inline, per the
redevelopment prompt's "no hardcoded business rules" rule -- an ops lead
should be able to tune these without a code change.
"""

from __future__ import annotations

import itertools

import pandas as pd
from rapidfuzz import fuzz

from . import schema
from .dedupe import normalize_name

DEFAULT_CONFIG = {
    "amount_tolerance_pct": 0.02,  # +/-2%
    "tight_date_window_days": 30,  # PROBABLE cutoff
    "wide_date_window_days": 90,  # POSSIBLE cutoff
    "name_similarity_threshold": 88.0,
}

CONFIDENCE_TIERS = ("CERTAIN", "PROBABLE", "POSSIBLE")
EXPOSURE_TIERS = ("CERTAIN", "PROBABLE")  # POSSIBLE is excluded from the exposure total

LEAKAGE_COLUMNS = [
    "confidence", "row_index_a", "row_index_b", "claim_ref_a", "claim_ref_b",
    "insured_name_a", "insured_name_b", "amount_a", "amount_b",
    "matched_fields", "amount_exposure", "detail",
]


def _amount(df: pd.DataFrame, idx) -> float | None:
    """The payment this module cares about is what was actually paid
    (CR0126CM), not the incurred total -- leakage is about money that
    has actually gone out the door twice."""
    paid = df.at[idx, schema.PAID_CODE]
    return float(paid) if pd.notna(paid) else None


def _record(confidence: str, df: pd.DataFrame, a, b, matched_fields: list[str],
            exposure: float, detail: str) -> dict:
    return {
        "confidence": confidence,
        "row_index_a": a,
        "row_index_b": b,
        "claim_ref_a": df.at[a, schema.CLAIM_REF_CODE],
        "claim_ref_b": df.at[b, schema.CLAIM_REF_CODE],
        "insured_name_a": df.at[a, schema.INSURED_NAME_CODE],
        "insured_name_b": df.at[b, schema.INSURED_NAME_CODE],
        "amount_a": _amount(df, a),
        "amount_b": _amount(df, b),
        "matched_fields": matched_fields,
        "amount_exposure": exposure,
        "detail": detail,
    }


def _certain_matches(df: pd.DataFrame) -> tuple[list[dict], set[frozenset]]:
    """Same claim reference appearing more than once -- the same claim
    paid twice. Mirrors dedupe._exact_duplicates but framed around the
    payment amount and an exposure figure."""
    records = []
    seen_pairs: set[frozenset] = set()

    ref = df[schema.CLAIM_REF_CODE]
    has_ref = ref.notna()
    counts = ref[has_ref].value_counts()
    dup_refs = counts[counts > 1].index

    for r in dup_refs:
        idxs = df.index[has_ref & (ref == r)].tolist()
        for a, b in itertools.combinations(idxs, 2):
            amt_a, amt_b = _amount(df, a), _amount(df, b)
            known = [x for x in (amt_a, amt_b) if x is not None]
            exposure = min(known) if known else 0.0
            records.append(_record(
                "CERTAIN", df, a, b, ["claim_reference"], exposure,
                f"claim reference {r!r} appears {len(idxs)} times",
            ))
            seen_pairs.add(frozenset((a, b)))
    return records, seen_pairs


def _probable_and_possible_matches(df: pd.DataFrame, config: dict, seen_pairs: set[frozenset]) -> list[dict]:
    sub = df[
        df[schema.INSURED_NAME_CODE].notna()
        & df[schema.LOSS_DATE_CODE].notna()
        & df[schema.PAID_CODE].notna()
    ]
    if sub.empty:
        return []

    idx_list = sub.index.tolist()
    names = sub[schema.INSURED_NAME_CODE].tolist()
    dates = sub[schema.LOSS_DATE_CODE].tolist()
    refs = sub[schema.CLAIM_REF_CODE].tolist()
    amounts = sub[schema.PAID_CODE].tolist()

    order = sorted(range(len(idx_list)), key=lambda k: dates[k])
    records = []

    for oi in range(len(order)):
        i = order[oi]
        for oj in range(oi + 1, len(order)):
            j = order[oj]
            days_apart = (dates[j] - dates[i]).days
            if days_apart > config["wide_date_window_days"]:
                break

            pair_key = frozenset((idx_list[i], idx_list[j]))
            if pair_key in seen_pairs:
                continue
            if pd.notna(refs[i]) and pd.notna(refs[j]) and refs[i] == refs[j]:
                continue  # same claim ref -> already a CERTAIN match, not a different-payee case

            name_score = fuzz.WRatio(normalize_name(str(names[i])), normalize_name(str(names[j])))
            if name_score < config["name_similarity_threshold"]:
                continue

            amt_i, amt_j = amounts[i], amounts[j]
            if amt_i in (None, 0) or amt_j in (None, 0):
                continue
            amount_diff_pct = abs(amt_i - amt_j) / max(abs(amt_i), abs(amt_j))
            if amount_diff_pct > config["amount_tolerance_pct"]:
                continue

            confidence = "PROBABLE" if days_apart <= config["tight_date_window_days"] else "POSSIBLE"
            exposure = min(amt_i, amt_j)
            seen_pairs.add(pair_key)
            records.append(_record(
                confidence, df, idx_list[i], idx_list[j],
                ["insured_name", "paid_amount", "loss_date"], exposure,
                f"insured names {names[i]!r}/{names[j]!r} are {name_score:.0f}% similar, "
                f"paid amounts {amt_i:.2f}/{amt_j:.2f} are within "
                f"{config['amount_tolerance_pct'] * 100:.0f}% tolerance, "
                f"loss dates are {days_apart} day(s) apart",
            ))
    return records


def find_leakage(df: pd.DataFrame, config: dict | None = None) -> pd.DataFrame:
    """Returns one row per flagged payment-leakage pair, tri-state
    `confidence` in CONFIDENCE_TIERS. Never auto-merges or removes
    rows -- flags for human review only, same discipline as dedupe.py."""
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    certain, seen_pairs = _certain_matches(df)
    probable_possible = _probable_and_possible_matches(df, cfg, seen_pairs)
    records = certain + probable_possible
    return pd.DataFrame(records, columns=LEAKAGE_COLUMNS)


def total_exposure(leakage_df: pd.DataFrame) -> float:
    """Sum of amounts on CERTAIN + PROBABLE flags -- an ESTIMATE requiring
    human confirmation, never a confirmed recovery figure. POSSIBLE-tier
    exposure is intentionally excluded: those matches are too weak to
    responsibly total into a headline number."""
    if leakage_df.empty:
        return 0.0
    scoped = leakage_df[leakage_df["confidence"].isin(EXPOSURE_TIERS)]
    return float(scoped["amount_exposure"].sum())
