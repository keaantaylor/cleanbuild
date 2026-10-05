# Competitive-advantage rebuild: Phase 5 (workbook as product + connectors), branch `rebuild`

| Area | Change |
|---|---|
| Workbook view | The report now opens on the workbook. Rows and columns are virtualised (tiles of 100 rows x 40 columns; a large sheet keeps under 1,500 cells in the page). Sheet tabs; frozen column letters, the sheet's own header row and row numbers; search across values and formulas; "rows with issues only"; range selection with count and sum; keyboard navigation (arrows, Shift, PageUp/Down, Ctrl+Home/End, Tab, Ctrl+F, Alt+N/P for next/previous issue); column resize. No new dependency |
| Cell states | Verified / Requires reconciliation / Undetermined, always as words (legend, cell title, inspector) with a left bar and tint, never colour alone |
| Inspector | Value, formula, state, each issue with expected / actual / difference and rule + version, known exceptions; propose a correction (policy shown), approve or reject inline, with the re-check result |
| Issue to cell | "Show in workbook" in the review queue switches sheet and selects the exact cell |
| Grid service | Values and formulas cached separately (formulas show their calculated value, the formula in the inspector); up to 1,000 columns; tiles by row and column range or explicit rows; search and issue-cell endpoints |
| Connectors | One interface, two providers: Microsoft 365 (Graph, app-only: "Open in Excel") and Google Sheets (service account). Open uploads a new file and never overwrites the source; "Read edits" turns changed cells into PROPOSED corrections under the execution policy (formulas, headers, claim references refused); "Write back" uploads the working copy as a new version. Credentials from server environment only, never stored or returned. Migration 0024 |

Checks: backend 412 passed (1 Windows-only memory-limit test); engine 100; frontend lint, typecheck, 24 unit, build OK; e2e 10/10, incl. a new workbook spec (virtualised DOM, keyboard, next issue, issue to cell). The golden-flow and checks specs were updated for the new report tabs (they had been out of date since Phase 1).
Left: connectors are verified with mocked Graph/Drive transports, not against live tenants (needs M365_* / GOOGLE_* credentials); connections are server-wide, not per organisation; Google write-back over a converted sheet is best-effort; no cell editing in the grid itself (corrections go through the inspector).
