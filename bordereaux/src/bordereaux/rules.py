"""One catalogue of every row-level rule: its plain-English name, the check it
belongs to, its severity, whether it is an error or something to review, and
the suggested fix.

This is the single source of truth for severity and wording. The engine's
score, the API (and through it the app, the PDF and every export) all read
it, so a finding can never be "Medium" on one screen and "High" in a file.

owner (who must act):
  "sender" -- only the sender can supply or correct the value: query them.
  "us"     -- the reviewer can resolve it without the sender: a safe fix the
              corrected copy applies (formatting only), or a mapping choice.

outcome:
  "FAIL"   -- red: the data is wrong, missing or contradictory. Counts against
              the health score.
  "REVIEW" -- amber: unusual or not in a checkable form. Shown and exported,
              never counted as an error in the score.
"""

from __future__ import annotations

from dataclasses import dataclass


# The rule set as a whole. Bump when any rule's logic, tolerance or wording of
# its outcome changes; each rule also carries its own version, recorded on
# every finding, so a result can always be traced to the logic that made it.
RULESET_VERSION = "2026.10.2"


@dataclass(frozen=True)
class Rule:
    code: str
    label: str
    check_type: str
    severity: str  # CRITICAL | HIGH | MEDIUM | INFO
    outcome: str  # FAIL | REVIEW
    fix: str
    owner: str = "sender"  # sender | us
    version: str = "1.0"
    # A deterministic, reversible formatting fix exists (applied only as a
    # proposed correction, never to the source file).
    auto_fix: bool = False


