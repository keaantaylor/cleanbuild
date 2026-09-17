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

## Validation outcomes

`CheckType` = `MANDATORY_FIELD | ARITHMETIC | DUPLICATE |
MAPPING_COMPLETENESS`. Arithmetic reconciliation (paid + reserve ==
incurred) is a three-outcome check — match / mismatch / **not evaluable**
(when a required operand was never mapped) — not a boolean pass/fail; "not
evaluable" is a visually distinct violet family (`--color-not-evaluable`),
never rendered as a pass. This is pre-existing pipeline behavior
(`bordereaux/src/bordereaux/validation.py`), unchanged this session.

## Design system (as of this session)

- Typography: serif `--font-display` (system stack: Iowan Old Style /
  Georgia / Cambria fallback, no webfont) for headings and eyebrows, sans
  for body/controls, mono for tabular figures (amounts, counts, IDs).
- Status badges: hairline-bordered tags (`--radius-xs`), never a filled
  pill, always paired with a glyph (●/▲/✕/◐/◆/?/⧉).
- Stat display: typographic block (uppercase label + tabular numeral +
  hairline top rule), not a bordered "card" — used for the Reports
  screen's four top-line metrics.
- Color tokens themselves are unchanged from before this session (see
  `truebind-web/frontend/styles/variables.css` /
  `lib/colorContrast.ts`) — deliberately, since they're already
  WCAG-AA-validated at build time and kept as distinct hue families per
  status system (mapping tri-state / arithmetic outcome / leakage
  confidence / sanctions). This session changed *how* those colors are
  applied (border vs. fill), not the palette.
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
