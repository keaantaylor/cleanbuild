# Claims Bordereaux Aggregation & Segregation Tool (MVP)

Upload a claims bordereau in any format — a single sheet or a whole
multi-sheet workbook, one tab per sender — and get back a standardised,
validated, exception-flagged version, plus a plain-English data-quality
report. Built against the six-phase brief; see inline docstrings in
`src/bordereaux/` for how each phase maps to its acceptance test, and the
"Ingestion & Mapping Fix Spec" work (below) for the multi-sheet/mapping
hardening that followed real-world testing.

## Setup

```bash
cd bordereaux
pip install -e .
# or: pip install -r requirements.txt
```

AI-assisted column mapping (Phase 3's fallback for headers the alias
dictionary doesn't recognise) calls the Claude API and needs:

```bash
export ANTHROPIC_API_KEY=sk-...
```

Without a key, fuzzy matching against known aliases still runs; anything
left unmatched just needs a manual pick in the mapping review step (CLI
prompt or the Streamlit dropdown) instead of an AI suggestion — the tool
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
scripts/process_file.py    Phase 2 CLI: hard-coded mapping, one file at a time
app.py                      Phase 6 (+ fix spec): Streamlit demo (upload,
                             single sheet or multi-sheet workbook -> mapping
                             review per sheet -> validation/duplicates,
                             with a coverage banner -> download)
tests/test_phase{2,3,4,5,6}.py   Each phase's acceptance test
tests/test_boundary_fixture.py   Fix spec 3.10: regression suite against
                                  test_boundary_cases.xlsx, one assertion per
                                  D1-D8 defect in the fix spec
tests/test_unmappable_sheet.py   Senior-pass fix spec Section 1: a sheet
                                  with unmappable (e.g. non-English) headers
                                  is never silently dropped, and a per-sheet
                                  read/scoring crash is isolated, not fatal
tests/test_header_suffix.py      Senior-pass fix spec Section 2: a trailing
                                  "(GBP)"-style header suffix doesn't block
                                  mapping, and backfills Currency when unmapped
tests/test_amount_parsing.py     Senior-pass fix spec Section 3: currency
                                  symbols/thousands separators parse; a
                                  missing/unparseable input is NOT_EVALUABLE,
                                  never silently treated as zero
tests/test_dedupe_scale.py       Senior-pass fix spec Section 4: duplicate
                                  detection stays close to the planted count
                                  (not orders of magnitude higher) at
                                  realistic and pathological-scale row counts
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
python3 tests/test_unmappable_sheet.py
python3 tests/test_header_suffix.py
python3 tests/test_amount_parsing.py
python3 tests/test_dedupe_scale.py
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

It opens with an upload box and a "Try it now with a sample bordereau"
button that pre-loads one Phase 1 synthetic file, so a prospect can see
output before uploading anything of their own, per Phase 6's brief.

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
