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

import re
from dataclasses import dataclass

import numpy as np
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
# Work budget for the probable-duplicate check: row pairs that share a name
# block and a loss-date window, i.e. pairs the fuzzy comparison would visit.
# Realistic bordereaux stay far below it (tens of thousands of pairs for 50k
# rows); a file where every name shares a prefix and every loss date falls
# in one month can need ~10^8. Above the budget the check is not run and is
# reported as NOT ASSESSED in coverage -- never as "no probable duplicates".
MAX_PROBABLE_CANDIDATE_PAIRS = 2_000_000

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


DUPLICATE_COLUMNS = ["match_type", "row_index_a", "row_index_b", "claim_ref_a", "claim_ref_b", "detail", "confidence"]

# Probable duplicates need corroboration (stress-test finding: name + loss date
# alone flagged ~1,400 pairs on 2,000 rows, ~2.5% real). A candidate pair (same
# name block, loss dates within ADJACENT_DAYS, similar names, different claim
# references) is scored 0-100 from independent evidence and reported only at or
# above PROBABLE_MIN_CONFIDENCE AND with at least one corroborating signal:
# matching policy reference, near-identical amounts in the same currency, or a
# near-identical claim reference (a transposed or mistyped digit).
PROBABLE_MIN_CONFIDENCE = 60
_BASE = 25                      # similar name + loss dates within the window
_EXACT_NAME = 10                # names identical once normalised
_SAME_DAY, _NEXT_DAY = 10, 5    # loss dates equal / one day apart
_POLICY_MATCH, _POLICY_DIFFER = 35, -10
_AMOUNT_SAME, _AMOUNT_CLOSE, _AMOUNT_FAR = 35, 20, -20   # within 0.5% / within 5% / further apart
_REF_NEAR = 35                  # claim references one edit or one transposition apart

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


@dataclass(frozen=True)
class ProbableCheck:
    """Whether the probable-duplicate check ran, and why not if it did not."""
    assessed: bool
    candidate_pairs: int
    reason: str | None = None


def find_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """True duplicates only (exact resubmissions, period-unknown repeats for
    review, probable near-duplicates). Claim DEVELOPMENT -- the same claim
    reported again with a later period or moved amounts -- is never a
    duplicate; see find_developments(). Callers that report coverage use
    find_duplicates_assessed() to learn whether the probable check ran."""
    return find_duplicates_assessed(df)[0]


def find_duplicates_assessed(df: pd.DataFrame) -> tuple[pd.DataFrame, ProbableCheck]:
    records: list[dict] = [r for r in _reference_repeats(df) if r["match_type"] != "development"]
    pairs = probable_candidate_pairs(df)
    if pairs > MAX_PROBABLE_CANDIDATE_PAIRS:
        check = ProbableCheck(False, pairs, (
            f"{pairs:,} candidate row pairs (similar insured names with loss dates within {ADJACENT_DAYS} days) "
            f"exceed the limit of {MAX_PROBABLE_CANDIDATE_PAIRS:,}; exact duplicates were still checked"))
    else:
        records.extend(_probable_duplicates(df))
        check = ProbableCheck(True, pairs)
    return pd.DataFrame(records, columns=DUPLICATE_COLUMNS), check


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
                        "detail": detail, "confidence": 100 if kind == "exact_duplicate" else None})

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


