"""Turns the deterministic aggregate from exception_aggregation_service
into a short plain-English narrative via Claude. Reuses the exact same
client/tool-call pattern as bordereaux.mapping.ClaudeAIMapper (this
codebase's one existing LLM integration, for the AI-assisted column-
mapping fallback) rather than a second, inconsistent integration:
os.environ["ANTHROPIC_API_KEY"], anthropic.Anthropic(...).messages.create
with tool_choice forcing a single structured tool call.

SAFETY RULE (non-negotiable for this feature): the model must never
compute, derive, recalculate, or estimate any financial figure. Every
number it is allowed to mention already exists in the aggregate this
module passes it -- see build_prompt()'s explicit instruction and
_find_unverifiable_numbers()'s post-hoc check below. This is a financial
reconciliation tool; an LLM doing its own maths on claim values would
introduce exactly the class of error the product exists to catch.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 1536

_TOOL_SCHEMA = {
    "name": "triage_summary",
    "description": (
        "Summarise a pre-computed, already-correct set of claims-bordereau exception "
        "statistics for a human reviewer. Explain, prioritise and group only -- never "
        "calculate, estimate, or restate a number differently than given."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "executive_summary": {
                "type": "string",
                "description": "2-4 sentences, plain English, for a non-technical claims reviewer.",
            },
            "actions": {
                "type": "array",
                "minItems": 3,
                "maxItems": 6,
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Short imperative action, e.g. 'Review the Acme Re sheet mapping'."},
                        "rationale": {"type": "string", "description": "One line: why this is worth doing, citing the given figures verbatim."},
                        "category": {"type": "string", "enum": ["ingestion", "data_quality", "duplicate", "other"]},
                        "filter_check_type": {
                            "type": ["string", "null"],
                            "description": "The check_type from by_category this action is about, if any, else null.",
                        },
                        "filter_sheet_name": {
                            "type": ["string", "null"],
                            "description": "The sheet_name from by_sheet this action is about, if any, else null.",
                        },
                    },
                    "required": ["title", "rationale", "category", "filter_check_type", "filter_sheet_name"],
                },
            },
            "ingestion_issues": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Short bullet points: findings that are likely mapping/ingestion problems, fixable in the tool.",
            },
            "data_issues": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Short bullet points: findings that are likely genuine data problems, to query with the cedant.",
            },
        },
        "required": ["executive_summary", "actions", "ingestion_issues", "data_issues"],
    },
}


def narrative_available() -> bool:
    """Same "checked once, up front" convention as bordereaux.mapping.
    ai_mapping_available() -- one source of truth for whether the AI
    narrative can run at all, so the route and any future caller never
    discover "no key configured" by catching an exception mid-call."""
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


@dataclass
class NarrativeResult:
    status: str  # "COMPLETE" | "FAILED" | "UNAVAILABLE"
    narrative: dict | None = None
    model: str | None = None
    error: str | None = None
    warning: str | None = None


def _build_prompt(aggregate: dict) -> str:
    return (
        "Below is a JSON object of PRE-COMPUTED, ALREADY-CORRECT statistics from a "
        "deterministic claims-bordereau validation engine. Every count, monetary value, "
        "and percentage in it has already been calculated correctly by that engine.\n\n"
        "STRICT RULES:\n"
        "- Do not perform any arithmetic. Do not add, subtract, multiply, divide, average, "
        "or recompute a percentage.\n"
        "- Do not estimate, round differently, or restate a number in a way that changes its "
        "value. Quote figures exactly as given (you may use their existing rounding).\n"
        "- Only ever mention a count, monetary value, or percentage that appears somewhere in "
        "the JSON below. If you want to reference something not in the JSON, describe it "
        "qualitatively instead (e.g. \"several sheets\") rather than inventing a number.\n"
        "- 'value_at_stake' figures are in the file's original currency units as recorded; do "
        "not add a currency symbol you were not given.\n\n"
        "Root-cause classification is already done for you: 'ingestion' means the finding is "
        "likely a mapping/ingestion problem fixable in the tool (e.g. a sheet's columns "
        "weren't recognised); 'data_quality' means it's likely a genuine problem with the "
        "cedant's submitted data, worth raising with them.\n\n"
        f"Statistics:\n{json.dumps(aggregate, indent=2)}\n\n"
        "Call triage_summary with: a short plain-English executive summary (2-4 sentences); "
        "3-6 prioritised recommended actions ordered by importance, each with a one-line "
        "rationale citing the relevant figures verbatim, and if the action is about a "
        "specific exception category or sheet, name it in filter_check_type/"
        "filter_sheet_name exactly as it appears in by_category/by_sheet so the UI can use it "
        "to filter; and separate bullet lists of likely ingestion issues vs. likely genuine "
        "data issues."
    )


_NUMBER_RE = re.compile(r"-?\d[\d,]*\.?\d*")


def _numbers_in_text(text: str) -> set[float]:
    found = set()
    for match in _NUMBER_RE.findall(text):
        cleaned = match.replace(",", "")
        try:
            value = float(cleaned)
        except ValueError:
            continue
        # Small integers (list positions, "a few", generic counts) are far
        # too common in ordinary English to reliably flag -- restrict the
        # check to figures large/precise enough to plausibly BE one of the
        # aggregate's real statistics rather than incidental phrasing.
        if abs(value) < 100 and "." not in cleaned:
            continue
        found.add(value)
    return found


def _allowed_numbers(aggregate: dict) -> set[float]:
    allowed: set[float] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
        elif isinstance(node, (int, float)) and not isinstance(node, bool):
            allowed.add(float(node))
            allowed.add(round(float(node)))

    walk(aggregate)
    return allowed


def _find_unverifiable_numbers(narrative: dict, aggregate: dict) -> list[float]:
    """Post-hoc defensive check (never blocking): every large/precise
    number the model wrote must trace back to something already in the
    aggregate. Not a guarantee against a model paraphrasing its way
    around this check, but it catches the common failure mode of a model
    computing and stating a derived figure (a sum, a percentage, an
    average) that isn't actually in the input -- exactly the class of
    error the "never do arithmetic" rule exists to prevent."""
    allowed = _allowed_numbers(aggregate)
    text_fields = [narrative.get("executive_summary", "")]
    for action in narrative.get("actions", []) or []:
        text_fields.append(action.get("title", ""))
        text_fields.append(action.get("rationale", ""))
    text_fields.extend(narrative.get("ingestion_issues", []) or [])
    text_fields.extend(narrative.get("data_issues", []) or [])

    unverifiable: list[float] = []
    tolerance = 1.0  # rounding slack
    for text in text_fields:
        for n in _numbers_in_text(text):
            if not any(abs(n - a) <= tolerance for a in allowed):
                unverifiable.append(n)
    return unverifiable


def generate_narrative(aggregate: dict) -> NarrativeResult:
    """Never raises -- every failure mode (no key, network error, bad
    response shape, timeout) comes back as a NarrativeResult the caller
    can persist and show, so a broken AI call can never take the
    Exceptions page down with it (fix spec Section 1.2)."""
    if not narrative_available():
        return NarrativeResult(status="UNAVAILABLE", error="ANTHROPIC_API_KEY is not set")

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=30.0)
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            tools=[_TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": "triage_summary"},
            messages=[{"role": "user", "content": _build_prompt(aggregate)}],
        )

        narrative = None
        for block in response.content:
            if block.type == "tool_use" and block.name == "triage_summary":
                narrative = block.input
                break

        if narrative is None:
            return NarrativeResult(status="FAILED", error="Claude did not return a triage_summary tool call")

        unverifiable = _find_unverifiable_numbers(narrative, aggregate)
        warning = None
        if unverifiable:
            formatted = ", ".join(f"{n:,.2f}" for n in sorted(unverifiable))
            warning = (
                f"The generated summary mentions figure(s) that don't trace back to the "
                f"underlying data ({formatted}) -- treat this narrative with caution and "
                "verify against the numbers below."
            )

        return NarrativeResult(status="COMPLETE", narrative=narrative, model=MODEL, warning=warning)

    except Exception as exc:  # noqa: BLE001 -- any failure degrades gracefully, never propagates
        return NarrativeResult(status="FAILED", error=f"{exc.__class__.__name__}: {exc}")
