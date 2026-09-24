/** What each finding means, in plain language. "Why it matters" and "what
 * to do" describe the check; they never claim more certainty than the
 * check itself has. */
export interface FindingGuide { title: string; why: string; next: string; certainty: "certain" | "signal" | "unknown" }

const GUIDES: Record<string, FindingGuide> = {
  missing_mandatory_field: { title: "Required field missing", certainty: "certain",
    why: "A claim without its reference, insured or date cannot be matched, reconciled or reported to the market.",
    next: "Ask the sender to supply the missing value for this row." },
  arithmetic_mismatch: { title: "Total incurred does not reconcile", certainty: "certain",
    why: "Paid to date + reserve (+ fees/expenses where reported) should equal total incurred. A gap can mean a keying error, a missing component or an unreported movement.",
    next: "Compare both sides of the sum shown, then query the sender for the component that differs." },
  date_order: { title: "Dates out of order", certainty: "certain",
    why: "A claim notified before its date of loss usually indicates a keying error.",
    next: "Confirm the correct dates with the sender." },
  date_in_future: { title: "Date in the future", certainty: "certain",
    why: "Future dates are almost always keying errors and distort reporting periods.", next: "Correct with the sender." },
  invalid_currency: { title: "Unrecognised currency code", certainty: "certain",
    why: "Amounts cannot be totalled or converted without a valid ISO currency.", next: "Ask for the ISO 4217 code." },
  currency_inconsistency: { title: "Claim reported in several currencies", certainty: "signal",
    why: "The same claim reference appears with different currencies, which may be a genuine change or an error.",
    next: "Check whether the currency changed legitimately." },
  invalid_status: { title: "Unrecognised claim status", certainty: "certain",
    why: "Status drives open/closed segregation; an unknown value cannot be classified.",
    next: "Map the sender's status value or ask them to use a standard one. Accepted values are configurable." },
  schema_violation: { title: "Value could not be read as the expected type", certainty: "certain",
    why: "The value in this cell does not match its column's type, so it was excluded from checks on this row only.",
    next: "Correct the cell at source; the rest of the file was processed." },
  mapping_completeness: { title: "Sheet only partly mapped", certainty: "signal",
    why: "Few columns on this sheet matched a known field, so findings on it may reflect mapping gaps rather than bad data.",
    next: "Review this sheet's mapping and re-process." },
  exact_duplicate: { title: "Exact resubmission", certainty: "certain",
    why: "Same claim reference, same reporting period and identical amounts and status: the row was sent twice.",
    next: "Confirm, then ask the sender to withdraw the repeat. Nothing is removed automatically." },
  probable_duplicate: { title: "Probable duplicate", certainty: "signal",
    why: "Similar insured names with close loss dates under different references. Similarity is evidence, not proof.",
    next: "Compare the two rows side by side before acting." },
  repeat_period_unknown: { title: "Repeat with no reporting period", certainty: "unknown",
    why: "The same claim appears on several sheets and no period is present, so TrueBind cannot tell a duplicate from development.",
    next: "Map a period column, or confirm manually." },
};

export function findingGuide(rule: string | null | undefined, status?: string): FindingGuide {
  if (status === "NOT_EVALUABLE") {
    return { title: "Could not be checked", certainty: "unknown",
      why: "A required input for this check was missing or unreadable, so TrueBind did not guess a result.",
      next: "Map or supply the missing input and re-process." };
  }
  return GUIDES[rule ?? ""] ?? { title: (rule ?? "Finding").replace(/_/g, " "), certainty: "signal",
    why: "See the message for the evidence recorded on this row.", next: "Review the source row." };
}
