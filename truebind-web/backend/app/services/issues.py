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


# Root cause versus downstream symptom, decided by code. A finding is a symptom
# when the same row also has a finding from one of the rules that can cause it:
# an amount held as text breaks the incurred reconciliation, an unreadable date
# breaks the date-order check. The cause is shown first; fixing it is expected
# to clear the symptom on the next run.
SYMPTOM_OF: dict[str, tuple[str, ...]] = {
    "arithmetic_mismatch": ("amount_stored_as_text", "schema_violation", "missing_mandatory_field"),
    "paid_exceeds_incurred": ("arithmetic_mismatch", "amount_stored_as_text", "schema_violation",
                              "missing_mandatory_field"),
    "incurred_over_limit": ("arithmetic_mismatch", "amount_stored_as_text", "schema_violation"),
    "date_order": ("date_unreadable", "date_stored_as_text", "missing_mandatory_field"),
    "date_in_future": ("date_unreadable", "date_stored_as_text"),
    "loss_outside_policy_period": ("expiry_before_inception", "date_unreadable", "date_stored_as_text"),
    "currency_inconsistency": ("invalid_currency", "currency_normalised"),
    "closed_with_reserve": ("invalid_status",),
    "repeat_period_unknown": ("missing_mandatory_field",),
    "probable_duplicate": ("exact_duplicate",),
}
_SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "INFO": 3}


def link_symptoms(items: list[dict]) -> None:
    """Set `symptom_of` (the cause's root-cause key) on each issue that is a
    downstream symptom of another issue on the same row. In place."""
    by_row: dict[tuple, list[dict]] = {}
    for i in items:
        by_row.setdefault((i["sheet"], i["row"]), []).append(i)
    for siblings in by_row.values():
        for i in siblings:
            causes = SYMPTOM_OF.get(i["rule"] or "")
            cause = next((s for s in siblings if causes and s is not i and s["rule"] in causes), None)
            i["symptom_of"] = (cause["root_cause"] or cause["rule"]) if cause else None


def group_root_causes(items: list[dict], amounts: dict[str, tuple[float, str | None]]) -> list[dict]:
    """One card per cause. `amounts` maps a row key (sheet:row) to (incurred,
    currency); the amount affected is summed over distinct rows per currency.
    Causes come first (by severity, then size), symptoms after."""
    groups: dict[str, dict] = {}
    for i in items:
        key = i["root_cause"] or i["rule"]
        r = catalogue_rule(i["rule"] or "")
        g = groups.get(key)
        if g is None:
            g = groups[key] = {
                "root_cause": key, "rule": i["rule"], "rule_version": i.get("rule_version"), "label": i["label"],
                "column": i["column"], "sheet": i["sheet"], "severity": r.severity, "outcome": i["outcome"],
                "owner": r.owner, "auto_fix": r.auto_fix, "fix": r.fix, "count": 0, "open": 0, "symptoms": 0,
                "caused_by": {}, "first_issue_id": i["id"], "first_open_issue_id": None, "_rows": set(),
            }
        g["count"] += 1
        is_open = i["status"] not in CLOSED
        g["open"] += is_open
        if is_open and g["first_open_issue_id"] is None:
            g["first_open_issue_id"] = i["id"]
        if i.get("symptom_of"):
            g["symptoms"] += 1
            g["caused_by"][i["symptom_of"]] = g["caused_by"].get(i["symptom_of"], 0) + 1
        g["_rows"].add(f"{i['sheet']}:{i['row']}")
    out = []
    for g in groups.values():
        affected: dict[str, float] = {}
        rows = g.pop("_rows")
        for rk in rows:
            amount, ccy = amounts.get(rk, (0.0, None))
            if amount:
                affected[ccy or ""] = round(affected.get(ccy or "", 0.0) + abs(amount), 2)
        g["rows"] = len(rows)
        g["amount_affected"] = [{"currency": c or None, "amount": a} for c, a in sorted(affected.items())]
        g["kind"] = "symptom" if g["symptoms"] == g["count"] else "cause"
        g["caused_by"] = [{"root_cause": k, "count": n} for k, n in sorted(g["caused_by"].items(), key=lambda kv: -kv[1])]
        out.append(g)
    out.sort(key=lambda g: (g["kind"] == "symptom", g["open"] == 0, _SEVERITY_ORDER.get(g["severity"], 9), -g["count"]))
    return out
