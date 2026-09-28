"""P5 Sanctions screening: insured names against the organisation's lists.

A match is never a verdict: every hit is REVIEW for a person to decide.
- exact match after normalisation (accents, case, punctuation, legal-form
  suffixes such as Ltd / GmbH, word order) -> REVIEW, CRITICAL;
- close match (token-sort similarity >= threshold, default 90) -> REVIEW, HIGH.
Rows with a blank name, an unmapped name column or no list loaded are
NOT_ASSESSED -- never reported as clear.
Candidates are found through a word index, so a 50k-row bordereau against
a list of tens of thousands of names is compared only where names share a
word.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from rapidfuzz import fuzz

from .base import CheckInput, FindingDraft, ModuleResult, RuleCoverage, field_label, finish, not_assessed

NAME = "CR0035M"
DEFAULT_THRESHOLD = 90
MAX_MATCHES_PER_ROW = 3
_LEGAL = frozenset(
    {
        "ltd",
        "limited",
        "llc",
        "llp",
        "plc",
        "inc",
        "incorporated",
        "co",
        "corp",
        "corporation",
        "company",
        "gmbh",
        "ag",
        "sa",
        "sas",
        "sarl",
        "srl",
        "spa",
        "bv",
        "nv",
        "oy",
        "ab",
        "as",
        "aps",
        "kft",
        "sro",
        "doo",
        "ooo",
        "pte",
        "pty",
        "lp",
    }
)
_NON_WORD = re.compile(r"[^\w]+")


def normalise(name: str | None) -> str:
    """Comparable form: no accents, lower case, no punctuation, no legal-form
    words, words sorted. 'Müller & Co. GmbH' and 'MULLER CO' compare equal."""
    if not name:
        return ""
    text = unicodedata.normalize("NFKD", name)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    words = [w for w in _NON_WORD.sub(" ", text).replace("_", " ").split() if w not in _LEGAL]
    return " ".join(sorted(words))


@dataclass(frozen=True)
class Entry:
    entity_id: str
    name: str
    list_name: str
    kind: str = "unknown"


class Index:
    def __init__(self, entries: list[Entry]) -> None:
        self.by_norm: dict[str, list[Entry]] = defaultdict(list)
        self.by_word: dict[str, set[str]] = defaultdict(set)
        for e in entries:
            n = normalise(e.name)
            if not n:
                continue
            self.by_norm[n].append(e)
            for w in n.split():
                if len(w) >= 3:
                    self.by_word[w].add(n)

    def search(self, name: str, threshold: int) -> list[tuple[str, int, Entry]]:
        """(kind, score, entry) best first; kind is 'exact' or 'close'."""
        n = normalise(name)
        if not n:
            return []
        out: list[tuple[str, int, Entry]] = [("exact", 100, e) for e in self.by_norm.get(n, [])]
        candidates: set[str] = set()
        for w in n.split():
            candidates |= self.by_word.get(w, set())
        candidates.discard(n)
        for c in candidates:
            score = round(fuzz.token_sort_ratio(n, c))
            if score >= threshold:
                out.extend(("close", score, e) for e in self.by_norm[c])
        out.sort(key=lambda x: (-x[1], x[2].name))
        seen: set[tuple[str, str]] = set()
        best: list[tuple[str, int, Entry]] = []
        for kind, score, e in out:
            if (e.list_name, e.entity_id) not in seen:
                seen.add((e.list_name, e.entity_id))
                best.append((kind, score, e))
        return best[:MAX_MATCHES_PER_ROW]


def run(inp: CheckInput) -> ModuleResult:
    rule = RuleCoverage("SAN_NAME_MATCH", "Insured name screened against sanctions lists")
    lists: list[dict[str, Any]] = inp.config.get("lists") or []
    if not lists:
        return not_assessed("No sanctions list is loaded, so no name was screened. Load one under Settings.", [rule])
    threshold = int(inp.config.get("threshold") or DEFAULT_THRESHOLD)
    index: Index = inp.context["sanctions_index"]
    findings: list[FindingDraft] = []
    cache: dict[str, list[tuple[str, int, Entry]]] = {}
    for row in inp.rows:
        sheet = inp.sheets[row.sheet_name]
        if NAME not in sheet.mapped:
            rule.skip(1, f"{field_label(NAME)} is not mapped on sheet '{sheet.name}'")
            continue
        if not (row.insured_name or "").strip():
            rule.skip(1, "insured name is blank")
            continue
        rule.assessed += 1
        name = row.insured_name or ""
        hits = cache.get(name)
        if hits is None:
            hits = cache[name] = index.search(name, threshold)
        for kind, score, e in hits:
            exact = kind == "exact"
            findings.append(
                FindingDraft(
                    "SAN_EXACT_MATCH" if exact else "SAN_CLOSE_MATCH",
                    "REVIEW",
                    "CRITICAL" if exact else "HIGH",
                    "Name matches a sanctions list entry" if exact else "Name is close to a sanctions list entry",
                    f"The insured '{name}' {'matches' if exact else f'is a {score}% match for'} '{e.name}' "
                    f"({e.kind}, reference {e.entity_id}) on {e.list_name}. This is a potential match, not a "
                    f"finding of fact: check date of birth, address and nationality before confirming or dismissing.",
                    row.sheet_name,
                    row.row_number,
                    NAME,
                    sheet.mapped.get(NAME),
                    row.claim_row_id,
                    row.claim_reference,
                    evidence={
                        "list": e.list_name,
                        "entry_name": e.name,
                        "entry_reference": e.entity_id,
                        "score": score,
                        "match": kind,
                    },
                    key=f"{e.list_name}:{e.entity_id}",
                )
            )
    return finish([rule], findings, {"lists": lists, "threshold": threshold})
