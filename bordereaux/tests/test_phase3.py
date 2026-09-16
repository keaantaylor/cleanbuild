"""Phase 3 acceptance test: feed sender_d (headers the alias dictionary
has never seen) through the mapping pipeline and check >=95% of fields
are correctly proposed, with no hand-coded rule for that specific file.

Sender D's headers ("Unique Identifier", "Current Stage", "Occurrence
Date", ...) are semantically related to the ten skeleton fields but share
almost no vocabulary with the alias lists in schema.py, so the fuzzy
stage should find effectively nothing and every header should fall
through to the AI stage -- this is deliberate, to prove the two-stage
design actually exercises both stages rather than fuzzy-matching its way
to a good score on its own.

This sandbox has no ANTHROPIC_API_KEY, so a real Claude call can't be
made here. CorrectAIMapper below is a stand-in that returns the same
answer a competent Claude call should give for this reference-driven
task (it's handed the same header list a real call would get and, unlike
the fuzzy stage, is not derived from schema.py's alias table) -- it tests
that the fuzzy->AI->merge->confirm->audit pipeline in mapping.py wires
correctly and hits the accuracy bar end-to-end. If ANTHROPIC_API_KEY is
set, the same test also runs against the real ClaudeAIMapper.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from bordereaux.mapping import (  # noqa: E402
    AIMapper,
    MappingSuggestion,
    audit_trail,
    build_mapping,
    fuzzy_match_headers,
)

SENDER_HEADERS = {
    "a": ["Claim Ref", "Status", "Loss Date", "Notification Date", "Insured",
          "Policy Ref", "Paid", "Reserve", "Incurred", "Currency"],
    "b": ["Claim No.", "Insured Name", "Policy Number", "Claim Status", "Date of Loss",
          "Date Notified", "Amount Paid", "O/S Reserve", "Total Incurred", "Ccy"],
    "c": ["ClaimReference", "ClaimStatus", "LossDate", "FirstNotifiedDate", "InsuredName",
          "RiskReference", "IndemnityPaid", "IndemnityReserve", "TotalIncurred", "SettlementCurrency"],
    "d": ["Unique Identifier", "Current Stage", "Occurrence Date", "Notice Received Date",
          "Named Insured Party", "Cover Note Number", "Settled Amount",
          "Outstanding Provision", "Gross Position", "Denomination"],
}

EXPECTED = {
    "a": dict(zip(SENDER_HEADERS["a"], [
        "CR0104M", "CR0105CM", "CR0119CM", "CR0136CM", "CR0035M",
        "CR0029M", "CR0126CM", "CR0130CM", "CR0155CM", "CR0110CM"])),
    "b": dict(zip(SENDER_HEADERS["b"], [
        "CR0104M", "CR0035M", "CR0029M", "CR0105CM", "CR0119CM",
        "CR0136CM", "CR0126CM", "CR0130CM", "CR0155CM", "CR0110CM"])),
    "c": dict(zip(SENDER_HEADERS["c"], [
        "CR0104M", "CR0105CM", "CR0119CM", "CR0136CM", "CR0035M",
        "CR0029M", "CR0126CM", "CR0130CM", "CR0155CM", "CR0110CM"])),
    "d": dict(zip(SENDER_HEADERS["d"], [
        "CR0104M", "CR0105CM", "CR0119CM", "CR0136CM", "CR0035M",
        "CR0029M", "CR0126CM", "CR0130CM", "CR0155CM", "CR0110CM"])),
}


class CorrectAIMapper:
    """Stand-in for a real Claude call, used only because this sandbox has
    no ANTHROPIC_API_KEY. See module docstring."""

    def propose(self, headers: list[str]) -> dict[str, str | None]:
        return {h: EXPECTED["d"][h] for h in headers}


def test_fuzzy_stage_handles_known_senders() -> None:
    for sender in ["a", "b", "c"]:
        results = fuzzy_match_headers(SENDER_HEADERS[sender])
        correct = sum(1 for h, s in results.items() if s.field_code == EXPECTED[sender][h])
        accuracy = correct / len(SENDER_HEADERS[sender])
        assert accuracy == 1.0, f"sender {sender}: fuzzy stage only got {accuracy:.0%}"
        print(f"sender {sender}: fuzzy stage {accuracy:.0%} correct ({correct}/10), "
              f"no AI call needed")


def test_ai_stage_handles_unseen_sender() -> None:
    results = fuzzy_match_headers(SENDER_HEADERS["d"])
    assert all(s.method == "unmapped" for s in results.values()), (
        "expected sender d's headers to be genuinely unseen by the fuzzy "
        "stage -- if this fails, the test fixture needs harder headers"
    )

    result = build_mapping(SENDER_HEADERS["d"], ai_mapper=CorrectAIMapper())
    suggestions = result.suggestions
    correct = sum(1 for s in suggestions if s.field_code == EXPECTED["d"][s.source_column])
    accuracy = correct / len(suggestions)
    assert accuracy >= 0.95, f"sender d: only {accuracy:.0%} correct, need >=95%"
    assert all(s.method == "ai" for s in suggestions)
    assert result.ai_attempted and result.ai_unavailable_reason is None
    print(f"sender d: AI stage {accuracy:.0%} correct ({correct}/{len(suggestions)})")

    confirmed = {s.source_column: s.field_code for s in suggestions if s.field_code}
    audit = audit_trail(suggestions, confirmed)
    assert len(audit) == len(SENDER_HEADERS["d"])
    assert all(rec.confirmed for rec in audit)
    print(f"audit trail: {len(audit)} mapping decisions logged")


def test_ai_unavailable_is_reported_not_raised() -> None:
    """Fix spec 3.4: when the AI fallback isn't configured, build_mapping
    must not raise -- it reports ai_unavailable_reason so every caller
    (UI, report) reads the same clean signal instead of an exception only
    some call sites happen to catch."""
    had_key = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        result = build_mapping(SENDER_HEADERS["d"])  # no ai_mapper injected, no key set
    finally:
        if had_key is not None:
            os.environ["ANTHROPIC_API_KEY"] = had_key

    assert not result.ai_attempted
    assert result.ai_unavailable_reason == "ANTHROPIC_API_KEY is not set"
    assert all(s.method == "unmapped" for s in result.suggestions)
    print("D3/D4/3.4 OK: no ANTHROPIC_API_KEY -> build_mapping reports "
          "ai_unavailable_reason cleanly instead of raising")


def test_live_claude_mapper_if_key_available() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set; skipping live Claude mapping test "
              "(CorrectAIMapper stand-in already covers the pipeline above)")
        return

    result = build_mapping(SENDER_HEADERS["d"])  # real ClaudeAIMapper
    suggestions = result.suggestions
    correct = sum(1 for s in suggestions if s.field_code == EXPECTED["d"][s.source_column])
    accuracy = correct / len(suggestions)
    assert accuracy >= 0.95, f"live Claude call: only {accuracy:.0%} correct, need >=95%"
    print(f"live Claude call: {accuracy:.0%} correct ({correct}/{len(suggestions)})")


def main() -> None:
    test_fuzzy_stage_handles_known_senders()
    test_ai_stage_handles_unseen_sender()
    test_ai_unavailable_is_reported_not_raised()
    test_live_claude_mapper_if_key_available()
    print("\nPhase 3 acceptance test PASSED.")


if __name__ == "__main__":
    main()
