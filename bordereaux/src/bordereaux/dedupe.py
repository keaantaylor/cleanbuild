"""Phase 4 (+ fix spec 3.8): duplicate detection.

Exact match: the same claim reference appearing more than once, anywhere
in the workbook (any sheet) -> certain duplicate. Fuzzy match: similar
insured name + same-or-adjacent loss date + no matching claim reference
-> probable duplicate, likewise checked across the whole combined
DataFrame regardless of which sheet each row came from. Both are flags
for human review only -- nothing here merges or drops rows.

Name similarity is scored on a *normalized* form (case-folded, "&"/"and"
unified, legal-suffix variants collapsed) rather than the raw string.
`fuzz.WRatio` does NOT case-fold by default in this rapidfuzz version --
"Fairwind Shipping Group" vs "FAIRWIND SHIPPING GROUP" scores ~22, not
~100 -- so comparing raw strings silently missed exactly this class of
near-duplicate (fix spec D7). Normalizing first fixes it.
"""

from __future__ import annotations

import itertools
import re

import pandas as pd
from rapidfuzz import fuzz

from . import schema

NAME_SIMILARITY_THRESHOLD = 88.0
ADJACENT_DAYS = 3

_LEGAL_SUFFIXES = {
    "ltd": "ltd", "limited": "ltd",
    "inc": "inc", "incorporated": "inc",
    "corp": "corp", "corporation": "corp",
    "co": "co", "company": "co",
    "plc": "plc",
}


def normalize_name(name: str) -> str:
    """Case-fold and collapse the punctuation/legal-suffix variants that
    show up across senders describing the same insured."""
    text = name.strip().lower().replace("&", " and ")
    text = re.sub(r"[.,]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    tokens = text.split(" ")
    if tokens and tokens[-1] in _LEGAL_SUFFIXES:
        tokens[-1] = _LEGAL_SUFFIXES[tokens[-1]]
    return " ".join(tokens)

DUPLICATE_COLUMNS = ["match_type", "row_index_a", "row_index_b", "claim_ref_a", "claim_ref_b", "detail"]


def find_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    records: list[dict] = []
    records.extend(_exact_duplicates(df))
    records.extend(_probable_duplicates(df))
    return pd.DataFrame(records, columns=DUPLICATE_COLUMNS)


def _exact_duplicates(df: pd.DataFrame) -> list[dict]:
    ref = df[schema.CLAIM_REF_CODE]
    has_ref = ref.notna()
    counts = ref[has_ref].value_counts()
    dup_refs = counts[counts > 1].index

    records = []
    for r in dup_refs:
        idxs = df.index[has_ref & (ref == r)].tolist()
        for a, b in itertools.combinations(idxs, 2):
            records.append({
                "match_type": "exact_duplicate",
                "row_index_a": a,
                "row_index_b": b,
                "claim_ref_a": r,
                "claim_ref_b": r,
                "detail": f"claim reference {r!r} appears {len(idxs)} times",
            })
    return records


def _probable_duplicates(df: pd.DataFrame) -> list[dict]:
    sub = df[df[schema.INSURED_NAME_CODE].notna() & df[schema.LOSS_DATE_CODE].notna()]
    if sub.empty:
        return []

    idx = sub.index.tolist()
    names = sub[schema.INSURED_NAME_CODE].tolist()
    dates = sub[schema.LOSS_DATE_CODE].tolist()
    refs = sub[schema.CLAIM_REF_CODE].tolist()

    order = sorted(range(len(idx)), key=lambda k: dates[k])
    records = []
    seen_pairs: set[tuple] = set()

    for oi in range(len(order)):
        i = order[oi]
        for oj in range(oi + 1, len(order)):
            j = order[oj]
            if (dates[j] - dates[i]).days > ADJACENT_DAYS:
                break
            if pd.notna(refs[i]) and pd.notna(refs[j]) and refs[i] == refs[j]:
                continue  # same claim, already covered by exact-duplicate check

            score = fuzz.WRatio(normalize_name(str(names[i])), normalize_name(str(names[j])))
            if score >= NAME_SIMILARITY_THRESHOLD:
                pair_key = tuple(sorted((idx[i], idx[j])))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                records.append({
                    "match_type": "probable_duplicate",
                    "row_index_a": idx[i],
                    "row_index_b": idx[j],
                    "claim_ref_a": refs[i],
                    "claim_ref_b": refs[j],
                    "detail": (
                        f"insured names {names[i]!r} / {names[j]!r} are {score:.0f}% similar, "
                        f"loss dates {dates[i].date()} / {dates[j].date()} are within "
                        f"{ADJACENT_DAYS} days, and claim references differ"
                    ),
                })
    return records
