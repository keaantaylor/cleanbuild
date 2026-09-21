# Handoff: Truebind upload fix + visual redesign

Read this before touching anything. `PROJECT_STATE.md`, `DECISIONS.md` and
`TODO.md` in this same directory are the other three files — read all four
before starting new work. This file covers one work session; it will get
long over time, so trim completed items into `PROJECT_STATE.md` once
they're no longer "recent."

---

## Session 2 (same day, follow-up work) — repeated-header-row bug, contrast audit, drill-down

Three asks, all completed and tested. Session 1's notes (below the divider)
are still accurate background reading; this section only covers what
changed *since* that commit.

**1. Fixed: a header row repeated mid-sheet was ingested as a fake claim.**
Root-caused: no row-filtering existed at all for blank/subtotal/repeated-
header rows in `bordereaux/src/bordereaux/ingest.py` prior to this session
(the task brief that prompted this assumed such filtering already existed
and just needed a repeated-header case added — it didn't, so this session
built the whole thing: `ExcludedRow` dataclass, `_classify_row()` with
blank/repeated-header/subtotal detection using the same normalized
(trim/collapse-whitespace/casefold, NFKC for non-breaking spaces) compare
already used for header-alias matching, wired through
`SheetData.excluded_rows` → `WorkbookCoverage.excluded_rows` →
`_coverage_line()` and a new "Excluded rows" sheet in the Excel report.
Applies to both the openpyxl/xlrd workbook path and the CSV path.
Regression test: `bordereaux/tests/test_row_exclusion.py` (also generates
its own fixture, `bordereaux/tests/fixtures/repeated_header_block.xlsx`).

**2. Contrast audit.** Two real WCAG AA failures found by actually
computing ratios (not guessing): `--color-text-tertiary` was 2.5:1 on
white (needs 4.5:1) despite being used as real text (row metadata, field
codes, tab counts) — fixed to `#69737F` (light mode only; dark mode's
`#94A3B8` was already fine). Also: `--color-grade-3` and `--color-grade-2`
were only 9° apart in hue (and grade-3 was the literal same hex as generic
`--color-warning`), making a 3/5 vs 2/5 grade hard to tell apart at a
glance — re-spaced across the full green→red run to ~27-31° apart
(`--color-grade-3: #7E7407`, `--color-grade-2: #B85B0A`, plus matching
dark-mode `--color-grade-3: #FBDE23`). `lib/colorContrast.ts`'s pair list
updated to match and to actually check text-tertiary (it wasn't checked
before despite being real text). Every other existing color pair was
already passing AA — this was not a wholesale palette problem, just these
two specific gaps.

**3. Explanations + drill-down.** The "Not evaluable" count was previously
an aggregate-only number with zero row-level detail anywhere (a real gap,
confirmed by reading `persistence_service.py`'s own comment on
`Report.arithmetic_not_evaluable` acknowledging it). Added
`bordereaux.validation.ValidationResult.not_evaluable_detail` (a DataFrame
kept deliberately separate from `exceptions` so it doesn't affect
composite scoring — a not-evaluable row is "insufficient information," not
"wrong data"), with four distinct reasons
(incurred_unmapped/paid_and_reserve_unmapped/incurred_blank/paid_and_reserve_blank).
Persisted into the existing `ValidationResult` SQL table using its
already-defined-but-unused `status="NOT_EVALUABLE"` value (check_type
stays `"ARITHMETIC"`) — no new table needed for this part. `/exceptions`
now takes a `status` query param; the Exceptions page has a "Not
evaluable" tab alongside "Arithmetic mismatch" (deliberately split so a
real defect and "we couldn't check" never look like the same thing) and
switched its tab-counting to filter a single already-fetched list
client-side (fixed a real pre-existing bug where switching tabs made every
*other* tab's count reflect whichever filter was previously active).
Excluded rows (from fix #1) needed a genuinely new table
(`excluded_rows`, migration `f9495471daf3`) since they never become a
`ClaimRow` — new `GET /reports/{id}/excluded-rows` endpoint, new
`ExcludedRowsPanel` component (expandable per-row, grouped by sheet) on
the report detail page. Added tooltips (reused the existing `Tooltip`
component, not a new pattern) explaining every headline metric, the
composite-score formula and grade bands, and per-field completeness
percentages. Found and fixed a real bug in `Tooltip.module.css` while
adding longer explanation text: the bubble inherited `text-transform:
uppercase` from ancestor label elements and used `white-space: nowrap`,
so a long tooltip rendered as one giant unreadable all-caps line — fixed
to wrap normally with a 320px max-width.

**Verified:** full `bordereaux` test suite (8 scripts) + `truebind-web`
backend pytest (9 tests, 2 new) + frontend `tsc`/`next build` (contrast
validator included) all pass. Manually walked the real upload → mapping →
process → Reports → Exceptions flow through actual dev servers with two
fixtures (the 10-sheet `test_boundary_cases.xlsx` for realistic flagged
data, and the new `repeated_header_block.xlsx` for the not-evaluable +
excluded-rows drill-down specifically) and screenshotted every new UI
surface.

**Not done / next session:** the Duplicates and Audit screens didn't get
their own explanation/tooltip pass (Reports and Exceptions did) — if a
future session wants full drill-down parity, those are the two screens
left. The pre-existing "Missing mandatory: 68 vs tab count 74" mismatch
(distinct-rows vs distinct-exceptions counting, see `TODO.md`) was
noticed but not fixed — it predates this session and wasn't part of what
was asked.

---

## Repo shape (read this first if you're new here)

There are **two separate applications** in this repo, not one:

- `bordereaux/` — the original Streamlit app. Contains the actual claims
  pipeline (ingest, mapping, validation, dedupe, health report) as a
  plain, Streamlit-free Python package in `bordereaux/src/bordereaux/`.
  Has its own test suite (`tests/test_phase{2..6}.py`,
  `test_boundary_fixture.py`, and now `test_legacy_formats.py`).
- `truebind-web/` — a from-scratch Next.js (App Router, TypeScript) +
  FastAPI redesign, added in a later commit. It **imports `bordereaux`
  directly** (`truebind-web/backend/app/services/pipeline_service.py`)
  instead of reimplementing the pipeline. Do not duplicate pipeline logic
  into the FastAPI layer — fix it in `bordereaux/src/bordereaux/` and both
  apps pick it up.

**The user's complaints in this task ("generic UI", "drag-and-drop upload
fails") were about `truebind-web/`, not the Streamlit app.** The Streamlit
app was not touched this session and there is no evidence it has the same
bug (it's a different upload code path, but calls the same
`bordereaux.ingest` module underneath, so the underlying fix helps it too
— just wasn't verified through the Streamlit UI specifically).

## What was investigated

1. Read both READMEs, both apps' structure, `pipeline_service.py`'s
   docstring explaining the reuse decision.
2. Traced the upload flow end-to-end: `FileUpload.tsx` (drag/drop +
   file input) → `lib/api.ts` `uploadReport()` → FastAPI
   `POST /api/v1/reports/upload` (`backend/app/routes/upload.py`) →
   `pipeline_service.load_workbook()` → `bordereaux.pipeline.load_workbook`
   → `bordereaux.ingest.load_workbook_sheets()`.
3. Built a real Python 3.11 venv, installed both apps' requirements
   (pandas resolved to **3.0.5** — no upper bound pin anywhere; see
   `DECISIONS.md`), ran the actual FastAPI server + Next.js dev server
   together, and drove the real HTTP API and a real Chromium browser
   (Playwright, pre-installed at `/opt/pw-browsers/chromium`) through the
   full upload → mapping → confirm → process flow.
4. Every synthetic fixture in `bordereaux/data/synthetic/` (including the
   10-sheet `test_boundary_cases.xlsx`) uploaded, mapped and processed
   correctly through the real API before any fix was applied — so the
   pipeline itself was not broadly broken.
5. Root-caused the actual defect by generating a **genuine legacy binary
   `.xls`** file with `xlwt` (not just an xlsx renamed to `.xls`) and
   feeding it through `bordereaux.ingest.load_workbook_sheets()` directly:

   ```
   openpyxl.utils.exceptions.InvalidFileException: openpyxl does not
   support the old .xls file format, please use xlrd to read this file,
   or convert it to the more recent .xlsx file format.
   ```

   Both the frontend's `accept=".xlsx,.xls,.csv"` and the backend's
   `ALLOWED_SUFFIXES = (".xlsx", ".xls", ".csv")` **advertised `.xls`
   support that never actually existed** — `ingest.py` only ever called
   `openpyxl.load_workbook`, unconditionally, for anything that wasn't
   `.csv`. A user with a real old-format Excel bordereau (very common for
   legacy market bordereaux — exactly the audience this product is for)
   would see exactly what was reported: drop the file, get an error.

## What was changed

**Bug fix** (`bordereaux/src/bordereaux/ingest.py`):
- Added `_iter_legacy_xls_rows()`, using `xlrd` (newly added dependency,
  `bordereaux/pyproject.toml`) to read real `.xls` workbooks, normalizing
  its cell output (blank → `None`, date cells → `datetime`) to match what
  `openpyxl.iter_rows(values_only=True)` already produced, so
  `_build_sheet_data()` (header detection, dedup) doesn't need to know
  which library produced a row.
- `load_workbook_sheets()` and `load_raw()` now dispatch on extension:
  `.csv` → existing pandas path (unchanged), `.xls` → the new xlrd path,
  everything else (`.xlsx`, `.xlsm`) → the existing openpyxl path
  (unchanged).
- Added `.xlsm` to both the frontend's `accept` attribute
  (`FileUpload.tsx`) and the backend's `ALLOWED_SUFFIXES`
  (`upload.py`) — same class of bug (openpyxl already handles `.xlsm`
  fine, it's the same zip/XML container as `.xlsx`; only the filename
  gate was too narrow), same one-line fix, so it was folded into this
  pass rather than left as a second round-trip. See `DECISIONS.md` for
  why this was judged in-scope.
- Added `bordereaux/tests/test_legacy_formats.py` plus two new binary
  test fixtures (`bordereaux/tests/fixtures/legacy_sample.xls`, genuinely
  BIFF/CDFV2, and `macro_enabled_sample.xlsm`) — regression coverage for
  exactly this defect class. Run with
  `python3 bordereaux/tests/test_legacy_formats.py`.

**Frontend redesign** (`truebind-web/frontend/`) — see `DECISIONS.md` for
the design rationale. Summary of files touched:
- `styles/variables.css`, `styles/globals.css` — added a serif
  `--font-display` token (system stack, no webfont/network dependency) for
  headings, kept sans for body/controls and the existing mono for tabular
  figures; added `.eyebrow` and `.stepList`/`.stepNumber` utility classes.
- `components/ui/Badge.module.css` — status badges are now hairline-bordered
  tags (radius-xs, transparent/hollow fill) instead of solid pill chips,
  so no state (including UNMAPPED/MISMATCH) reads as a "clean pass" via a
  cheerful filled color.
- `components/ui/Button.module.css`, `Card.module.css`/`Card.tsx`,
  `Table.module.css`, `Tabs.module.css` — flattened corners, removed
  boxed "metric card" treatment in favor of a typographic stat block (top
  rule + label + tabular numeral), uppercase-tracked table headers.
- `components/layout/Sidebar.tsx`/`.module.css` — removed emoji nav icons,
  serif wordmark, thin left-rule active state instead of a filled pill.
- `components/upload/FileUpload.tsx`/`.module.css`,
  `SheetsList.tsx`/`.module.css`,
  `app/(dashboard)/upload/page.tsx`/`.module.css` — rebuilt to match the
  brief's mockup structure: "STEP ONE OF THREE" eyebrow, "Bring any
  bordereau." headline, restrained dropzone, 01/02/03 numbered explainer.
  Per-sheet rows now read `{name} / {rows} rows · header line {n} [·
  mapped]` per the brief's example.
- `components/report/*`, `app/(dashboard)/{reports,exceptions,duplicates,
  todo,audit}/*` — same typographic system applied for consistency
  (eyebrow + h1 headers, hairline dividers instead of boxed sections
  where the box wasn't load-bearing).
- Every other page/component not listed was left as-is; they already
  consumed the shared atoms (`Table`, `Badge`, `Button`, `ReportPicker`)
  so the visual language propagated without needing per-page rewrites.

## What is now working (verified, not assumed)

- `python3 bordereaux/tests/test_phase{2,3,4,5,6}.py`,
  `test_boundary_fixture.py`, `test_legacy_formats.py` — all pass.
- `cd truebind-web/backend && pytest tests/ -v` — all 7 pass (these run
  the real upload→confirm→process flow through the FastAPI `TestClient`).
- `cd truebind-web/frontend && npx tsc --noEmit` — clean.
- `cd truebind-web/frontend && npm run build` — succeeds, including the
  build-time WCAG-AA contrast validator
  (`lib/colorContrast.ts` via `app/layout.tsx`) which throws on failure.
- Manually verified via a real Chromium browser (Playwright) driving the
  actual dev servers: uploaded a clean `.xlsx`, a genuine legacy `.xls`
  (via a simulated real `drop` `DataEvent`, not just the file input), a
  `.xlsm`, a `.csv`, and the 10-sheet `test_boundary_cases.xlsx` — all
  parsed, showed correct per-sheet mapping proposals, confirmed, and
  processed to a health report with no console errors and no failed
  network requests.
- Screenshotted every redesigned screen (upload landing, mapping
  confirmation, report detail, exceptions, duplicates, to-do, audit) at
  1440px to confirm the new visual language renders correctly, not just
  that the CSS compiles.

## What is still broken / not done

- **Legacy `.xls` fix was not verified through the Streamlit app's own
  upload path** (`bordereaux/app.py`) — only through direct
  `bordereaux.ingest` calls and through `truebind-web`'s FastAPI/Next.js
  stack. Since both call the same `bordereaux.ingest.load_workbook_sheets`,
  it should work there too, but this was not run end-to-end through
  Streamlit's `st.file_uploader`. Worth a quick manual check
  (`streamlit run bordereaux/app.py`) before calling that surface done.
- **Duplicates/Exceptions/To-do/Audit screens got the shared design
  system applied but were not individually redesigned beyond that** — no
  populated screenshot exists for Duplicates or Exceptions with real
  flagged data (the test fixture used for screenshots was a clean file
  with zero exceptions/duplicates). Worth re-screenshotting with
  `bordereaux/data/synthetic/test_boundary_cases.xlsx` once uploaded,
  which does have real arithmetic mismatches, missing-mandatory rows and
  probable duplicates, to sanity-check the MISMATCH/duplicate-comparison
  visual treatment under real flagged data.
- **`pandas>=2.2` has no upper bound** anywhere and resolved to `3.0.5` in
  this session's fresh install — it happened to work (full test suite
  green), but pandas 3.0 is a major version with real breaking changes
  upstream and this wasn't a deliberate upgrade decision by anyone. See
  `DECISIONS.md` and `TODO.md`.
- **No `next/font` webfont was added** — the serif is a system font stack
  (Georgia/Cambria/Iowan Old Style fallback chain), not a loaded webfont.
  This was a deliberate choice to avoid a build-time network dependency,
  not an oversight — but it means the typographic voice depends on
  whatever serif the visiting OS actually has. See `DECISIONS.md` if a
  future session wants to revisit this with a real webfont.
- Auth is still `web_user` for every action (pre-existing, out of scope
  this session, noted in `truebind-web/README.md` already).
- Payment-leakage detection, the Lloyd's v5.2 template, and the PDF
  governance pack are still not ported into `truebind-web` (pre-existing,
  documented in `truebind-web/README.md`).

## Do NOT redo

- Do not re-investigate "why does upload fail" — it's the `.xls`/openpyxl
  gap documented above, already fixed and tested. If a *new* upload
  failure is reported, get the actual file and actual error first; don't
  assume it's the same bug.
- Do not reimplement the bordereaux pipeline inside
  `truebind-web/backend` — `pipeline_service.py` is a deliberate thin
  wrapper (see its own docstring). Fix bugs in `bordereaux/src/bordereaux/`.
- Do not add `xlrd` usage anywhere except `ingest.py`'s `.xls` branch —
  `xlrd` dropped `.xlsx` support in v2.0, it must never be used for the
  zip/XML formats.
- Do not reintroduce pill-shaped filled badges, emoji nav icons, or
  boxed-single-stat "metric cards" — these were deliberately removed per
  the design brief in `DECISIONS.md`. If a future change needs a new
  status indicator, extend `Badge`/`statusBadges.tsx`, don't invent a
  parallel pattern.
- Frontend/backend dev servers were run from a scratch venv at
  `/tmp/tbvenv` (outside the repo, not committed) for testing this
  session — that venv does not persist between sessions; recreate it
  (`pip install -r truebind-web/backend/requirements.txt`) rather than
  looking for it.
