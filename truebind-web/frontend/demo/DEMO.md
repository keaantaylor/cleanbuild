# TrueBind product demo (60 seconds)

> TrueBind takes messy insurance bordereaux and turns them into structured, validated and reviewable data with a clear audit trail.

Recorded from the real application (branch `rebuild`, production build of the frontend, real API) running locally on a throwaway SQLite database. Nothing touches truebind.ie, which still runs the older `main` build without the Workbook and Review views.

## Re-record

```sh
cd truebind-web/frontend
MSYS_NO_PATHCONV=1 NEXT_PUBLIC_API_URL=/api/v1 TRUEBIND_API_ORIGIN=http://127.0.0.1:8766 npm run build
FFMPEG=/path/to/ffmpeg TRUEBIND_PYTHON=../backend/.venv/Scripts/python.exe \
  npx playwright test -c demo/playwright.demo.config.ts        # DEMO_PACE=0.5 for a quick rehearsal
```

Output in `demo/output/` (git-ignored): `truebind-demo.mp4` (H.264, 1920x1080, 30 fps, from a CDP screencast), `shots/*.png`, `timeline.json` (time of each moment in the raw take), and Playwright's own WebM as a fallback. On Windows also set `PLAYWRIGHT_CHROMIUM_EXECUTABLE` if Playwright's pinned Chromium is missing.

## Safety

- Demo account `analyst@demo.truebind.example` / organisation "Demo Syndicate", created by the script in a fresh local database each run. No real person, customer, credential or key.
- No AI provider: `ANTHROPIC_API_KEY` is empty, so mapping uses the deterministic alias rules and nothing leaves the machine.
- `demo/pyshim/sitecustomize.py` gives the local worker a neutral name, so the audit trail shows `truebind-worker`, not the recording machine's host name.

## Workbooks (synthetic, deterministic)

| File | Rows | Use |
|---|---|---|
| `workbooks/Coastline_MGA_Claims_Bordereau_Sep_2026.xlsx` | 5,022 claims, 150 planted problems | The file uploaded on camera |
| `workbooks/Harbour_MGA_Claims_Bordereau_Aug_2026.xlsx` | 242 claims | Seeded off camera, so the overview has history |

Generated with `backend/tests/fixtures/generate_bordereau.py --rows 5000 --seed 7 --rate 0.03` (and `--rows 240 --seed 11 --rate 0.02`). Same seed, same content; each has an answer key (`*.answers.json`) listing every planted problem with its cell. The files themselves are committed, so the SHA-256 shown in the lineage view is always `1bc02835…`. They look like a coverholder's monthly file: a title row, headers such as "Pol No." and "Date Rptd", mixed currencies, a subtotal row, plus Summary and Notes tabs that TrueBind recognises as non-claims and skips.

## Journey and shot list

Raw take is about 2:06; the cut is about 60 s. "Raw" is the time in `truebind-demo.mp4`.

| # | Cut | Raw | Screen | What it shows | Screenshot |
|---|---|---|---|---|---|
| 1 | 0-4 s | 0-6 s | Sign in | Demo analyst signs in | `01-login.png` |
| 2 | 4-9 s | 12-16 s | Overview | What needs attention today, files, open findings | `02-overview.png` |
| 3 | 9-17 s | 16-21 s, 35-41 s | Intake and mapping | Sender typed, file dropped; "13 columns mapped automatically · nothing to decide"; Summary and Notes tabs skipped with the reason. Cut the 15 s read in between | `03-mapping.png` |
| 4 | 17-22 s | 41-48 s (speed up the rest, to 76 s) | Processing | The engine's real stages: 5,022 rows read, validating, duplicates, building the report | `04-processing.png` |
| 5 | 22-34 s | 76-93 s | Workbook | The spreadsheet itself, every flagged cell named. Next issue: Claims!C7, "Requires reconciliation: required data missing", rule and version. Then rows with issues only | `05-workbook-issue-cell.png`, `05b-workbook-issues-only.png` |
| 6 | 34-41 s | 93-101 s | Review issues | One decision per root cause: "Issue 1 of 14", rows and money affected, every affected cell, Send to sender / Override | `06-review-root-cause.png` |
| 7 | 41-49 s | 101-111 s | Health check | Verdict, errors / warnings / couldn't check, top fixes with the exact cell and money at stake | `07-health-check.png` |
| 8 | 49-52 s | 111-117 s | Mapping | Field completeness, unmapped fields named, row reconciliation 5,023 source rows -> 5,022 claims + 1 excluded | `08-mapping-completeness.png` |
| 9 | 52-56 s | 117-122 s | Lineage | Source file SHA-256, sender, programme, every recorded step, processing history with timings | `09-lineage.png` |
| 10 | 56-60 s | 122-126 s | Audit trail | Hash chain intact, every action with who did it | `10-audit-trail.png` |

