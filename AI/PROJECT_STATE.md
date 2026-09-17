# Project state: Truebind

Snapshot of what the application actually is and does right now. Update
this file (not just `HANDOFF.md`) whenever a session changes the
architecture, the data model, or what's built vs. deferred — `HANDOFF.md`
is a session diary and gets pruned; this file is the durable reference.

## Two applications, one shared pipeline

```
cleanbuild/
├── bordereaux/                 Original Streamlit app + the shared pipeline
│   └── src/bordereaux/         ingest, mapping, validation, dedupe, report,
│                                schema, iso4217 -- plain Python, no
│                                Streamlit imports. This is the product's
│                                actual business logic.
│   └── app.py                  Streamlit UI over the above
│   └── tests/                  test_phase{2..6}.py, test_boundary_fixture.py,
│                                test_legacy_formats.py
└── truebind-web/                Next.js + FastAPI redesign, imports
    ├── backend/app/             `bordereaux` directly rather than
    │   services/pipeline_service.py   reimplementing it
    ├── backend/app/models/       SQLAlchemy: reports, sheets, mappings,
    │                              claim_rows, validation_results,
    │                              leakage_flags, obligations, alerts,
    │                              templates, audit_log
    ├── backend/app/routes/       upload, mapping, reports, exceptions,
    │                              duplicates, obligations, alerts, audit,
    │                              templates
    └── frontend/                 Next.js 16 App Router, TypeScript,
        app/(dashboard)/          CSS Modules (no component library) --
                                   upload, reports, exceptions, duplicates,
                                   audit, todo
```

**Both apps are live products, not one superseding the other.** The
Streamlit app is "kept as-is and still fully working" per its own README;
`truebind-web` is a separate, parallel redesign covering the same
"Phase 0" flow (upload → mapping → health report → exceptions →
duplicates → audit → to-do) with a real Postgres/SQLite-backed API instead
of Streamlit's in-memory session state.

## Upload → processing flow (truebind-web)

1. `POST /api/v1/reports/upload` (multipart file) — validates extension
   (`.xlsx`, `.xlsm`, `.xls`, `.csv`), writes to a temp file, calls
   `bordereaux.pipeline.load_workbook()` (→
   `bordereaux.ingest.load_workbook_sheets()`), which returns one
   `SheetData` per sheet (header row auto-detected, skipped sheets
   flagged with a reason, never silently dropped). Also proposes a column
   mapping per sheet (`propose_mapping_for_workbook`, alias/fuzzy + AI
   fallback if `ANTHROPIC_API_KEY` is set). Persists a `Report` row + one
   `Sheet` row per sheet + one `MappingField` row per canonical field per
   sheet.
2. `GET /reports/{id}/sheets` — per-sheet status (`PENDING_CONFIRMATION`,
   `CONFIRMED`, `SKIPPED`), row count, detected header row.
3. `GET/POST /reports/{id}/sheets/{name}/mapping[/confirm]` — the
   mapping-confirmation screen: shows each canonical field's proposed
   source column, mapping state (`MAPPED_BY_ALIAS`/`MAPPED_BY_AI`/
   `UNMAPPED`/`MANUAL`), confidence, sample values; user can override or
   leave unmapped; nothing is processed until every sheet is confirmed.
4. `POST /reports/{id}/process` — rejects if any sheet is still
   `PENDING_CONFIRMATION`; otherwise runs
   `bordereaux.pipeline.run_workbook_pipeline()` (validation, dedupe,
   health-report scoring) and persists `ClaimRow`/`ValidationResult`
   rows.
5. `GET /reports/{id}/summary` — the health-report numbers the Reports
   screen renders (coverage, grade, missing-mandatory count, arithmetic
   mismatch/not-evaluable counts, duplicate counts, per-field
   completeness).

## Canonical field model

`bordereaux/src/bordereaux/schema.py` is the single source of truth for
the 10 canonical fields (claim reference, insured name, claim status,
date of loss, date first notified, policy reference, paid/reserve/
incurred amounts, currency) and their requiredness tier (unconditional /
conditional-pair / reconciled / optional). This already matches the
brief's canonical-field list; nothing needed to change here. Do not
duplicate this list elsewhere — both apps import `schema.FIELDS`.

## Mapping states (tri-state + manual)

