"""Execution policy for every proposed change, decided by code.

  AUTO               a deterministic fix that keeps the value (text that is a
                     number or date written as one, stray spaces): applied at once
  AUTO_WITH_POLICY   a deterministic fix that rewrites the value ("Euro" -> "EUR",
                     "Settled" -> "Closed"): applied at once only when a person in
                     this organisation already approved the same rewrite for the
                     same rule; otherwise it waits for review
  REVIEW_REQUIRED    any person with write access decides
  APPROVAL_REQUIRED  a material financial or business value (amounts, currency,
                     status, dates): a different person from the proposer
                     approves, unless they are the only one who can
  BLOCKED            never applied: formulas, header rows, the claim reference
                     that identifies the record

AI never chooses a policy and never applies a change; it can only propose a
value that then goes through this function like any other.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

from bordereaux import schema as S
from bordereaux.rules import rule as catalogue_rule

AUTO, AUTO_WITH_POLICY, REVIEW_REQUIRED, APPROVAL_REQUIRED, BLOCKED = (
    "AUTO", "AUTO_WITH_POLICY", "REVIEW_REQUIRED", "APPROVAL_REQUIRED", "BLOCKED")
POLICIES = (AUTO, AUTO_WITH_POLICY, REVIEW_REQUIRED, APPROVAL_REQUIRED, BLOCKED)

MONEY_FIELDS = frozenset({S.PAID_TD_CODE, S.PAID_MONTH_CODE, S.PREV_PAID_CODE, S.RESERVE_CODE,
                          S.FEES_PAID_MONTH_CODE, S.FEES_PREV_PAID_CODE, S.FEES_RESERVE_CODE, S.FEES_PAID_TD_CODE,
                          S.INCURRED_IND_CODE, S.INCURRED_CODE, S.POLICY_LIMIT_CODE})
MATERIAL_FIELDS = MONEY_FIELDS | {S.CURRENCY_CODE, S.STATUS_CODE, S.LOSS_DATE_CODE, S.NOTIFIED_DATE_CODE,
                                  "TB_INCEPTION", "TB_EXPIRY"}
IDENTITY_FIELDS = frozenset({S.CLAIM_REF_CODE})


@dataclass(frozen=True)
class Decision:
    policy: str
    reason: str


def _number(v: str | None) -> float | None:
    if v is None:
        return None
    s = re.sub(r"[\s,]", "", str(v))
    try:
        return float(s)
    except ValueError:
        return None


def _date(v: str | None) -> dt.date | None:
    s = str(v or "").strip()[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%d-%m-%Y"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def same_value(before: str | None, after: str | None) -> bool:
    """True when only the representation changes: '1,500' -> 1500,
    '15/01/2024' -> 2024-01-15, ' CLM-1 ' -> 'CLM-1'."""
    if before is None or after is None:
        return before == after
    if str(before).strip() == str(after).strip():
        return True
    a, b = _number(before), _number(after)
    if a is not None and b is not None:
        return abs(a - b) < 1e-9
    d1, d2 = _date(before), _date(after)
    return d1 is not None and d1 == d2


def classify(*, field_code: str | None, source: str, rule: str | None, before: str | None, after: str | None,
             header_row: bool, precedent: bool = False) -> Decision:
    """The policy for one proposed cell change. Pure and deterministic."""
    if after is not None and str(after).lstrip().startswith(("=", "+", "-", "@")) and _number(after) is None:
        return Decision(BLOCKED, "Formulas and formula-like text are never written into a bordereau.")
    if header_row:
        return Decision(BLOCKED, "Header and title rows are not corrected.")
    if field_code in IDENTITY_FIELDS and not same_value(before, after):
        return Decision(BLOCKED, "The claim reference identifies the record. Ask the sender to resubmit it.")
    if source == "auto" and rule and catalogue_rule(rule).auto_fix:
        if same_value(before, after):
            return Decision(AUTO, "Formatting only: the value is unchanged.")
        if precedent:
            return Decision(AUTO_WITH_POLICY, "Applied: the same rewrite was approved before in this organisation.")
        return Decision(AUTO_WITH_POLICY, "Waits for review: this rewrite has not been approved here before.")
    if field_code in MATERIAL_FIELDS and not same_value(before, after):
        return Decision(APPROVAL_REQUIRED, "Changes a financial or business value: a second person approves.")
    return Decision(REVIEW_REQUIRED, "A person with write access decides.")
