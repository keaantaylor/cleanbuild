# Claims Bordereaux Aggregation & Segregation Tool (MVP)

Upload a claims bordereau in any format → get back a standardised,
validated, exception-flagged version, plus a plain-English data-quality
report. Built against the six-phase brief; see inline docstrings in
`src/bordereaux/` for how each phase maps to its acceptance test.

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
src/bordereaux/
  schema.py               Section 3: the 10-field skeleton, as field specs
  iso4217.py               ISO 4217 currency codes
  ingest.py                Load a raw file, apply a confirmed mapping
  pandera_schema.py        Column-level type schema
  validation.py             Section 8 row-level rules -> exception report
  export.py                  Segregated export (one sheet per claim status)
  mapping.py                 Phase 3: fuzzy + AI-assisted column mapping
  dedupe.py                   Phase 4: exact + probable duplicate detection
  report.py                    Phase 5: completeness/health report (xlsx + pdf)
  pipeline.py                   Orchestrates the above for the CLI and the app
scripts/process_file.py    Phase 2 CLI: hard-coded mapping, one file at a time
app.py                      Phase 6: Streamlit demo (upload -> mapping review
                             -> validation/duplicates -> download)
tests/test_phase{2,3,4,5,6}.py   Each phase's acceptance test
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

Run the acceptance tests for each phase:

```bash
python3 tests/test_phase2.py
python3 tests/test_phase3.py
python3 tests/test_phase4.py
python3 tests/test_phase5.py
python3 tests/test_phase6.py
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
- Every mapping decision (fuzzy-matched, AI-suggested, human-confirmed)
  is shown in the app's "Mapping audit trail" panel per run.
