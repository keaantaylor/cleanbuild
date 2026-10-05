# Competitive-advantage rebuild: Phase 2 (reconciliation core), branch `rebuild`

| Type | State |
|---|---|
| Arithmetic, cross-column, tolerance | Existing (incurred = paid + reserve, paid <= incurred, dates, 0.01 tolerance); unchanged |
| Totals vs detail | New `totals_mismatch`: each total/subtotal line against its section or everything above it (tolerance 0.005 per row); finding points at the total line's cell |
| Cross-sheet | New `cross_sheet_conflict`: same claim and known period on two sheets with different paid, reserve or incurred |
| Current vs previous submission, record-level | New `paid_decreased`, `rollforward_break`: claim-by-claim match with the latest earlier processed file from the same sender (skipped when the sender is unknown, or the currency changed). Evidence names the previous file, sheet and row |
| Duplicates, near-duplicates, development, reference data | Existing (exact/probable duplicates, development pairs, ISO 4217, status list); unchanged |
| Re-check after corrections | Approving a correction, a bulk safe fix and building a version re-run every check on the corrected workbook. Fixed only if the rule stops firing on that cell; otherwise reopened with expected/actual. New findings on touched rows reported. Audited |

All four new rules are deterministic, versioned (ruleset 2026.10.2), and carry expected, actual, difference and the source cell. No AI is used for any of them.
False positives: none of the new rules fired on the 4 regression replicas or the generated 500-row file (finding counts unchanged).
Limits: health score is computed by the engine before previous-submission findings are added, so those two rules show as issues but do not move the score. Reconciliation against a summary SHEET (not a total line) is not yet covered.
Checks: engine 100 passed; backend 397 passed (1 Windows-only memory-limit test fails); frontend lint, typecheck, 24 unit, build OK. Windows test shim as in Phase 1. Not deployed.
