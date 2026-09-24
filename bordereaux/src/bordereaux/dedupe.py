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
    """True duplicates only (exact resubmissions, period-unknown repeats for
    review, probable near-duplicates). Claim DEVELOPMENT -- the same claim
    reported again with a later period or moved amounts -- is never a
    duplicate; see find_developments()."""
    records: list[dict] = [r for r in _reference_repeats(df) if r["match_type"] != "development"]
    records.extend(_probable_duplicates(df))
    return pd.DataFrame(records, columns=DUPLICATE_COLUMNS)


def find_developments(df: pd.DataFrame) -> pd.DataFrame:
    """Same claim reference reported again with a different reporting period
    or different amounts/status: normal development of a live claim,
    reported for information, never flagged as a defect."""
    return pd.DataFrame([r for r in _reference_repeats(df) if r["match_type"] == "development"],
                        columns=DUPLICATE_COLUMNS)


def _value_signature(df: pd.DataFrame) -> pd.Series:
    """What must be identical for a repeat to be a resubmission: every
    monetary field plus status (amounts rounded to the cent)."""
    codes = [c for c in (*schema.MONETARY_CODES, schema.STATUS_CODE) if c in df.columns]
    parts = []
    for c in codes:
        col = df[c]
        if c in schema.MONETARY_CODES:
            col = pd.to_numeric(col, errors="coerce").round(2)
        parts.append(col.astype("object").where(col.notna(), None))
    if not parts:
        return pd.Series([()] * len(df), index=df.index, dtype="object")
    return pd.Series(list(zip(*[p.tolist() for p in parts])), index=df.index, dtype="object")


def _reference_repeats(df: pd.DataFrame) -> list[dict]:
    """Classify every repeat of a claim reference (forensic F1 + user
    regression StressTest_450: development pairs were reported as duplicates).

    Key = (claim reference, reporting period) where the period is the mapped
    period column, else a period in the sheet name, else unknown.
    - same ref, same known period, identical values  -> exact_duplicate
    - same ref, same known period, different values  -> development (restated)
    - same ref, different known periods               -> development
    - period unknown, same sheet, identical values    -> exact_duplicate
    - period unknown, same sheet, different values    -> development (restated)
    - period unknown, different sheets, identical     -> repeat_period_unknown (review)
    - period unknown, different sheets, different     -> development
    Each cluster links to its first occurrence (k-1 links, not k^2 pairs)."""
    ref = df[schema.CLAIM_REF_CODE]
    has_ref = ref.notna()
    if not has_ref.any():
        return []
    counts = ref[has_ref].value_counts()
    dup_refs = set(counts[counts > 1].index)
    if not dup_refs:
        return []
    sub = df.index[has_ref & ref.isin(dup_refs)]
    periods = row_periods(df)
    sheets = df[schema.SOURCE_SHEET_CODE] if schema.SOURCE_SHEET_CODE in df.columns else pd.Series(None, index=df.index)
    sig = _value_signature(df.loc[sub])
    records: list[dict] = []

    def link(kind, a, b, r, detail):
        records.append({"match_type": kind, "row_index_a": a, "row_index_b": b, "claim_ref_a": r, "claim_ref_b": r,
                        "detail": detail})

    by_ref: dict = {}
    for i in sub:
        by_ref.setdefault(ref.at[i], []).append(i)
    for r, idxs in by_ref.items():
        # 1) within one period (or one sheet when the period is unknown)
        slots: dict = {}
        for i in idxs:
            p = periods.at[i]
            slots.setdefault(("P", p) if p is not None else ("S", sheets.at[i]), []).append(i)
        slot_heads = []
        for (kind, k), members in slots.items():
            basis = f"reporting period {k}" if kind == "P" else f"sheet {k!r} (no reporting period present)"
            by_sig: dict = {}
            for i in members:
                by_sig.setdefault(sig.at[i], []).append(i)
            heads = []
            for same in by_sig.values():
                heads.append(same[0])
                for b in same[1:]:
                    link("exact_duplicate", same[0], b, r,
                         f"claim reference {r!r} is repeated with identical amounts and status in the same {basis}")
            for b in heads[1:]:
                link("development", heads[0], b, r,
                     f"claim reference {r!r} appears twice in the same {basis} with different amounts or status "
                     "(a restatement or correction) -- not treated as a duplicate")
            slot_heads.append(((kind, k), members[0]))
        # 2) across periods / sheets
        known = [(k, i) for (kind, k), i in slot_heads if kind == "P"]
        for (k, b) in known[1:]:
            link("development", known[0][1], b, r,
                 f"claim reference {r!r} reported for period {known[0][0]} and again for period {k}: "
                 "claim development, not a duplicate")
        unknown = [i for (kind, _), i in slot_heads if kind == "S"]
        for b in unknown[1:]:
            a = unknown[0]
            if sig.at[a] == sig.at[b]:
                link("repeat_period_unknown", a, b, r,
                     f"claim reference {r!r} appears on sheets {sheets.at[a]!r} and {sheets.at[b]!r} with identical "
                     "amounts and no reporting period: either a duplicate or an unchanged later period -- confirm")
            else:
                link("development", a, b, r,
                     f"claim reference {r!r} appears on sheets {sheets.at[a]!r} and {sheets.at[b]!r} with different "
                     "amounts: claim development, not a duplicate")
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