`MappingState` (`frontend/lib/types.ts`) = `MAPPED_BY_ALIAS |
MAPPED_BY_AI | UNMAPPED | MANUAL`. Rendered via `MappingStateBadge`
(`components/ui/statusBadges.tsx`) with a glyph per state (●/◐/▲/◆) — this
was already correct before this session's redesign; the redesign only
changed the badge's visual treatment (hairline tag, not filled pill), not
the state model.

## Row exclusion (blank / subtotal / repeated header)

Before a sheet's data rows reach mapping/validation, each is classified
(`bordereaux/src/bordereaux/ingest.py`: `_classify_row()`) as blank,
subtotal/total, a repeated copy of the sheet's own header row, or genuine
data. Excluded rows are never counted as claims and never flagged as
validation exceptions; they're tracked separately
(`SheetData.excluded_rows` → `WorkbookCoverage.excluded_rows`) and
reported by name/count in the coverage line and a dedicated "Excluded
rows" sheet in the Excel export. In `truebind-web`, they're persisted to
their own `excluded_rows` table (they never become a `ClaimRow`, so they
can't hang off `ValidationResult`) and exposed via
`GET /reports/{id}/excluded-rows`, rendered as an expandable panel
(`ExcludedRowsPanel`) on the report detail page.

## Validation outcomes

`CheckType` = `MANDATORY_FIELD | ARITHMETIC | DUPLICATE |
MAPPING_COMPLETENESS`. Arithmetic reconciliation (paid + reserve ==
incurred) is a three-outcome check — match / mismatch / **not evaluable**
(when a required operand was never mapped, or blank/unparseable on that
row) — not a boolean pass/fail; "not evaluable" is a visually distinct
violet family (`--color-not-evaluable`), never rendered as a pass. The
three-outcome logic itself (`bordereaux/src/bordereaux/validation.py`)
predates this session, but per-row drill-down into *why* a row is not
evaluable (`ValidationResult.not_evaluable_detail`, four distinct reasons)
was added in session 2 — previously only the aggregate count existed.
Persisted using `ValidationResult.status = "NOT_EVALUABLE"` (a value the
SQL model already declared but nothing wrote until session 2) with
`check_type` still `"ARITHMETIC"`; kept out of the `exceptions` DataFrame
bordereaux scores against, so it doesn't penalize the composite score
(see `DECISIONS.md`). The `/exceptions` API takes a `status` filter; the
Exceptions screen has a dedicated "Not evaluable" tab, deliberately
separate from "Arithmetic mismatch."

## Design system (as of this session)

- Typography: serif `--font-display` (system stack: Iowan Old Style /
  Georgia / Cambria fallback, no webfont) for headings and eyebrows, sans
  for body/controls, mono for tabular figures (amounts, counts, IDs).
- Status badges: hairline-bordered tags (`--radius-xs`), never a filled
  pill, always paired with a glyph (●/▲/✕/◐/◆/?/⧉).
- Stat display: typographic block (uppercase label + tabular numeral +
  hairline top rule), not a bordered "card" — used for the Reports
  screen's four top-line metrics.
- Color tokens: session 1 changed only *how* colors are applied (border
  vs. fill), not the values. Session 2 fixed two actual value defects
  found by computing real contrast ratios: `--color-text-tertiary` was
  2.5:1 on white against a 4.5:1 AA requirement (now `#69737F`), and
  `--color-grade-3`/`--color-grade-2` were only 9° apart in hue with
  grade-3 sharing an exact hex with generic `--color-warning` (now
  `#7E7407`/`#B85B0A`, re-spaced ~27-31° apart across the full grade
  ramp). `lib/colorContrast.ts` is the enforcement mechanism — it throws
  at `app/layout.tsx` import time if any listed pair fails, and is the
  first place to check before changing any color token.
- Full rationale for every above choice: `DECISIONS.md`.

## Known deferred scope (pre-existing, not this session's problem)

- Payment-leakage detection, Lloyd's v5.2 template, PDF governance pack:
  exist in the Streamlit build's `claude/great-gauss-082g8l` branch, not
  yet ported to `truebind-web`.
- Sanctions/PEP screening, technical account reconciliation: Phase 2 of
  the original brief, not started anywhere.
- Auth: every action logs as `web_user`; no real multi-user identity.
- Production deployment: `truebind-web/docker-compose.yml` covers local
  dev only.
