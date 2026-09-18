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
# Fix spec 4.2: when the same-sheet policy reference clearly differs
# (this is "same client, renewed under a new policy" territory), a name
# match alone is a weaker signal -- require a near-exact name match
# instead of the base threshold before still flagging it.
NAME_SIMILARITY_THRESHOLD_STRICT = 95.0
POLICY_REF_SIMILARITY_THRESHOLD = 90.0
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


def _name_block_key(name: str) -> str:
    """Fix spec 4.1: the cheap, high-precision blocking key candidates
    are compared within. Just the first normalized character (not first
    N, N>1) -- deliberately coarse. A longer prefix (e.g. first 3-4 chars)
    buckets far more tightly and is the textbook choice, but it also
    splits a genuine same-claim-entered-twice pair the moment a typo
    lands in the first few characters (confirmed against this project's
    own boundary fixture: "Anbsoro LLC" vs "Ansboro LLC", a transposed
    3rd/4th letter, would land in different buckets under a first-4-char
    key and be missed entirely -- silently losing recall on exactly the
    case this check exists to catch). First-character-only still turns
    an unbounded/near-unbounded comparison into ~26+ buckets, which is
    what actually matters for the runaway-comparison-count failure mode
    (many rows sharing a close date): it bounds the within-date-window
    fan-out by name bucket instead of comparing every same-date row
    against every other regardless of name."""
    normalized = normalize_name(name)
    return normalized[:1] if normalized else ""


def _policy_ref_signal(sheet_a: object, sheet_b: object, ref_a: object, ref_b: object) -> str:
    """"match" / "differ" / "unknown". Fix spec 4.2: only compared when
    both rows come from the SAME sheet -- different senders routinely use
    their own policy-numbering scheme even when reporting the exact same
    underlying claim (confirmed against this project's own boundary
    fixture: several genuine cross-sheet duplicate pairs have no
    relationship between their policy references at all), so a cross-
    sheet mismatch carries no information and must never suppress or
    down-weight a match. Within one sheet, though, two rows for the same
    client under two genuinely different policy numbers is real evidence
    of "renewed", not "entered twice"."""
    if sheet_a != sheet_b:
        return "unknown"
    if pd.isna(ref_a) or pd.isna(ref_b):
        return "unknown"
    sim = fuzz.ratio(str(ref_a).strip().lower(), str(ref_b).strip().lower())
    return "match" if sim >= POLICY_REF_SIMILARITY_THRESHOLD else "differ"


def _scan_bucket(idx: list, names: list, dates: list, refs: list, sheets: list, policy_refs: list) -> list[dict]:
    """The expensive fuzzy-name comparison, run only within one blocking
    bucket (same first-letter name key) and only across rows already
    known to be date-adjacent (fix spec 4.1's "never across the whole
    dataset" -- this used to run for every date-adjacent pair regardless
    of name; blocking by name first narrows that fan-out further)."""
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
            policy_signal = _policy_ref_signal(sheets[i], sheets[j], policy_refs[i], policy_refs[j])
            # Fix spec 4.2: "same client renewed" (same sheet, clearly
            # different policy ref) needs a much closer name match than
            # the ordinary "probably the same claim" bar before it's
            # still worth a human's time.
            threshold = NAME_SIMILARITY_THRESHOLD_STRICT if policy_signal == "differ" else NAME_SIMILARITY_THRESHOLD
            if score < threshold:
                continue

            pair_key = tuple(sorted((idx[i], idx[j])))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)
            policy_note = {
                "match": "policy references match, ",
                "differ": "despite differing policy references (weaker signal; likely repeat business), ",
                "unknown": "",
            }[policy_signal]
            records.append({
                "match_type": "probable_duplicate",
                "row_index_a": idx[i],
                "row_index_b": idx[j],
                "claim_ref_a": refs[i],
                "claim_ref_b": refs[j],
                "detail": (
                    f"insured names {names[i]!r} / {names[j]!r} are {score:.0f}% similar, "
                    f"loss dates {dates[i].date()} / {dates[j].date()} are within "
                    f"{ADJACENT_DAYS} days, {policy_note}and claim references differ"
                ),
            })
    return records


def _probable_duplicates(df: pd.DataFrame) -> list[dict]:
    sub = df[df[schema.INSURED_NAME_CODE].notna() & df[schema.LOSS_DATE_CODE].notna()]
    if sub.empty:
        return []

    sub = sub.copy()
    sub["_name_block"] = sub[schema.INSURED_NAME_CODE].map(lambda n: _name_block_key(str(n)))

    records = []
    for _, bucket in sub.groupby("_name_block", sort=False):
        records.extend(_scan_bucket(
            bucket.index.tolist(),
            bucket[schema.INSURED_NAME_CODE].tolist(),
            bucket[schema.LOSS_DATE_CODE].tolist(),
            bucket[schema.CLAIM_REF_CODE].tolist(),
            bucket[schema.SOURCE_SHEET_CODE].tolist() if schema.SOURCE_SHEET_CODE in bucket.columns
            else [None] * len(bucket),
            bucket[schema.POLICY_REF_CODE].tolist() if schema.POLICY_REF_CODE in bucket.columns
            else [None] * len(bucket),
        ))
    return records
