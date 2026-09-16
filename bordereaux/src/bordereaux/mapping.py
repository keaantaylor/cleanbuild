"""Phase 3: propose a column mapping for an unseen bordereau layout.

Two-stage approach:
  1. Fuzzy match each header against a maintained alias list per field
     (cheap, no API call, catches near-exact header names).
  2. Anything left unmatched (or below the confidence threshold) is
     batched into a single Claude call that returns a structured mapping.

Nothing here is auto-committed: build_mapping() returns suggestions with
provenance ("fuzzy" vs "ai") and a confidence score; the caller (CLI or
Streamlit) must run them through confirm_mapping() / a human review step
before the mapping is used to ingest data. This is also where every
mapping decision gets logged for the audit trail (Section 6).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Protocol

from rapidfuzz import fuzz
from rapidfuzz import process as rf_process

from .schema import FIELDS, FIELDS_BY_CODE

FUZZY_THRESHOLD = 85.0  # rapidfuzz token_sort_ratio, 0-100


def normalize_header(header: str) -> str:
    """'ClaimReference' -> 'claim reference', 'O/S Reserve' -> 'o s reserve'."""
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", header)
    text = re.sub(r"[_./\\\-]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


@dataclass
class MappingSuggestion:
    source_column: str
    field_code: str | None
    confidence: float
    method: str  # "fuzzy" | "ai" | "unmatched"


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
            results[header] = MappingSuggestion(header, alias_index[alias], score, "fuzzy")
        else:
            results[header] = MappingSuggestion(header, None, match[1] if match else 0.0, "unmatched")
    return results


class AIMapper(Protocol):
    def propose(self, headers: list[str]) -> dict[str, str | None]:
        """Return {header: field_code or None} for the given headers."""
        ...


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


def build_mapping(headers: list[str], ai_mapper: AIMapper | None = None) -> list[MappingSuggestion]:
    """Stage 1 (fuzzy) then stage 2 (AI) for anything left unmatched."""
    suggestions = fuzzy_match_headers(headers)
    unmatched = [h for h, s in suggestions.items() if s.method == "unmatched"]

    if unmatched:
        mapper = ai_mapper or ClaudeAIMapper()
        ai_results = mapper.propose(unmatched)
        for header in unmatched:
            code = ai_results.get(header)
            suggestions[header] = MappingSuggestion(
                header, code, confidence=1.0 if code else 0.0, method="ai" if code else "unmatched"
            )

    return [suggestions[h] for h in headers]


def render_confirmation_table(suggestions: list[MappingSuggestion]) -> str:
    lines = [f"{'Source column':<30} {'-> Field':<12} {'Field name':<32} {'Method':<10} {'Confidence'}"]
    lines.append("-" * 100)
    for s in suggestions:
        field_name = FIELDS_BY_CODE[s.field_code].name if s.field_code else "(unmapped)"
        confidence_str = f"{s.confidence:.0f}%" if s.method == "fuzzy" else f"{s.confidence:.2f}"
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
