# Truebind: Claims Bordereaux Aggregation & Segregation Tool

Upload a claims bordereau in any format — a single sheet or a whole
multi-sheet workbook, one tab per sender — and get back a standardised,
validated, exception-flagged version, a payment-leakage and duplicate
report, and a plain-English data-quality report, with every mapping
decision and export logged to a persisted audit trail. Built up across
three phases of work; see inline docstrings in `src/bordereaux/` for how
each maps to its acceptance test:

1. **The original six-phase MVP brief** (Phase 1-6 below).
2. **An "Ingestion & Mapping Fix Spec"** hardening pass (multi-sheet
   ingestion, header-row detection below a merged banner, tri-state
   mapping, requiredness taxonomy, three-outcome arithmetic, duplicate
   name-normalization, coverage reporting).
3. **The "Truebind" redevelopment**: real database persistence, a
   payment-leakage detector, an audit trail with a one-click governance
   review pack export, a real (sourced, not guessed) Lloyd's Coverholder
   Reporting Standards v5.2 template, and a higher-contrast design system
   across every screen.

## Setup

```bash
cd bordereaux
pip install -e .
# or: pip install -r requirements.txt
```

Apply the database migrations (SQLite by default, at `data/app.db`; the
app also calls this automatically on startup, so this is only needed for
CLI/script use outside Streamlit):

```bash
python3 -m alembic upgrade head
```

To point at Postgres instead for a production-minded deployment, set
`DATABASE_URL` (e.g. `postgresql://user:pass@host/dbname`) before running
migrations or the app -- no code change needed.