def _probable_blocks(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    sub = df[df[schema.INSURED_NAME_CODE].notna() & df[schema.LOSS_DATE_CODE].notna()]
    if sub.empty:
        return sub, {}
    block_keys = sub[schema.INSURED_NAME_CODE].astype(str).map(_block_key)
    return sub, sub.groupby(block_keys, sort=False).groups


def probable_candidate_pairs(df: pd.DataFrame) -> int:
    """How many row pairs _compare_block would visit: pairs in the same name
    block whose loss dates are within ADJACENT_DAYS whole days of each other
    ((later - earlier).days <= ADJACENT_DAYS, i.e. less than ADJACENT_DAYS+1
    days apart). Vectorised per block, so it is cheap even when the answer
    is huge."""
    sub, groups = _probable_blocks(df)
    window = np.int64((ADJACENT_DAYS + 1) * 86_400 * 10**9)
    total = 0
    for block_index in groups.values():
        if len(block_index) < 2:
            continue
        loss = pd.DatetimeIndex(sub.loc[block_index, schema.LOSS_DATE_CODE]).as_unit("ns")
        ns = np.sort(loss.astype("int64").to_numpy())
        ends = np.searchsorted(ns, ns + window, side="left")
        total += int((ends - np.arange(len(ns)) - 1).sum())
    return total


def _probable_duplicates(df: pd.DataFrame) -> list[dict]:
    sub, groups = _probable_blocks(df)
    if sub.empty:
        return []
    have_policy = schema.POLICY_REF_CODE in sub.columns

    records: list[dict] = []
    seen_pairs: set[tuple] = set()
    for block_index in groups.values():
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
    norm_policies = [_normalize_policy_ref(str(p)) if pd.notna(p) else None for p in policy_refs]
    name_counts_by_sheet: dict[tuple, int] = {}
    for n, s in zip(norm_names, sheets):
        key = (n, s)
        name_counts_by_sheet[key] = name_counts_by_sheet.get(key, 0) + 1

    order = sorted(range(len(idx)), key=lambda k: dates[k])
    records = []
    scores: dict[tuple[str, str], float] = {}  # repeat clients recur: score each name pair once
    amounts = _pair_amounts(block)
    currencies = (block[schema.CURRENCY_CODE].tolist() if schema.CURRENCY_CODE in block.columns
                  else [None] * len(block))
    norm_refs = [_normalize_policy_ref(str(r)).upper() if pd.notna(r) else None for r in refs]

    for oi in range(len(order)):
        i = order[oi]
        for oj in range(oi + 1, len(order)):
            j = order[oj]
            gap = (dates[j] - dates[i]).days
            if gap > ADJACENT_DAYS:
                break
            if pd.notna(refs[i]) and pd.notna(refs[j]) and refs[i] == refs[j]:
                continue  # same claim, already covered by exact-duplicate check
            ci, cj = currencies[i], currencies[j]
            if pd.notna(ci) and pd.notna(cj) and ci != cj:
                continue  # different settlement currencies: not the same payment

            same_sheet = sheets[i] is not None and sheets[i] == sheets[j]
            both_policies_known = norm_policies[i] is not None and norm_policies[j] is not None
            policies_match = both_policies_known and norm_policies[i] == norm_policies[j]
            is_repeat_client = name_counts_by_sheet.get((norm_names[i], sheets[i]), 0) > HIGH_FREQUENCY_REPEAT_THRESHOLD
            if same_sheet and both_policies_known and not policies_match and is_repeat_client:
                continue  # a repeat client with a different known policy each time: ordinary business

            name_pair = (norm_names[i], norm_names[j])
            score = scores.get(name_pair)
            if score is None:
                score = scores[name_pair] = fuzz.WRatio(*name_pair, score_cutoff=NAME_SIMILARITY_THRESHOLD)
            if not score:
                continue

            evidence: list[str] = []
            conf = _BASE
            corroborated = False
            if norm_names[i] == norm_names[j]:
                conf += _EXACT_NAME
            conf += _SAME_DAY if gap == 0 else _NEXT_DAY if gap == 1 else 0
            if policies_match:
                conf += _POLICY_MATCH
                corroborated = True
                evidence.append("policy references match")
            elif both_policies_known:
                conf += _POLICY_DIFFER
                evidence.append("policy references differ")
            a_amt, b_amt = amounts[i], amounts[j]
            if a_amt is not None and b_amt is not None:
                denom = max(abs(a_amt), abs(b_amt), 1.0)
                rel = abs(a_amt - b_amt) / denom
                if rel <= 0.005:
                    conf += _AMOUNT_SAME
                    corroborated = True
                    evidence.append("amounts are the same")
                elif rel <= 0.05:
                    conf += _AMOUNT_CLOSE
                    corroborated = True
                    evidence.append(f"amounts within {rel:.1%}")
                else:
                    conf += _AMOUNT_FAR
                    evidence.append("amounts differ")
            if norm_refs[i] and norm_refs[j] and _refs_near(norm_refs[i], norm_refs[j]):
                conf += _REF_NEAR
                corroborated = True
                evidence.append("claim references differ by one character or a transposition")
            conf = max(0, min(100, conf))
            if not corroborated or conf < PROBABLE_MIN_CONFIDENCE:
                continue

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
                "confidence": int(conf),
                "detail": (
                    f"{int(conf)}% confidence: insured names {names[i]!r} / {names[j]!r} are {score:.0f}% similar, "
                    f"loss dates {dates[i].date()} / {dates[j].date()} are {gap} day{'s' if gap != 1 else ''} apart, "
                    f"claim references differ; " + "; ".join(evidence)
                ),
            })
    return records


def _pair_amounts(block: pd.DataFrame) -> list[float | None]:
    """The figure compared between two candidate rows: total incurred, else
    paid to date + reserve, else None (no amount evidence either way)."""
    def col(code):
        return (pd.to_numeric(block[code], errors="coerce").tolist() if code in block.columns
                else [float("nan")] * len(block))
    inc, paid, res = col(schema.INCURRED_CODE), col(schema.PAID_TD_CODE), col(schema.RESERVE_CODE)
    out: list[float | None] = []
    for a, p, r in zip(inc, paid, res):
        if pd.notna(a):
            out.append(float(a))
        elif pd.notna(p) or pd.notna(r):
            out.append(float(p if pd.notna(p) else 0) + float(r if pd.notna(r) else 0))
        else:
            out.append(None)
    return out


def _refs_near(a: str, b: str) -> bool:
    """One substitution, insertion, deletion or adjacent transposition apart
    (CLM-100123 vs CLM-100132), on references of a realistic length."""
    if a == b or min(len(a), len(b)) < 5:
        return False
    from rapidfuzz.distance import DamerauLevenshtein

    return DamerauLevenshtein.distance(a, b) <= 1
