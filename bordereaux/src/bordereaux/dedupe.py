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
# Short deliberately: this only needs to separate CLEARLY different names
# (the "100 unrelated repeat clients" case) without risking a same-
# insured pair whose spelling varies later in the string (a transposed
# typo, a suffix difference) landing in different blocks and never being
# compared at all -- recall matters more here than block size, since a
# missed duplicate is a worse failure than a slightly bigger block.
BLOCK_KEY_LENGTH = 2

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


def _block_key(name: str) -> str:
    """A cheap, high-precision bucketing key: the first few characters of
    the normalized name. Fix spec 3.11 / Section 4: unbounded pairwise
    comparison across the whole file is O(n^2) and, at realistic volume
    (thousands of rows with ordinary repeat clients), produces tens of
    thousands of false "probable duplicate" flags purely from comparing
    every row against every other row regardless of name. Grouping by
    this prefix first means the expensive fuzzy comparison only ever
    runs WITHIN a block of already-similar names, never across the whole
    dataset -- standard record-linkage blocking. A prefix (not the full
    normalized name) is used deliberately so a typo *after* the prefix
    still lands in the same block and is still caught by the fuzzy
    compare within it; a typo *within* the prefix itself is the one
    accepted trade-off blocking always makes for tractable performance."""
    return normalize_name(name)[:BLOCK_KEY_LENGTH]


def _normalize_policy_ref(value: str) -> str:
    """Loose enough to tolerate formatting variance ('POL-001-2020' vs
    'pol 001 2020') while still being a precise equality check -- this is
    only ever used to detect a clear MATCH or a clear CONFLICT, never
    fuzzy-scored."""
    return re.sub(r"[^a-z0-9]", "", value.strip().lower())


DUPLICATE_COLUMNS = ["match_type", "row_index_a", "row_index_b", "claim_ref_a", "claim_ref_b", "detail"]

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
_PERIOD_PATTERNS = [
    (re.compile(r"(?<!\d)(20\d{2})[-_/. ]?(0[1-9]|1[0-2])(?!\d)"), lambda m: f"{m.group(1)}-{m.group(2)}"),
    (re.compile(r"(?<![a-z])(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[-_ .']*(20\d{2}|\d{2})(?!\d)"),
     lambda m: f"{m.group(2) if len(m.group(2)) == 4 else '20' + m.group(2)}-{_MONTHS[m.group(1)]:02d}"),
    (re.compile(r"(?<!\d)(20\d{2})[-_ ]?q([1-4])(?!\d)"), lambda m: f"{m.group(1)}-Q{m.group(2)}"),
    (re.compile(r"(?<![a-z])q([1-4])[-_ ]?(20\d{2})(?!\d)"), lambda m: f"{m.group(2)}-Q{m.group(1)}"),
]


def period_from_text(text: object) -> str | None:
    """'2024-03', 'Mar 2024', 'March-24', '202403', '2024 Q1' -> a normalised
    period key. Returns None rather than guessing when nothing explicit is
    present -- a reporting period is never assumed (forensic F1)."""
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return None
    if hasattr(text, "year") and hasattr(text, "month"):
        return f"{text.year}-{text.month:02d}"
    s = str(text).strip().lower()
    for pat, fmt in _PERIOD_PATTERNS:
        m = pat.search(s)
        if m:
            return fmt(m)
    return None


def row_periods(df: pd.DataFrame) -> pd.Series:
    """Reporting period per row: the mapped period column if it parses,
    else an explicit period in the source sheet's NAME (e.g. tab "2024-03"),
    else None (unknown)."""
    idx = df.index
    from_col = (df[schema.PERIOD_CODE].map(period_from_text) if schema.PERIOD_CODE in df.columns
                else pd.Series(None, index=idx, dtype="object"))
    if schema.SOURCE_SHEET_CODE in df.columns:
        sheet_period = {n: period_from_text(n) for n in df[schema.SOURCE_SHEET_CODE].dropna().unique()}
        from_sheet = df[schema.SOURCE_SHEET_CODE].map(sheet_period)
    else:
        from_sheet = pd.Series(None, index=idx, dtype="object")
    return from_col.where(from_col.notna(), from_sheet)


