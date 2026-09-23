"""Phase 3 (+ fix spec 3.3/3.4): propose a column mapping for an unseen
bordereau layout.

Two-stage approach:
  1. Fuzzy match each header against a maintained alias list per field
     (cheap, no API call, catches near-exact header names).
  2. Anything left unmatched is batched into a single Claude call that
     returns a structured mapping -- but only if AI-assisted mapping is
     actually available (ANTHROPIC_API_KEY set). That availability is
     checked ONCE via ai_mapping_available(), up front, not discovered by
     catching an exception per column mid-run: build_mapping() never
     raises for "no key configured", it returns a MappingBatchResult
     whose `ai_unavailable_reason` is set instead. This is the single
     object every caller (CLI, Streamlit, the report generator) reads,
     so "AI mapping is unavailable" can never be shown by one surface and
     silently swallowed by another (fix spec D3/D4).

Every column ends up in exactly one of three states, which survives into
every downstream consumer (ingest, validation, report): "alias" (fuzzy
match found), "ai" (Claude resolved it), or "unmapped" (neither did, and
no source column exists for that field -- never treated as "field exists
and is blank once ingested").

Nothing here is auto-committed: build_mapping() returns suggestions with
provenance and a confidence score; the caller (CLI or Streamlit) must run
them through confirm_mapping() / a human review step before the mapping
is used to ingest data. This is also where every mapping decision gets
logged for the audit trail (Section 6).
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass
from typing import Protocol

from rapidfuzz import fuzz
from rapidfuzz import process as rf_process

from .schema import FIELDS, FIELDS_BY_CODE

FUZZY_THRESHOLD = 85.0  # rapidfuzz token_sort_ratio, 0-100

MappingState = str  # "alias" | "ai" | "unmapped"

_TRAILING_PAREN_RE = re.compile(r"\s*\(([^()]*)\)\s*$")


def split_trailing_parenthetical(header: str) -> tuple[str, str | None]:
    """'Paid to Date (GBP)' -> ('Paid to Date', 'GBP'); 'Paid Amount' ->
    ('Paid Amount', None). Only strips a single trailing group, so a
    header with a legitimate parenthetical elsewhere in the middle of the
    text is left alone. Used both to normalize header text for matching
    (the suffix would otherwise drag every token_sort_ratio score down --
    "Paid to Date (GBP)" scored 80 against the "paid to date" alias,
    just under FUZZY_THRESHOLD, so real bordereaux headers like this were
    silently unmapped) and to recover a currency/unit hint from it."""
    match = _TRAILING_PAREN_RE.search(header)
    if not match:
        return header, None
    core = header[: match.start()]
    suffix = match.group(1).strip()
    return core, (suffix or None)


# TB-003: a header's parenthetical suffix can carry a scale multiplier
# ("Paid (USD m)" means every value is stated in millions) alongside, or
# instead of, a currency code. Previously the suffix was parsed only for
# an exact-match currency code and the scale semantics were discarded
# entirely -- so a $36,686,000 claim exported as $36.69.
_SCALE_MULTIPLIERS = {
    "000s": 1_000.0, "000": 1_000.0, "k": 1_000.0, "thousands": 1_000.0,
    "m": 1_000_000.0, "mn": 1_000_000.0, "million": 1_000_000.0, "millions": 1_000_000.0,
    "bn": 1_000_000_000.0, "billion": 1_000_000_000.0, "billions": 1_000_000_000.0,
}


def parse_scale_suffix(suffix: str | None) -> float | None:
    """'USD m' -> 1_000_000.0, 'GBP' -> None, 'EUR 000s' -> 1_000.0.
    Tokenized (not matched whole) since a real suffix commonly carries a
    currency code and a scale token side by side."""
    if not suffix:
        return None
    for token in suffix.replace(",", " ").split():
        mult = _SCALE_MULTIPLIERS.get(token.strip().lower())
        if mult is not None:
            return mult
    return None


def parse_currency_suffix(suffix: str | None, valid_codes: frozenset[str]) -> str | None:
    """'GBP' -> 'GBP', 'USD m' -> 'USD', 'm' -> None. Tokenized for the
    same reason as parse_scale_suffix -- a currency code sharing a
    suffix with a scale token must still be recognised."""
    if not suffix:
        return None
    for token in suffix.replace(",", " ").split():
        code = token.strip().upper()
        if code in valid_codes:
            return code
    return None


def normalize_header(header: str) -> str:
    """'ClaimReference' -> 'claim reference', 'O/S Reserve' -> 'o s reserve',
    'Paid to Date (GBP)' -> 'paid to date' (trailing parenthetical unit/
    currency suffixes never take part in alias matching -- see
    split_trailing_parenthetical() to recover the suffix itself)."""
    core, _ = split_trailing_parenthetical(header)
    text = unicodedata.normalize("NFKC", core)  # non-breaking spaces etc. -> regular space
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
    text = re.sub(r"[_./\\\-]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


@dataclass
class MappingSuggestion:
    source_column: str
    field_code: str | None
    confidence: float
    method: MappingState  # "alias" | "ai" | "unmapped"


def _alias_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for f in FIELDS:
        index[normalize_header(f.name)] = f.code
        for alias in f.aliases:
            index[normalize_header(alias)] = f.code
    return index


def fuzzy_match_headers(headers: list[str]) -> dict[str, MappingSuggestion]:
    alias_index = _alias_index()
    choices = list(alias_index.keys())

    results: dict[str, MappingSuggestion] = {}
    for header in headers:
        norm = normalize_header(header)
        match = rf_process.extractOne(norm, choices, scorer=fuzz.token_sort_ratio)
        if match and match[1] >= FUZZY_THRESHOLD:
            alias, score, _ = match
            results[header] = MappingSuggestion(header, alias_index[alias], score, "alias")
        else:
            results[header] = MappingSuggestion(header, None, match[1] if match else 0.0, "unmapped")
    return results


class AIMapper(Protocol):
    def propose(self, headers: list[str]) -> dict[str, str | None]:
        """Return {header: field_code or None} for the given headers."""
        ...


def ai_mapping_available() -> bool:
    """The single source of truth for whether the AI-assisted mapping
    fallback can run. Checked once, up front (fix spec 3.4: validated
    "at startup", not discovered per-column mid-run), and used both to
    decide whether build_mapping() attempts an AI call and to render the
    same "unavailable" state in the UI -- there is no second copy of this
    decision anywhere else in the codebase."""
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


_TOOL_SCHEMA = {
    "name": "propose_mapping",
    "description": (
        "Propose a mapping from raw claims-bordereau column headers to the "
        "canonical Lloyd's Coverholder Reporting Standard v5.2 field codes. "
        "If a header does not correspond to any of the listed fields, map it to null."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "mappings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "source_column": {"type": "string"},
                        "field_code": {
                            "type": ["string", "null"],
                            "enum": [f.code for f in FIELDS] + [None],
                        },
                        "confidence": {
                            "type": "number",
                            "description": "0-1 confidence in this mapping",
                        },
                    },
                    "required": ["source_column", "field_code", "confidence"],
                },
            },
        },
        "required": ["mappings"],
    },
}


def _field_reference_text() -> str:
    lines = []
    for f in FIELDS:
        lines.append(f"- {f.code}: {f.name} ({f.dtype}{', required' if f.required else ''}) - {f.notes}")
    return "\n".join(lines)


class ClaudeAIMapper:
    """Live implementation. Requires ANTHROPIC_API_KEY in the environment."""

    def __init__(self, model: str = "claude-haiku-4-5-20251001"):
        self.model = model

    def propose(self, headers: list[str]) -> dict[str, str | None]:
        import anthropic

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set; cannot call the AI mapping fallback. "
                "Set it in the environment, or resolve remaining headers manually."
            )

        client = anthropic.Anthropic(api_key=api_key)
        prompt = (
            "Here are the canonical target fields for a claims bordereau:\n\n"
            f"{_field_reference_text()}\n\n"
            "Here are raw column headers from an insurer bordereau file that could "
            "not be confidently matched by fuzzy string matching against known "
            "aliases. For each header, propose which canonical field code it "
            "corresponds to (or null if none apply, e.g. it's a field outside "
            "the 10-field skeleton).\n\n"
            f"Headers:\n{json.dumps(headers, indent=2)}\n\n"
            "Call propose_mapping with your answer."
        )

        response = client.messages.create(
            model=self.model,
            max_tokens=2048,
            tools=[_TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": "propose_mapping"},
            messages=[{"role": "user", "content": prompt}],
        )

        for block in response.content:
            if block.type == "tool_use" and block.name == "propose_mapping":
                mappings = block.input.get("mappings", [])
                return {m["source_column"]: m.get("field_code") for m in mappings}
        raise RuntimeError("Claude did not return a propose_mapping tool call")


@dataclass
class MappingBatchResult:
    """The one object both the UI and the report/validation layers read
    for "how did this file's columns get mapped" -- see module docstring.
    """
    suggestions: list[MappingSuggestion]
    ai_attempted: bool = False
    ai_unavailable_reason: str | None = None

    @property
    def by_column(self) -> dict[str, MappingSuggestion]:
        return {s.source_column: s for s in self.suggestions}

    def unmapped_codes_among(self, codes: "list[str] | tuple[str, ...]") -> list[str]:
        """Which of the given canonical field codes have no column mapped
        to them at all in this batch (used to flag unmapped required
        fields distinctly from "mapped but blank")."""
        mapped = {s.field_code for s in self.suggestions if s.field_code}
        return [c for c in codes if c not in mapped]


def build_mapping(headers: list[str], ai_mapper: AIMapper | None = None) -> MappingBatchResult:
    """Stage 1 (fuzzy/alias) then stage 2 (AI) for anything left unmapped.
    Never raises for "AI mapping not configured" -- that's a normal,
    reportable outcome, not an error to catch per call site."""
    suggestions = fuzzy_match_headers(headers)
    unmatched = [h for h, s in suggestions.items() if s.method == "unmapped"]

    ai_attempted = False
    ai_unavailable_reason = None

    if unmatched:
        if ai_mapper is not None:
            ai_attempted = True
            ai_results = ai_mapper.propose(unmatched)
        elif ai_mapping_available():
            ai_attempted = True
            ai_results = ClaudeAIMapper().propose(unmatched)
        else:
            ai_results = None
            ai_unavailable_reason = "ANTHROPIC_API_KEY is not set"

        if ai_attempted:
            for header in unmatched:
                code = ai_results.get(header)
                suggestions[header] = MappingSuggestion(
                    header, code, confidence=1.0 if code else 0.0, method="ai" if code else "unmapped"
                )

    return MappingBatchResult(
        suggestions=[suggestions[h] for h in headers],
        ai_attempted=ai_attempted,
        ai_unavailable_reason=ai_unavailable_reason,
    )


def derive_field_state(suggestions: list[MappingSuggestion], confirmed_mapping: dict[str, str]) -> dict[str, str]:
    """For every canonical field code, how it ended up in the CONFIRMED
    mapping (fix spec 3.3): "alias" | "ai" | "manual" (a human picked a
    column the automatic stages didn't suggest for that field) |
    "unmapped" (no confirmed column at all). This is what validation.py
    and report.py check before treating a null cell as "genuinely blank"
    rather than "field was never mapped for this sheet"."""
    suggested_by_column = {s.source_column: s for s in suggestions}
    state: dict[str, str] = {}
    for source_col, code in confirmed_mapping.items():
        suggestion = suggested_by_column.get(source_col)
        if suggestion and suggestion.field_code == code and suggestion.method in ("alias", "ai"):
            state[code] = suggestion.method
        else:
            state[code] = "manual"
    for f in FIELDS:
        state.setdefault(f.code, "unmapped")
    return state


def render_confirmation_table(suggestions: list[MappingSuggestion]) -> str:
    lines = [f"{'Source column':<30} {'-> Field':<12} {'Field name':<32} {'Method':<10} {'Confidence'}"]
    lines.append("-" * 100)
    for s in suggestions:
        field_name = FIELDS_BY_CODE[s.field_code].name if s.field_code else "(unmapped)"
        confidence_str = f"{s.confidence:.0f}%" if s.method == "alias" else f"{s.confidence:.2f}"
        lines.append(
            f"{s.source_column:<30} {s.field_code or '-':<12} {field_name:<32} "
            f"{s.method:<10} {confidence_str}"
        )
    return "\n".join(lines)


def confirm_mapping_cli(suggestions: list[MappingSuggestion], auto_confirm: bool = False) -> dict[str, str]:
    """Print the proposed mapping and ask for confirmation before it's
    used to ingest anything. Returns {source_column: field_code}, with any
    rows the user rejects removed. Never silently trusts fuzzy or AI output."""
    print(render_confirmation_table(suggestions))
    if not auto_confirm:
        answer = input("\nAccept this mapping as-is? [y]es / [n]o (abort): ").strip().lower()
        if answer not in ("y", "yes"):
            raise RuntimeError("Mapping rejected by user; aborting ingestion.")
    return {s.source_column: s.field_code for s in suggestions if s.field_code}


@dataclass
class MappingAuditRecord:
    source_column: str
    field_code: str | None
    method: str
    confidence: float
    confirmed: bool


def audit_trail(suggestions: list[MappingSuggestion], confirmed_mapping: dict[str, str]) -> list[MappingAuditRecord]:
    """Section 6: log every mapping decision (auto-matched vs AI-suggested
    vs human-confirmed) for the audit trail."""
    return [
        MappingAuditRecord(
            source_column=s.source_column,
            field_code=s.field_code,
            method=s.method,
            confidence=s.confidence,
            confirmed=confirmed_mapping.get(s.source_column) == s.field_code and s.field_code is not None,
        )
        for s in suggestions
    ]
