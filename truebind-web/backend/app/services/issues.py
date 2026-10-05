"""Issues: each finding as a first-class record.

A finding (ValidationResult) carries, in its `extra`: the rule and its version,
the ruleset version, the issue status and its history, expected / actual /
difference where the rule compares values, the cell coordinates and a
root-cause key (rule + source column) used to group issues that share a cause.
Lineage (file, sheet, row, column, original -> normalised value, mapped field,
transformation) is computed on request from the stored original and the
normalised claim row.

Statuses, decided by code only:
  DETECTED                a rule found an error
  AUTO_FIX_PROPOSED       a deterministic formatting fix is proposed (never applied to the source)
  AUTO_FIXED              that fix was approved into a corrected version
  REQUIRES_INFORMATION    the check could not run: a value or column is missing
  REQUIRES_HUMAN_REVIEW   unusual, or a similarity signal: a person decides
  RESOLVED                corrected, or confirmed fixed by the sender
  OVERRIDDEN              accepted as reported by a person, with a reason
  BLOCKED                 cannot proceed until something outside TrueBind changes
"""

from __future__ import annotations

from bordereaux.rules import RULESET_VERSION
from bordereaux.rules import rule as catalogue_rule

from ..models._util import utcnow

STATUSES = ("DETECTED", "AUTO_FIX_PROPOSED", "AUTO_FIXED", "REQUIRES_INFORMATION", "REQUIRES_HUMAN_REVIEW",
            "RESOLVED", "OVERRIDDEN", "BLOCKED")
CLOSED = ("AUTO_FIXED", "RESOLVED", "OVERRIDDEN")
# Allowed moves. Reopening a closed issue goes back to DETECTED (or review).
TRANSITIONS: dict[str, tuple[str, ...]] = {
    "DETECTED": ("REQUIRES_INFORMATION", "REQUIRES_HUMAN_REVIEW", "RESOLVED", "OVERRIDDEN", "BLOCKED",
                 "AUTO_FIX_PROPOSED"),
    "AUTO_FIX_PROPOSED": ("AUTO_FIXED", "DETECTED", "REQUIRES_HUMAN_REVIEW", "OVERRIDDEN", "RESOLVED"),
    "AUTO_FIXED": ("DETECTED", "REQUIRES_HUMAN_REVIEW"),
    "REQUIRES_INFORMATION": ("DETECTED", "REQUIRES_HUMAN_REVIEW", "RESOLVED", "OVERRIDDEN", "BLOCKED"),
    "REQUIRES_HUMAN_REVIEW": ("DETECTED", "REQUIRES_INFORMATION", "RESOLVED", "OVERRIDDEN", "BLOCKED",
                              "AUTO_FIX_PROPOSED"),
    "RESOLVED": ("DETECTED", "REQUIRES_HUMAN_REVIEW"),
    "OVERRIDDEN": ("DETECTED", "REQUIRES_HUMAN_REVIEW"),
    "BLOCKED": ("DETECTED", "REQUIRES_INFORMATION", "REQUIRES_HUMAN_REVIEW", "RESOLVED", "OVERRIDDEN"),
}
# The older review decisions (exceptions page) map onto issue statuses.
REVIEW_TO_STATUS = {"open": "DETECTED", "in_review": "REQUIRES_HUMAN_REVIEW", "resolved": "RESOLVED",
                    "accepted": "OVERRIDDEN", "false_positive": "OVERRIDDEN"}


class TransitionError(ValueError):
    pass


def initial_status(outcome: str, rule_code: str) -> str:
    """Where an issue starts, from the rule's outcome alone (deterministic)."""
    if outcome == "NOT_EVALUABLE":
        return "REQUIRES_INFORMATION"
    if catalogue_rule(rule_code).auto_fix:
        return "AUTO_FIX_PROPOSED"
    return "DETECTED" if outcome == "FAIL" else "REQUIRES_HUMAN_REVIEW"


def difference(expected, actual):
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return round(actual - expected, 2)
    return None


def issue_fields(outcome: str, rule_code: str, expected, actual, column: str | None, field_code: str | None) -> dict:
    """The issue part of a finding's `extra`, written when the finding is created."""
    r = catalogue_rule(rule_code)
    status = initial_status(outcome, rule_code)
    return {
        "rule_version": r.version, "ruleset_version": RULESET_VERSION,
        "issue_status": status, "expected": expected, "actual": actual,
        "difference": difference(expected, actual),
        "root_cause": f"{rule_code}:{column or field_code or 'row'}",
        "history": [{"at": utcnow().isoformat(), "status": status, "actor": "system",
                     "note": f"Detected by rule {rule_code} v{r.version} (ruleset {RULESET_VERSION})"}],
    }


def transition(extra: dict, new_status: str, actor: str, note: str | None) -> dict:
    """A new `extra` with the status changed and the move appended to the
    history. Raises TransitionError for a move the lifecycle does not allow."""
    if new_status not in STATUSES:
        raise TransitionError(f"Unknown status {new_status}.")
    current = extra.get("issue_status") or "DETECTED"
    if new_status == current:
        return extra
    if new_status not in TRANSITIONS.get(current, ()):
        raise TransitionError(f"An issue cannot move from {current} to {new_status}.")
    if new_status == "OVERRIDDEN" and not (note or "").strip():
        raise TransitionError("Say why the value is accepted as reported.")
    history = list(extra.get("history") or [])
    history.append({"at": utcnow().isoformat(), "status": new_status, "from": current, "actor": actor,
                    "note": (note or "")[:2000] or None})
    return {**extra, "issue_status": new_status, "history": history}


def describe_transformation(field_dtype: str | None, original, normalised) -> str:
    if original is None or normalised is None:
        return "none"
    o, n = str(original).strip(), str(normalised)
    if o == n:
        return "none"
    if field_dtype == "date":
        return "read as a date (ISO)"
    if field_dtype == "decimal":
        return "read as a number"
    if o.lower() == n.lower():
        return "case standardised"
    return "normalised (alias or synonym)"