def find_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    records: list[dict] = []
    records.extend(_exact_duplicates(df))
    records.extend(_probable_duplicates(df))
    return pd.DataFrame(records, columns=DUPLICATE_COLUMNS)


def _exact_duplicates(df: pd.DataFrame) -> list[dict]:
    """Same claim reference reported more than once *for the same reporting
    period*. Forensic F1: a claim appearing on 12 monthly tabs is 12
    period movements, not 66 duplicate pairs -- the old check graded a
    correct multi-period workbook 2/5 with a 100% duplicate rate.

    - same ref, same known period            -> exact_duplicate
    - same ref, different known periods      -> not a duplicate (movement)
    - same ref, period unknown, same sheet   -> exact_duplicate
    - same ref, period unknown, other sheets -> repeat_period_unknown (review:
      could be a duplicate or a later period -- we do not guess)
    Each cluster is linked to its first occurrence (k-1 links, not k^2 pairs)."""
    ref = df[schema.CLAIM_REF_CODE]
    has_ref = ref.notna()
    if not has_ref.any():
        return []
    counts = ref[has_ref].value_counts()
    dup_refs = set(counts[counts > 1].index)
    if not dup_refs:
        return []
    periods = row_periods(df)
    sheets = df[schema.SOURCE_SHEET_CODE] if schema.SOURCE_SHEET_CODE in df.columns else pd.Series(None, index=df.index)
    sub = df.index[has_ref & ref.isin(dup_refs)]
    records = []
    groups: dict[tuple, list] = {}
    for i in sub:
        p = periods.at[i]
        key = (ref.at[i], ("P", p) if p is not None else ("S", sheets.at[i]))
        groups.setdefault(key, []).append(i)
    for (r, (kind, k)), idxs in groups.items():
        if len(idxs) < 2:
            continue
        first = idxs[0]
        basis = f"reporting period {k}" if kind == "P" else f"sheet {k!r} (no reporting period present)"
        for b in idxs[1:]:
            records.append({"match_type": "exact_duplicate", "row_index_a": first, "row_index_b": b,
                            "claim_ref_a": r, "claim_ref_b": r,
                            "detail": f"claim reference {r!r} appears {len(idxs)} times in the same {basis}"})
    # Unknown-period repeats across different sheets: review, not certain.
    unknown = [i for i in sub if periods.at[i] is None]
    by_ref: dict = {}
    for i in unknown:
        by_ref.setdefault(ref.at[i], []).append(i)
    for r, idxs in by_ref.items():
        sheet_first: dict = {}
        for i in idxs:
            sheet_first.setdefault(sheets.at[i], i)
        firsts = list(sheet_first.values())
        if len(firsts) < 2:
            continue
        for b in firsts[1:]:
            records.append({"match_type": "repeat_period_unknown", "row_index_a": firsts[0], "row_index_b": b,
                            "claim_ref_a": r, "claim_ref_b": r,
                            "detail": f"claim reference {r!r} appears on sheets {sheets.at[firsts[0]]!r} and "
                                      f"{sheets.at[b]!r} and no reporting period is present: either a duplicate "
                                      "or a later period's movement -- confirm"})
    return records


def _probable_duplicates(df: pd.DataFrame) -> list[dict]:
    sub = df[df[schema.INSURED_NAME_CODE].notna() & df[schema.LOSS_DATE_CODE].notna()]
    if sub.empty:
        return []

    block_keys = sub[schema.INSURED_NAME_CODE].astype(str).map(_block_key)
    have_policy = schema.POLICY_REF_CODE in sub.columns

    records: list[dict] = []
    seen_pairs: set[tuple] = set()
    for _, block_index in sub.groupby(block_keys, sort=False).groups.items():
        if len(block_index) < 2:
            continue
        block = sub.loc[block_index]
        records.extend(_compare_block(block, seen_pairs, have_policy))
    return records


HIGH_FREQUENCY_REPEAT_THRESHOLD = 5  # see _compare_block: this many exact-name repeats in one sheet reads as a repeat client, not an isolated near-duplicate pair