AI-assisted column mapping (the fallback for headers the alias dictionary
doesn't recognise) calls the Claude API and needs:

```bash
export ANTHROPIC_API_KEY=sk-...
```

Without a key, fuzzy matching against known aliases (and any saved/
Lloyd's template) still runs; anything left unmatched just needs a manual
pick in the mapping review step instead of an AI suggestion — the tool
degrades gracefully rather than failing.

## Project layout

```
data/synthetic/          Phase 1: messy synthetic bordereaux + answer key
                          Fix-spec fixture: test_boundary_cases.xlsx (10-sheet,
                          320-row) + test_boundary_cases_answer_key.json
src/bordereaux/
  schema.py               Section 3: the 10-field skeleton, as field specs --
                           also the single source of truth for field
                           requiredness (required / optional / conditional
                           pair / reconciled -- fix spec 3.6)
  iso4217.py               ISO 4217 currency codes
  ingest.py                Load a raw file OR every sheet of a workbook, with
                            per-sheet header-row detection (fix spec 3.1/3.2);
                            apply a confirmed mapping
  pandera_schema.py        Column-level type schema
  validation.py             Section 8 row-level rules -> exception report,
                             tri-state-mapping-aware (fix spec 3.3), three-
                             outcome arithmetic reconciliation (fix spec 3.7)
  export.py                  Segregated export (one sheet per claim status)
  mapping.py                  Phase 3 (+ fix spec 3.3-3.5): fuzzy/alias +
                               AI-assisted column mapping, tri-state
                               (alias/ai/unmapped), AI-availability checked
                               once up front rather than caught per column
  dedupe.py                    Phase 4 (+ fix spec 3.8): exact + probable
                                duplicate detection, name-normalized
                                (case/punctuation/legal-suffix), cross-sheet
  report.py                     Phase 5 (+ fix spec 3.3/3.6/3.7/3.9):
                                 completeness/health report (xlsx + pdf),
                                 coverage banner, reliability caveat
  pipeline.py                    Orchestrates the above for the CLI and the
                                  app; both a single-sheet path and a
                                  multi-sheet workbook path
  db/models.py                    SQLAlchemy models: Report, LeakageFlag,
                                   ExceptionRecord, AuditLogEntry, Template,
                                   TemplateFieldMapping, Obligation, Alert
  db/session.py                    Engine/session factory (SQLite by
                                    default; DATABASE_URL for Postgres)
  persistence.py                    Bridges a pipeline run into the DB
  leakage.py                         Payment-leakage detector: CERTAIN/
                                      PROBABLE/POSSIBLE, config-driven
                                      amount tolerance + date windows
  templates.py                        Saved-mapping templates: create,
                                       score against incoming headers,
                                       suggest (never auto-applied)
  lloyds_template.py                   The real Lloyd's v5.2 claims field
                                        data, sourced from the official PDF
                                        (see module docstring for the exact
                                        source and what it does NOT claim)
  audit.py                              Append-only audit log helpers
  governance_pack.py                     One-click Governance Review Pack
                                          PDF export
  theme.py                                Design system: WCAG-AA-validated
                                           color tokens per status system,
                                           badge/stat render helpers
alembic/                    Database migrations
scripts/process_file.py    Phase 2 CLI: hard-coded mapping, one file at a time
app.py                      Multi-page Streamlit entrypoint (st.navigation)
upload_and_process.py       Page: upload -> mapping review (incl. template
                             suggestion badge) -> validation/duplicates/
                             leakage -> download, with the run persisted
leakage_dashboard.py         Page: Leakage & Duplicates -- exposure total,
                              filterable by confidence tier
compliance_audit.py           Page: Compliance & Audit -- audit log,
                               Governance Review Pack export
tests/test_phase{2,3,4,5,6}.py   Each MVP phase's acceptance test
tests/test_boundary_fixture.py   Fix spec 3.10: regression suite against
                                  test_boundary_cases.xlsx, one assertion per
                                  D1-D8 defect in the fix spec
tests/test_leakage.py             Leakage detector: exact tier match, zero
                                   false positives, against its own fixture
tests/test_audit_governance.py     Every action type logs; the governance
                                    pack includes everything logged
tests/test_lloyds_template.py       Lloyd's template suggested correctly
                                     for both bare codes and real field names
tests/test_theme.py                  Every color pair meets WCAG AA;
                                      not-evaluable/sanctions stay distinct
```

## Running things

Generate the synthetic test files (already committed under
`data/synthetic/`, only needed if you want to regenerate them):

```bash
pip install -e ".[dev]"
python3 data/synthetic/generate_synthetic.py
```

Run one file through the Phase 2 hard-coded-mapping pipeline:

```bash
python3 scripts/process_file.py a   # a | b | c | d
```

Run the acceptance tests for each phase, plus the fix-spec regression suite:

```bash
python3 tests/test_phase2.py
python3 tests/test_phase3.py
python3 tests/test_phase4.py
python3 tests/test_phase5.py
python3 tests/test_phase6.py
python3 tests/test_boundary_fixture.py
python3 tests/test_leakage.py
python3 tests/test_audit_governance.py
python3 tests/test_lloyds_template.py
python3 tests/test_theme.py
```

To regenerate the fix-spec fixture (already committed under `data/synthetic/`):

```bash
pip install -e ".[dev]"
python3 data/synthetic/generate_boundary_fixture.py
```

Launch the demo app:

```bash
streamlit run app.py
```

It's a multi-page app (sidebar: Upload & Process, Leakage & Duplicates,
Compliance & Audit). The Upload & Process page opens with an upload box
and a "Try it now with a sample bordereau" button that pre-loads one
Phase 1 synthetic file, so a prospect can see output before uploading
anything of their own, per Phase 6's brief. Every run is persisted, so
the other two pages show real data for any report processed in this or a
previous session.

## Notes on the Truebind expansion

- **Two things the redevelopment prompt assumed already existed did
  not**: an "alerts/obligations system" and a "user-created-template
  mechanism". A repo-wide grep before starting this work found zero
  trace of either. Both were built as minimal prerequisites (`templates.py`,
  and `Obligation`/`Alert` models) sized to exactly what the leakage
  detector and audit trail need to plug into -- not a speculative
  workflow engine.
- **The Lloyd's v5.2 template's field data is real, not guessed** --
  sourced from the official 118-page "Coverholder Reporting Standards
  User Guide Version 5.2" PDF (20 August 2019, assets.lloyds.com),
  fetched and text-extracted during this build. `lloyds_template.py`'s
  module docstring documents exactly what it does and doesn't claim:
  the internal `M`/`CM` field-code suffixes are this project's own
  convention, not Lloyd's notation, and the mandatory/conditional split
  falls back to this project's own schema where the PDF's prose doesn't
  explicitly say "must be reported" (the Market Business Glossary's
  authoritative grid needs a portal account this build didn't have).
- **Streamlit-viability**: it holds this weight fine at this scale --
  multi-page nav, a SQLAlchemy-backed store, and dataframe/PDF-heavy
  dashboards are all within its normal range. The one real gap is
  multi-user auth (Streamlit has none built in); every persisted action
  currently logs as a single `streamlit_user` actor. Worth addressing
  before any real multi-user deployment, not before then.
- **Every status system in the product has its own WCAG-AA-validated
  color family** (`theme.py`): mapping tri-state, arithmetic three-outcome
  (not-evaluable is deliberately violet, outside the green/amber/red
  families, so it's never mistaken for "clean"), leakage confidence heat,
  and a reserved, theme-invariant treatment for sanctions/PEP severity
  (defined now, not yet surfaced anywhere -- sanctions screening itself
  is Phase 2, not built).
- Phase 2 (sanctions/PEP screening, technical account reconciliation) is
  deliberately not started -- the redevelopment prompt is explicit that
  Phase 2 waits until Phase 1 is shipped and in front of a real prospect.

## Notes on scope

- No OCR/PDF pipeline, no authority-limit monitoring, no client system
  integrations, no fraud/image analysis, no formal security certification
  work, no multi-tenant billing/roles — see Section 4 of the brief. This
  is a standalone upload → process → export tool.
- The tool prepares data for human review; it does not accept, deny or
  price claims, and nothing here auto-merges a flagged duplicate.
- Every mapping decision (fuzzy-matched, AI-suggested, manually-picked) is
  shown in the app's "Mapping audit trail" panel per run, per sheet.
- Field requiredness (fix spec 3.6): only claim reference and insured name
  are unconditionally required. Status/dates/currency/policy reference are
  validated when present but don't trigger a missing-mandatory-field flag
  when absent. Paid/reserve are a conditional pair (flagged only if both
  are null). Total incurred is checked via arithmetic reconciliation
  (paid + reserve == incurred), not as an independent non-null field.
- A workbook can have any number of sheets; each is mapped independently.
  A sheet with no header row the pipeline can recognise (e.g. a notes/
  cover tab) is skipped and reported as skipped, never silently dropped
  or silently counted as claims. A canonical field left unmapped
  everywhere in the file shows as "column not found" in the health
  report, never as a misleading 0% completeness.