_RULES = [
    # Required data
    Rule("missing_mandatory_field", "Required data missing", "MANDATORY_FIELD", "CRITICAL", "FAIL",
         "Ask the sender for the missing value."),
    Rule("missing_policy_reference", "Policy number missing", "POLICY", "MEDIUM", "REVIEW",
         "Ask the sender for the policy number."),
    # Amounts
    Rule("arithmetic_mismatch", "Total incurred does not reconcile", "ARITHMETIC", "HIGH", "FAIL",
         "Total incurred should equal paid plus reserve (plus fees). Ask the sender which figure is right.", version="1.1"),
    Rule("paid_exceeds_incurred", "Paid exceeds total incurred", "ARITHMETIC", "HIGH", "FAIL",
         "Paid to date cannot be more than total incurred. Ask the sender to correct the figures."),
    Rule("negative_reserve", "Negative reserve", "AMOUNT", "HIGH", "FAIL",
         "Reserves cannot be negative. Ask the sender for the correct outstanding amount."),
    Rule("amount_stored_as_text", "Amount stored as text", "AMOUNT", "INFO", "REVIEW",
         "Read correctly, but the cell holds text. The corrected copy converts it to a number.", "us", auto_fix=True),
    # Dates
    Rule("date_order", "Notified before the loss date", "DATE", "MEDIUM", "FAIL",
         "The claim was notified before it happened. Check both dates with the sender."),
    Rule("date_in_future", "Date in the future", "DATE", "MEDIUM", "FAIL",
         "Check the date with the sender."),
    Rule("date_unreadable", "Cannot be validated as a date", "DATE", "MEDIUM", "REVIEW",
         "The cell is not a recognisable date, so the date checks could not run. Ask for a real date."),
    Rule("date_stored_as_text", "Date stored as text or a number", "DATE", "INFO", "REVIEW",
         "Read correctly, but stored as text or an Excel serial number. The corrected copy converts it to a "
         "real date.", "us", auto_fix=True),
    # Policy
    Rule("loss_outside_policy_period", "Loss outside the policy period", "POLICY", "HIGH", "FAIL",
         "The date of loss is before inception or after expiry. Check the dates and the policy."),
    Rule("expiry_before_inception", "Policy expiry before inception", "POLICY", "MEDIUM", "FAIL",
         "The policy period is the wrong way round. Check the inception and expiry dates."),
    Rule("incurred_over_limit", "Incurred exceeds the policy limit", "POLICY", "HIGH", "FAIL",
         "Total incurred is above the policy limit: a possible overpayment or a wrong limit. Check both."),
    Rule("policy_limit_missing", "Policy limit missing", "POLICY", "INFO", "REVIEW",
         "The limit is blank or zero, so the limit check could not run."),
    Rule("policy_ref_format", "Policy number format differs", "POLICY", "INFO", "REVIEW",
         "This policy number does not follow the format of the others in the file. Check it is right."),
    # References
    Rule("claim_ref_format", "Claim reference formatting", "REFERENCE", "INFO", "REVIEW",
         "The reference has extra spaces or hidden characters. The corrected copy trims them; check any "
         "capitalisation difference with the sender.", "us", auto_fix=True),
    # Currency
    Rule("invalid_currency", "Currency code not recognised", "CURRENCY", "HIGH", "FAIL",
         "Use a valid ISO currency code (EUR, GBP, USD...). Confirm which currency the amounts are in."),
    Rule("currency_inconsistency", "Claim reported in several currencies", "CURRENCY", "HIGH", "FAIL",
         "The same claim appears in more than one currency. Confirm the settlement currency."),
    Rule("currency_normalised", "Currency written non-standardly", "CURRENCY", "INFO", "REVIEW",
         "Read as the ISO code shown. The corrected copy writes the ISO code.", "us", auto_fix=True),
    # Status
    Rule("invalid_status", "Status not recognised", "STATUS", "MEDIUM", "FAIL",
         "Use one of the agreed statuses (Open, Closed, Reopened...), or add it to the accepted list."),
    Rule("closed_with_reserve", "Closed claim still holds a reserve", "STATUS", "MEDIUM", "REVIEW",
         "A closed or settled claim should hold no reserve. Ask the sender to release it or reopen the claim."),
    # Mapping
    Rule("mapping_completeness", "Sheet only partly understood", "MAPPING_COMPLETENESS", "HIGH", "REVIEW",
         "Few columns on this sheet matched a claim field. Check the mapping.", "us"),
    # Other
    Rule("schema_violation", "Value has the wrong type", "OTHER", "HIGH", "FAIL",
         "The value does not fit the field. Ask the sender to correct it."),
    # Duplicates (recorded by the duplicate check, listed here for one source of wording)
    Rule("exact_duplicate", "Exact duplicate", "DUPLICATE", "HIGH", "FAIL",
         "The same claim was sent twice with identical figures. Ask the sender to withdraw one."),
    Rule("repeat_period_unknown", "Repeated with no reporting period", "DUPLICATE", "MEDIUM", "REVIEW",
         "The same claim appears on two sheets with identical figures and no period. Confirm which applies."),
    Rule("probable_duplicate", "Probable duplicate", "DUPLICATE", "MEDIUM", "REVIEW",
         "Compare the two rows side by side; confirm whether they are the same loss.", version="2.0"),
    # Reconciliation across rows, sheets and submissions (reconcile.py)
    Rule("totals_mismatch", "Total line does not match its rows", "RECONCILIATION", "HIGH", "FAIL",
         "The stated total differs from the sum of the claim rows. Ask the sender which is right."),
    Rule("cross_sheet_conflict", "Same claim, different amounts on two sheets", "RECONCILIATION", "HIGH", "FAIL",
         "One claim and period carries two different amounts. Ask the sender which sheet is correct."),
    Rule("paid_decreased", "Paid to date went down since last submission", "RECONCILIATION", "HIGH", "FAIL",
         "Paid to date should never fall. Ask the sender for the recovery or correction behind it."),
    Rule("rollforward_break", "Previously paid does not match last submission", "RECONCILIATION", "HIGH", "FAIL",
         "Previously paid should equal last submission's paid to date. Ask the sender to reconcile."),
]

RULES: dict[str, Rule] = {r.code: r for r in _RULES}
FAIL_RULES = frozenset(r.code for r in _RULES if r.outcome == "FAIL")
REVIEW_RULES = frozenset(r.code for r in _RULES if r.outcome == "REVIEW")


SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "INFO": 3}


def rule(code: str) -> Rule:
    """The catalogue entry, or a safe generic one for an unknown code."""
    return RULES.get(code) or Rule(code, code.replace("_", " ").capitalize(), "OTHER", "INFO", "REVIEW", "")