def _compare_block(block: pd.DataFrame, seen_pairs: set[tuple], have_policy: bool) -> list[dict]:
    """Pairwise comparison within one name-block only (see _block_key) --
    never across the whole file. Still bounded further by the existing
    date-adjacency window.

    Policy reference is used as a distinguishing signal, but narrowly:
    excluding a same-name pair just because its two policy references
    differ would also exclude a genuine duplicate that happens to have a
    typo'd/re-keyed policy field -- an existing, deliberately-designed
    regression fixture (bordereaux/tests/test_boundary_fixture.py, fix
    spec D7) plants exactly that shape (two rows, same sheet, same name,
    one day apart, DIFFERENT policy refs) as a genuine duplicate, and
    breaking that already-verified behavior to satisfy a new, less
    certain heuristic would be a regression, not a fix. What actually
    distinguishes "ordinary repeat business" (per the brief: a client
    that appears ~20 times) from an isolated duplicate pair (a name that
    appears exactly twice, planted as a defect) is REPETITION COUNT, not
    policy reference alone -- so the policy-conflict exclusion only
    applies once a name has shown up often enough in this sheet to look
    like a genuine repeat client, never for a rare/isolated pair."""
    idx = block.index.tolist()
    names = block[schema.INSURED_NAME_CODE].tolist()
    dates = block[schema.LOSS_DATE_CODE].tolist()
    refs = block[schema.CLAIM_REF_CODE].tolist()
    policy_refs = block[schema.POLICY_REF_CODE].tolist() if have_policy else [None] * len(block)
    sheets = (block[schema.SOURCE_SHEET_CODE].tolist() if schema.SOURCE_SHEET_CODE in block.columns
              else [None] * len(block))

    norm_names = [normalize_name(str(n)) for n in names]
    name_counts_by_sheet: dict[tuple, int] = {}
    for n, s in zip(norm_names, sheets):
        key = (n, s)
        name_counts_by_sheet[key] = name_counts_by_sheet.get(key, 0) + 1

    order = sorted(range(len(idx)), key=lambda k: dates[k])
    records = []

    for oi in range(len(order)):
        i = order[oi]
        for oj in range(oi + 1, len(order)):
            j = order[oj]
            if (dates[j] - dates[i]).days > ADJACENT_DAYS:
                break
            if pd.notna(refs[i]) and pd.notna(refs[j]) and refs[i] == refs[j]:
                continue  # same claim, already covered by exact-duplicate check

            same_sheet = sheets[i] is not None and sheets[i] == sheets[j]
            policy_i, policy_j = policy_refs[i], policy_refs[j]
            both_policies_known = pd.notna(policy_i) and pd.notna(policy_j)
            policies_match = both_policies_known and (
                _normalize_policy_ref(str(policy_i)) == _normalize_policy_ref(str(policy_j))
            )
            is_repeat_client = name_counts_by_sheet.get((norm_names[i], sheets[i]), 0) > HIGH_FREQUENCY_REPEAT_THRESHOLD
            if same_sheet and both_policies_known and not policies_match and is_repeat_client:
                continue  # a name repeated often enough to read as a genuine repeat client, with a different known policy each time -- ordinary business, not a duplicate

            score = fuzz.WRatio(norm_names[i], norm_names[j], score_cutoff=NAME_SIMILARITY_THRESHOLD)
            if not score:
                continue
            pair_key = tuple(sorted((idx[i], idx[j])))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            policy_note = (
                "; policy references match" if policies_match
                else "; policy reference not available on one or both rows"
            )
            records.append({
                "match_type": "probable_duplicate",
                "row_index_a": idx[i],
                "row_index_b": idx[j],
                "claim_ref_a": refs[i],
                "claim_ref_b": refs[j],
                "detail": (
                    f"insured names {names[i]!r} / {names[j]!r} are {score:.0f}% similar, "
                    f"loss dates {dates[i].date()} / {dates[j].date()} are within "
                    f"{ADJACENT_DAYS} days, and claim references differ{policy_note}"
                ),
            })
    return records
