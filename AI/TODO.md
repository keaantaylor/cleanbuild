# TODO, in priority order

Update this file whenever you complete, add, or reprioritize an item —
don't let it drift from what `HANDOFF.md`'s "still broken" section says.

## High priority

1. **Verify the `.xls` fix through the Streamlit app's own upload path**
   (`streamlit run bordereaux/app.py`, upload
   `bordereaux/tests/fixtures/legacy_sample.xls` through the actual
   `st.file_uploader` widget). It should work — both apps call the same
   `bordereaux.ingest.load_workbook_sheets()` — but this session only
   verified it through `truebind-web`'s FastAPI/Next.js stack, not
   Streamlit's UI specifically. Quick to check, worth confirming before
   calling the bug fully closed everywhere it's promised.

2. **Re-screenshot Exceptions, Duplicates and the report detail page with
   a file that actually has flagged data.** This session's manual
   browser verification used a clean synthetic file (zero exceptions,
   zero duplicates) for speed. Upload
   `bordereaux/data/synthetic/test_boundary_cases.xlsx` (10 sheets, 38
   arithmetic mismatches, 68 missing-mandatory rows, 16 probable
   duplicate pairs per the answer key) through the redesigned UI and
   confirm the MISMATCH/duplicate side-by-side comparison screens read
   correctly under real flagged data, not just empty states.

3. **Decide on `pandas` version pinning.** Currently unpinned
   (`pandas>=2.2`), resolved to `3.0.5` in this session's fresh install,
   all tests pass. Not broken, but also not a deliberate choice by
   anyone — see `DECISIONS.md`. If a pandas-3.x-specific bug surfaces
   later, check `copy_on_write` semantics, `errors="ignore"` removal, and
   default string dtype behavior first.

## Medium priority

4. Port payment-leakage detection, the Lloyd's v5.2 template, and the PDF
   governance-review-pack export from the Streamlit build's
   `claude/great-gauss-082g8l` branch into `truebind-web` — flagged as
   "natural follow-up work" in `truebind-web/README.md`, not started
   there or in this session.

5. Consider a real webfont for `--font-display` if the deploy
   environment's build-time network access is confirmed reliable — see
   the relevant `DECISIONS.md` entry for what to check first and what
   the swap would involve.

6. The Duplicates/Exceptions/Todo/Audit screens inherited the new design
   system automatically (shared `Table`/`Badge`/`Button`/`ReportPicker`
   atoms) but were not given screen-specific redesign passes the way
   Upload and Reports were. If a future session has more design-review
   time, look specifically at:
   - `SideBySideComparison` (duplicates) — the comparison table works but
     wasn't tested with a genuinely tricky near-duplicate (fuzzy
     name-match, not exact) to confirm the visual distinction reads well.
   - `ExceptionDetail`'s obligation-raising form — functional, not
     restyled beyond global input theming.

## Low priority / housekeeping

7. `truebind-web/frontend/.gitignore` now ignores `AGENTS.md`/`CLAUDE.md`
   (Next.js 16 auto-generates these on every `next dev`). If a future
   Next.js version changes this behavior, revisit.

8. No auth beyond a single `web_user` actor — pre-existing, documented,
   not this session's scope, but worth flagging again since it blocks any
   real multi-user deployment.
