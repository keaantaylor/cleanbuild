# TODO, in priority order

Update this file whenever you complete, add, or reprioritize an item —
don't let it drift from what `HANDOFF.md`'s "still broken" section says.

## Manual QA in progress (2026-09-22 onward)

The user is running the app locally (both servers, real browser) to find
things that don't work before considering this "a viable option." Log
every finding here as it comes in — file/line if known, repro steps,
whether it's fixed yet — so nothing gets reported twice or lost between
sessions. Don't pre-fill this with guesses; only add a real finding once
it's actually been hit.

*(empty — nothing logged yet)*

## Highest priority (blocks everything else)

0. **Reconcile this branch against `main`.** They have diverged with two
   different fixes for some of the same bugs, plus `main` has an AI
   exception-triage feature and a marketing homepage this branch lacks.
   See `PROJECT_STATE.md`'s "`main` has diverged" section. Needs a
   deliberate side-by-side decision, not an automatic merge — different
   Alembic migration chains alone will conflict if merged blindly.

## High priority

1. **Verify the `.xls` fix through the Streamlit app's own upload path**
   (`streamlit run bordereaux/app.py`, upload
   `bordereaux/tests/fixtures/legacy_sample.xls` through the actual
   `st.file_uploader` widget). It should work — both apps call the same
   `bordereaux.ingest.load_workbook_sheets()` — but this session only
   verified it through `truebind-web`'s FastAPI/Next.js stack, not
   Streamlit's UI specifically. Quick to check, worth confirming before
   calling the bug fully closed everywhere it's promised.

2. ~~Re-screenshot Exceptions, Duplicates and the report detail page with
   a file that actually has flagged data.~~ **Done in session 2**: Reports
   and Exceptions were screenshotted with `test_boundary_cases.xlsx` (real
   missing-mandatory/mismatch/duplicate counts) and with the new
   `repeated_header_block.xlsx` fixture (real not-evaluable + excluded-row
   data). Duplicates' `SideBySideComparison` screen specifically still
   hasn't been screenshotted with a genuinely flagged pair — see item 9.

3. **Decide on `pandas` version pinning.** Currently unpinned
   (`pandas>=2.2`), resolved to `3.0.5` in this session's fresh install,
   all tests pass. Not broken, but also not a deliberate choice by
   anyone — see `DECISIONS.md`. If a pandas-3.x-specific bug surfaces
   later, check `copy_on_write` semantics, `errors="ignore"` removal, and
   default string dtype behavior first.

## Medium priority

3a. **Sanitize `Report.processing_error` before it reaches an end user.**
    Right now it's the raw Python exception string, shown as-is in the
    frontend's FAILED-state banner. Fine for internal QA (you'll want the
    real error while testing), but needs a friendlier message layer
    before any real customer sees it.

3b. **No CI/CD, no Railway/Render config anywhere in the repo.** Both
    Dockerfiles are production-ready now (session 3-4) but nothing
    auto-deploys. If a Railway service is already paid for, check its
    dashboard directly for: which branch it tracks, whether "deploy on
    push" is even on, and what commit is actually live — none of that is
    visible from the repo.

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

9. **(session 2)** Duplicates and Audit screens didn't get the
   tooltip/explanation treatment Reports and Exceptions got. Also,
   `SideBySideComparison` (duplicates) still hasn't been visually verified
   against a genuinely tricky near-duplicate (fuzzy name match, not exact)
   — only exact-match pairs have been screenshotted so far.

10. **(session 2)** Verify the `.xls` fix's item 1 above is still open —
    not re-checked this session, still Streamlit-UI-unverified.

11. **(session 2)** Noticed but did not fix: the Exceptions page's
    "Missing mandatory" tab count (counts individual flagged exceptions —
    a row missing both claim ref *and* insured name counts twice) differs
    from the Reports page's `missing_mandatory_rows` metric (counts
    distinct rows, deduplicated) — e.g. 74 vs 68 on the boundary fixture.
    Both numbers are individually correct for what they measure, but
    showing two different "missing mandatory" numbers on two screens
    without explaining the difference undercuts exactly the
    trust/verifiability goal Section 2 was about. Pre-existing behavior,
    not introduced this session — worth a dedicated pass (either make the
    Exceptions tab count distinct rows too, or label both counts
    explicitly enough that the difference makes sense).