Suggested captions (one per shot, plain): "A coverholder's monthly bordereau" · "Columns mapped, non-claims tabs set aside" · "Every row validated and reconciled" · "Each problem on its exact cell" · "One decision per cause, not per row" · "A health check the sender can act on" · "What was mapped, what was not" · "Where every number came from" · "Every step recorded and hash-chained".

## Notes for the edit

- The two waits (reading the 5,000-row file, about 15 s; processing and the first load of the workbook, about 30 s) are real. Cut or speed them up; do not imply they are instant.
- The pointer is a recording overlay (headless Chromium draws none). It is not part of the product.

## What the take shows (same every run)

5,022 claim rows read; 13 columns mapped automatically, nothing to decide; Summary and Notes tabs set aside; 165 findings (116 errors on 105 rows, 49 warnings) reduced to 14 review decisions; verdict "Fix before submitting"; 5,023 source rows reconcile to 5,022 claims + 1 excluded total line; audit chain intact.

## UI issues found while recording

Fixed (a defect in the Phase 5 grid, committed separately):
- The workbook's first load on a 5,000-row file took 124 s and the page showed "Request timed out after 30s". Cause: the grid read 1,000 columns on every row, and parallel tile requests each rebuilt the cache. It now reads only the sheet's own width, and builds once behind a lock: about 5 s cold, 0.1 s after.

Fixed after the first takes:
- Workbook view: a loading state ("Loading the sheet…") instead of an empty frame reading "0 rows · 0 columns".
- Top bar: solid background; content no longer shows through it when scrolling.
- Counts with their noun everywhere on the overview and processing screens ("1 critical finding", "2 duplicate candidates"), never "finding(s)".
- Binder (and other) checks that were not assessed: one sentence with one full stop, no repeated reason, no table of zeros, no "No findings - nothing was assessed yet."

Not fixed (reported):
1. The audit trail and lineage show the worker's host name ("claimed by <host>:<pid>:..."): a real machine or user name in production. Worked around for the demo only.
2. Lineage: "Received 21:43" but "Retained until ... 20:43": two time zones on one panel.
3. Audit trail: raw field codes ("Mapping confirmed: CR0110CM", "TB_BINDER_REF"), generic "module run" entries, actor emails truncated ("analyst@demo.true").
4. The breadcrumb says "Health Check" on the Workbook and Review tabs.
5. The verdict says "The grade is provisional: at least one sheet was only partly understood" although every required field on Claims is mapped (9 optional fields are not); easy to misread on camera.
6. Mapping review with nothing to decide still shows the table header over an empty body, and the Claims sheet keeps a warning icon and "13/22 fields".
7. Review card for missing data shows Expected / Actual / Difference columns that are all "-".
8. The workbook's frozen header repeats the sheet's own header row, which also appears as row 2.
9. Leakage card text is dense and technical ("0 assessed, 5022 not assessed (Reporting period, Paid this month - indemnity not mapped ...").
10. The checks under "Other checks & evidence" load a few seconds after the tab opens and push the lineage section down.

From the intended journey, everything exists in the current UI: sign in, overview, upload, processing, health check, findings, mapping and unmapped fields, source traceability (lineage with file hash), audit trail.
