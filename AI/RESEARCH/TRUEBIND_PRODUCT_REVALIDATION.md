# TrueBind — Product Revalidation (Discovery Phase)

**Date:** 2026-09-24 · **Repository:** `keaantaylor/cleanbuild` ·
**Commit investigated:** `eee00cf` ("Merge claude/truebind-improvements-y992ya into main")
· **Branch for this work:** `claude/truebind-discovery-research-1soe9p` ·
**No production code was changed.** This phase produced only
`AI/RESEARCH/*.md`.

Companion files: `TRUEBIND_SOURCE_REGISTER.md` (all citations, `[Xn.n]`),
`TRUEBIND_COMPETITIVE_LANDSCAPE.md`, `TRUEBIND_MARKET_EXPANSION.md`,
`TRUEBIND_UNIT_ECONOMICS.md`, `TRUEBIND_STRATEGIC_ROADMAP.md`.

**Method.** Every statement about the code comes from reading the source at
`eee00cf` and from runs against it in this session: test suites,
**18 correctness probes (P1–P18) plus follow-ups F1–F2**, an **HTTP
benchmark matrix** (uvicorn; SQLite and Postgres 16; 1k to 250k rows;
sheet, column, exception, duplicate and structure variants), **security
probes (S1–S10)** and a **real-browser test**. The external-research method
is described in the source register. The handoff, README and commit messages
were treated as claims to test, not as evidence.

---

## 0. Executive summary

1. **TrueBind today is an 8-day-old claims-bordereau checker** (first
   TrueBind commit 2026-09-16, last 2026-09-23). It reads multi-sheet Excel
   or CSV, proposes a 10-field column mapping, asks a human to confirm it,
   then runs completeness, arithmetic, date, currency and duplicate checks
   and produces a graded report with a row-count reconciliation. It has
   **no customers, no auth, no tenancy, no deployment, and no real customer
   file** in the repository.

2. **Its core arithmetic contradicts the Lloyd's standard it claims to
   implement.** The v5.2 guide defines CR0155 *Total Incurred* as paid this
   month + **previously paid** + reserve, for indemnity **and fees** [B1.1].
   TrueBind checks `CR0126 (paid this month) + CR0130 (reserve) == CR0155`.
   On genuine v5.2 claims data with any prior payments or fees, it reports
   **false arithmetic mismatches**. Its alias list also maps "paid to date"
   and "paid ytd" onto the *this-month* field (§3.2).

3. **The handoff's claimed fixes mostly exist in code and have tests**
   (TB-001/002/003/004/005/007b). **Adversarial probes found that several
   introduced or left silent failures** (§4). The worst are:
   - In a workbook where half the sheets have French headers, one accidental
     alias hit reclassifies those claims sheets as "summaries", **dropping
     50% of the claims while the report says grade 5 "Excellent" and
     `score_reliable: True`** (F3).
   - Data after a run of 500+ blank rows is **silently dropped**, and the
     reconciliation still reports "reconciles" (P2).
   - A dd/mm date column containing a single ISO date is re-parsed
     month-first for every row (P5).
   - A "Total" row in a narrow sheet is ingested as a claim, doubling
     incurred (F2).
   - A claim row with only its reference populated is excluded as a "title"
     (P1).
   - A normal multi-month workbook scores 100% duplicates and grade 2
     (F1).
   - Currency-inconsistency findings are persisted with the
     `MAPPING_COMPLETENESS` label (P19).
   - "Paid (GBP)" plus "Reserve (EUR)" are summed without complaint (P9).

4. **The user-reported problems reproduce.** These are real HTTP runs,
   locally, on 4 vCPU (§5–6):
   - Upload blocks the whole server. `/health` could not answer for
     **18.7 s at 100k rows and 46.3 s at 250k rows**, because an `async`
     route does synchronous parsing.
   - On SQLite, status polls return **HTTP 500 "database is locked"**
     during large persists (100k and 250k runs).
   - At 250k rows the Duplicates endpoint takes **38 s and returns 85 MB**,
     beyond the frontend's 30 s timeout. The page has no error handling, so
     the UI shows *"No probable duplicates found"* (inferred from code; the browser run was not completed).
   - Processing time grows super-linearly because of dedupe (**144 s** at
     250k rows).
   - Peak RAM is **1.7 GB** at 250k rows.
   - **Hosted behaviour could not be measured:** no hosted deployment was
     reachable.

5. **The market problem is real and durable.** Delegated arrangements are
   **39% of Lloyd's GWP** (Lloyd's CUO, Q3 2024) [B2.2]. The CUO called
   out-of-date bordereau data "bizarre" [B2.2]. v5.2 says "Lloyd's has not
   mandated that a particular format is used" [B1.1]. Solvency II requires
   technical-provision data to be complete, accurate and appropriate
   [B3.1]. The research literature shows humans miss errors in spreadsheets
   [A1.5] and miss what automation fails to flag [A3.4, A3.5].

6. **The competitive window has changed.** Lloyd's **DDM stopped being a
   mandated core service on 13 Sep 2024** [B2.1, B1.2], so managing agents
   are choosing platforms now. Well-funded incumbents already sell AI
   ingestion: VIPR (Bridgepoint-backed), Charles Taylor Tide plus
   **Bordereaux Sync**, Vellum, Verodat, Send and Scrub AI. Bordereaux Sync
   in particular sells the "screen before the BMS" slot TrueBind targets
   [B5.1]. **"AI maps your columns" is table stakes.**

7. **The strongest evidence-supported version of TrueBind** is not a
   bordereaux management system. It is a narrow **delegated-authority data
   *assurance* layer**: a deterministic, standard-correct engine that
   *refuses to guess*, accounts for every source row, states what it could
   not verify, and produces an evidence pack. It feeds the customer's
   existing BMS or warehouse and does not replace them. This fits the
   regulatory pull [B3.1, B3.2] and the automation-trust literature
   [A3.1, A3.3, A3.13]. It is the **only** thing in the codebase that
   competitors do not visibly document.
   - Confidence in the **problem**: high.
   - Confidence that **this positioning wins**: low–medium. It is untested
     with buyers, Bordereaux Sync occupies the slot, and TrueBind's own
     "assurance" is currently wrong on the headline v5.2 check.

8. **What to do next** (details in the roadmap):
   - (i) Fix correctness against v5.2 and the silent-loss defects.
   - (ii) Fix the five reliability defects that explain the user's
     "doesn't load / large files fail".
   - (iii) Stop claiming "Lloyd's v5.2" until a v5.2-conformant fixture
     passes.
   - (iv) Get **50 real bordereaux and 12 buyer interviews** before
     building anything new.
   - (v) Trial Bordereaux Sync hands-on.
   - The strategy is **conditional** on those experiments. There is no
     evidence yet that anyone will pay.

---

## 1. Repository forensics: what TrueBind is today

### 1.1 Git state (verified 2026-09-24)

| Item | Finding |
|---|---|
| Current branch | `claude/truebind-discovery-research-1soe9p`, at `eee00cf`, identical to `origin/main` |
| `main` | `eee00cf` "Merge claude/truebind-improvements-y992ya into main". **Matches the handoff.** |
| `claude/truebind-improvements-y992ya` | `27e3ec4`, an ancestor of `main`, **not ahead**. **Matches the handoff.** |
| Other remote branches | `claude/great-gauss-082g8l` (holds **Phase 1: leakage detection, governance pack, v5.2 template**, commit `9fb63d0`, *not merged to main*); `claude/truebind-web-redesign`, `integrate-truebind`, `claude/deploy-prep`, `claude/focused-planck-dxba74` (merged or ancestors) |
| History | 40 commits on all branches. Repo started 2026-07-06 ("LaunchPoint site"); TrueBind work 2026-09-16 → 2026-09-23. Authors: "Claude" (29 commits) and "keaantaylor" (10, mostly merges) |
| Size | 237 tracked files. Python: bordereaux core ≈ 2.3k LOC, FastAPI backend ≈ 3.3k LOC. Frontend: 109 files (Next.js 16.3.5, React 19.2.8, CSS Modules, no component library) |
| Unrelated artefacts | `LaunchPoint Site.dc.html` (115 kB) and `assets/launchpoint-logo.png` at the repo root, left over from the original site |

### 1.2 Handoff documents vs reality

| Document | State |
|---|---|
| `AI/HANDOFF.md` | **Stale.** Covers sessions 1–5 only. Session 6 (TB-001…TB-007b) appears only in `TODO.md`; session 7 (performance) only in commit `27e3ec4`'s message. |
| `AI/PROJECT_STATE.md` | **Stale and contradictory.** Still warns "⚠️ `main` has diverged — do not assume it agrees with this branch", but both the AI-triage feature (`9e1e69d`) and the session-5 work (`72ba26b`) are in `main` (checked with `git merge-base --is-ancestor`). |
| `AI/TODO.md` | Item 0 "Reconcile this branch against main" is effectively done by merges `bbb6e78`/`eee00cf` but not marked done. The "Manual QA in progress" log is empty ("nothing logged yet"), so **the user's reported failures were never written down**. |
| `AI/DECISIONS.md` | Consistent with the code for the decisions it covers (xlrd, .xlsm, pandas unpinned, serif stack, badges). |
| READMEs | `truebind-web/README.md` says "The backend runs `alembic upgrade head` automatically on container start". **True only for `docker-compose.yml`.** The production `Dockerfile` CMD runs uvicorn with no migration, and the app has no `create_all`. A standalone container would start against an empty DB, and the startup hook's `SELECT … FROM reports` would fail (inferred from code; not run in a container). |

### 1.3 Build, deploy, config

| Area | Finding |
|---|---|
| Backend deps | `fastapi>=0.115`, `pandas>=2.2` (unpinned; resolved to **pandas 3.0.6**, numpy 2.4.6), `openpyxl 3.1.5`, `xlrd 2.0.2`, `anthropic 1.8.0`, `rapidfuzz`, `pandera`, `reportlab`. **`defusedxml` is absent** (§19). |
| Database | SQLite at `backend/data/truebind.db` by default; Postgres via `DATABASE_URL`. 7 Alembic migrations, one merge. **`alembic check` fails: the DB has `reports.processing_phase`, the model does not.** |
| Background work | A `threading.Thread(daemon=True)` per `/process`. No queue, no timeout, no memory limit, no cancellation. On restart, *every* `PROCESSING` report is marked FAILED, including ones owned by another live worker if more than one process runs. |
| Config | `DATABASE_URL`, `CORS_ORIGINS`, `ANTHROPIC_API_KEY`, `NEXT_PUBLIC_API_URL` (baked in at `next build`; the frontend Dockerfile passes no build arg, so a hosted build defaults to `http://localhost:8000/api/v1` unless the env is set at build time). |
| Logging | Python `logging` to stdout. One timing line per processed report. Tracebacks on failure. Correlation IDs on unhandled 500s. |
| CI/CD | **None.** No workflow files. |
| Auth | **None.** Every endpoint is anonymous. The audit "actor" comes from the request body (§19 S8). |

### 1.4 Test and quality evidence (actual counts, this session)

| Suite | Handoff claim | Observed on a clean checkout | Notes |
|---|---|---|---|
| bordereaux pytest | "34 passed" (session 6) | **35 passed, 8 errors** | The 8 errors are `test_boundary_fixture.py`, a script-style file that pytest collects. Run as a script it **passes**. `27e3ec4` added one test, which accounts for 34 → 35. |
| bordereaux script suites | "pass" | `test_boundary_fixture`, `test_phase2..6`, `test_legacy_formats`: **all pass** | |
| backend pytest | "18 passed" | **25 passed, 2 failed** on a clean checkout. **27 passed** only after `alembic upgrade head` creates the *developer* DB | `tests/test_exception_summary.py::db_session` calls `database.get_session_factory()` directly, so it bypasses the test override and **uses the real `data/truebind.db`**. The test result depends on local state. |
| frontend `tsc --noEmit` | clean | **clean** | |
| frontend `eslint` | "clean" (session 5) | **5 errors** (`react-hooks/set-state-in-effect`) in `exceptions/page.tsx`, `todo/page.tsx`, `AiTriagePanel.tsx`, `Reveal.tsx`, `useCountUp.ts` | Probably arrived with the `main` merge; not clean at HEAD. |
| Test hygiene | — | Running the suites **rewrote 10 tracked binary fixtures** in `bordereaux/tests/fixtures/` and wrote upload directories into `backend/data/uploads/` | Tests are not hermetic. The fixtures were restored with `git checkout` before committing. |

---

## 2. System map: what the code actually does

Flow in `truebind-web` (the Streamlit `bordereaux/app.py` uses the same
`bordereaux` package through a different UI, which was not exercised this
session).

| Stage | Source (file · function) | Input → output | DB | External | Failure mode (verified = ✔, from code = ◇) | Tests | Perf (measured) | Security / audit |
|---|---|---|---|---|---|---|---|---|
| **User / frontend** | `frontend/app/(dashboard)/upload/page.tsx`; `lib/api.ts request()` | File → `POST /upload`; 30 s timeout on every call, 120 s on upload | — | — | ✔ Timeouts surface on the report page, but **list pages have no `catch`** and show empty ("No probable duplicates found") on failure. ◇ The mapping `useEffect` has no catch, so a failed GET leaves "Loading…" forever | tsc only; no FE tests | Browser: §6 | No auth |
| **API** | `backend/app/main.py`; routers | JSON/multipart | — | — | ✔ Global 500 handler with correlation ID and CORS (TB-004) | `test_exception_containment.py` | — | CORS reflects any origin if `*` configured; credentials true |
| **Upload** | `routes/upload.py · upload_report` (**`async def`**) | Streams to a temp file (1 MiB chunks) | Creates Report, Sheet, Mapping, ExcludedRow | — | ✔ **Blocks the event loop** for the whole parse (§5). ◇ **No size limit.** ◇ Stored under the client filename (§19 S1/S2). ◇ Temp file leaks if mapping or persistence raises | `test_pipeline_parity`, others | 25k: 4.7 s; 100k: 18.8 s; 250k: 46.9 s | OWASP gaps (§19) |
| **Storage** | `routes/deps.py · stored_upload_path` → `data/uploads/{report_id}/{file_name}` | Original file kept forever | — | Local disk | ◇ No retention/deletion policy except `DELETE /reports/{id}`; ◇ the local disk is ephemeral on most PaaS | — | — | Unencrypted at rest; no tenant separation |
| **Ingestion** | `bordereaux/ingest.py · load_workbook_sheets` (openpyxl `read_only`, `data_only`); `_iter_legacy_xls_rows` (xlrd); `_build_csv_sheet_data` (pandas) | File → `list[SheetData]` (raw strings DataFrame per sheet) | — | — | ✔ **Silent truncation after 500 consecutive blank rows (P2)**; ✔ columns beyond 500 dropped only when the declared width >500 (P3); ✔ **cp1252 CSV raises UnicodeDecodeError (P13)**; ✔ `;`-delimited CSV becomes one column (P13b); ✔ CSV title rows break the header (P13c); ✔ hidden sheets and rows are ingested (P14); ✔ formulas without cached values read as blank (P12) | `test_legacy_formats`, `test_stray_cell_bounded_scan`, … | Materialises every row as Python tuples, then a string DataFrame: RSS 413 MB at 25k, 1.7 GB at 250k | openpyxl without `defusedxml` (§19) |
| **Header detection** | `ingest._detect_header_row` (fuzzy alias score over the first **50** rows, needs ≥3 matches) → `_structural_header_row` fallback | Rows → header index | — | — | ✔ Header at row 51 means the sheet is **skipped** (visible, reason given) (P4) | `test_low_header_row`, `test_unmappable_sheet` | `fuzzy_match_headers` rebuilds the alias index per row | — |
| **Row classification** | `ingest._classify_row`: blank / repeated header / subtotal / title | Rows → kept + `ExcludedRow` ledger | `excluded_rows` table | — | ✔ Claim-ref-only row → "title" (**real claim excluded**, P1); ✔ "Total" row with amounts in a ≤7-column sheet is **kept as a claim** (F2; P17: "TOTAL CLAIMS" and "Sum" not recognised) | `test_row_exclusion`, `test_title_row_exclusion` | cheap | Excluded rows keep their raw values (good for audit) |
| **Sheet classification** | `report.classify_sheet_status` (mapped / partial / unmapped / empty / error / non_claim_summary) | Mapped field codes → status | Computed on the fly | — | ✔ A **policy-keyed claims tab** (no claim ref, no insured) is classed `non_claim_summary` and **all its rows leave the claim set**, while `fully_covered=True` (P10) | `test_non_claim_summary_sheet` | — | Visible in UI and report |
| **Mapping** | `mapping.build_mapping` → `fuzzy_match_headers` (rapidfuzz `token_sort_ratio` ≥85 vs ~100 aliases) | Headers → suggestions | `mappings` | — | ✔ Multiple headers → same field with 100% "confidence" (P7b); ✔ last column wins silently at apply time (P7) | `test_header_suffix` | — | — |
| **AI fallback** | `mapping.ClaudeAIMapper.propose` (Haiku 4.5, forced tool call) — **only if `ANTHROPIC_API_KEY` is set** | Unmatched headers → field codes | Stored as `MAPPED_BY_AI` | Anthropic API; headers only, no cell values | ◇ **Model confidence discarded; stored as 1.0** (P18); ◇ no client timeout (SDK default 10 min) and no try/except around it at upload, so an API outage fails the upload; ◇ **called again in `/process`** (double cost, can diverge); ◇ forced `tool_choice` is rejected by newer models (Opus 5.5 / Fable 5.1) | Stubbed only | Not measured (no key) | Headers are untrusted prompt input (§19) |
| **Human confirmation** | `routes/mapping.py · confirm_sheet_mapping` → `persistence_service.confirm_sheet_mapping` | `{field_code: source_col}` | Updates `mappings`; `audit_log` | — | ◇ No check for one column bound to two fields, or two to one; ◇ no display of scale or currency interpretation for veto (TB-003 "not done") | `test_pipeline_parity` | Confirm ~30–600 ms/sheet (cache hit) | Actor spoofable (S8) |
| **Validation** | `validation.validate`: mandatory, arithmetic (three-state), dates, currency, status | Canonical DF → exceptions + not-evaluable detail | — | — | ✔ **Arithmetic formula wrong vs v5.2** (§3.2); ✔ cross-currency arithmetic accepted (P9); ✔ date re-parse flips day/month (P5); ✔ "1.234" European thousands read as 1.234 (P6) | `test_amount_parsing`, `test_excel_dates`, phase tests | 0.1–1.5 s at 25k–250k | — |
| **Structural filtering** | See row classification | | | | | | | |
| **Dedupe** | `dedupe.find_duplicates`: exact claim ref (all pairs) + fuzzy name within 2-char prefix blocks ± 3 days | Canonical → pair list | `validation_results` (DUPLICATE) | — | ✔ **No period concept**: the same claim across 12 monthly tabs gives 13,200 "certain duplicate" pairs, 100% dup rate, grade 2 (F1); ✔ O(k²) pairs per repeated ref | `test_dedupe_scale` | **1.9 s @25k → 24.6 s @100k → 144 s @250k** | — |
| **Reconciliation** | `pipeline._build_reconciliation`; `persistence_service.compute_report_summary` | Counts | Recomputed from DB per GET | — | ✔ Blind to rows lost *before* counting (P2 reports `reconciles: True` with 10 of 20 rows missing). Its own docstring says the two paths "agree by construction" | `test_reconciliation*` | Summary GET: 1.3 s @25k, 5.7 s @100k PG, 17.6–19.3 s @250k (loads every ClaimRow; N+1 lazy loads) | — |
| **Persistence** | `persistence_service.persist_pipeline_result` (ORM `add_all` of one object per claim row and per finding) | Canonical + findings → rows | `claim_rows`, `validation_results`, `alerts` | — | ✔ **Rules other than arithmetic/mandatory persisted as `MAPPING_COMPLETENESS`** (P19); ◇ money stored as `Float`; ◇ `VARCHAR` limits (currency 8, status 64, message 1000, `processing_error` 2000) are enforced only on Postgres; ◇ **re-processing a COMPLETE report appends a second copy of every row** (S10) | `test_background_processing` | **8.9 s @25k, 43 s @100k, 109–115 s @250k** | — |
| **Report** | `report.build_health_report` (composite = completeness − exception% − 0.5 × dup%) → grade 1–5 | Health report | `reports.grade/score` | — | ◇ A heuristic score, labelled as such in the docstring; F1 shows it can grade a correct file "2 – Poor" | phase5 | ~1 s @250k | — |
| **Export** | `export_service.claims_by_status_csv`, `audit_log_csv`; `bordereaux.report.write_health_report_excel/pdf` (Streamlit/CLI only) | CSV | Reads all rows | — | ◇ **No CSV-injection neutralisation** (S6); ◇ the web app has no Excel/PDF export | — | by-status CSV 10.7 s / 26 MB @250k | Formula injection (§19) |
| **AI triage narrative** | `exception_aggregation_service.build_aggregate` → `exception_narrative_service.generate_narrative` | Aggregate → narrative | `exception_summaries` | Anthropic | ◇ Well designed: numbers pre-computed, post-hoc number check, never raises. But ◇ `value_at_stake` **sums amounts across currencies**, and P19 makes its "ingestion vs data" split wrong | `test_exception_summary` (2 fail on a clean checkout) | Not measured | Aggregate includes sheet names (prompt-injection surface, low impact) |
| **Polling** | `reports/[reportId]/page.tsx` polls `GET /reports/{id}` every 1.5 s | Status | Reads | — | ✔ 5xx during large SQLite persists (§5) | — | p95 0.7–0.8 s, max 5.7 s during processing | — |

---

## 3. Reconciling previous claims

### 3.1 Claim table

Status legend: **VERIFIED** (code + test + runtime probe agree),
**PARTIAL** (implemented, with a verified gap), **UNVERIFIED**,
**BROKEN**, **ABSENT**.

| Claim | Expected implementation | Actual implementation | Test evidence | Runtime evidence (this session) | Status |
|---|---|---|---|---|---|
| **TB-004** global exception containment + CORS-on-error + numeric coercion | Top-level handler; CORS headers on 500; Excel error sentinels and U+2212 handled | `main.py · unhandled_exception_handler` with correlation ID and `_cors_headers_for`; `_EXCEL_ERROR_SENTINELS`; `replace("−","-")` | `test_exception_containment.py` passes | 5xx during the benchmark returned a structured JSON body with a correlation ID (poll error sample, §5) | **VERIFIED** |
| **TB-002** header scan 5 → 30 (now 50) rows | `HEADER_SCAN_ROWS` | `HEADER_SCAN_ROWS = 50` (raised further in `27e3ec4`) | `test_low_header_row.py` (row 41) passes | P4: header at row 50 → OK; at 51 → sheet skipped **with a visible reason** | **VERIFIED** (bounded by design) |
| **TB-005** bounded worksheet reads | Stop reading empty space | `_read_bounded_rows`: stop after 500 blank rows; cap columns at 500 when the declared width >500 | `test_stray_cell_bounded_scan.py` passes | **P2: a genuine second data block after 600 blank rows is silently dropped (10 of 20 rows lost) and reconciliation says `reconciles: True`.** P3: a sheet >500 columns with key fields beyond col 500 is skipped with a misleading reason | **PARTIAL.** Fixes the freeze; introduces silent data loss |
| **TB-001** summary-sheet classification | Require claim identity before emitting claims | `classify_sheet_status` → `non_claim_summary` if no claim ref and no (insured + date), with monetary fields bound | `test_non_claim_summary_sheet.py` passes | P10: a **real** claims tab keyed by policy number is also excluded (0 of 50 rows kept). **F3: French-header claims sheets with one monetary alias match are excluded (12,500 claims), and the report grades the file 5/5 with `score_reliable: True`** | **PARTIAL, with an S1 false-exclusion path** |
| **TB-003** scale multiplier from header suffix | "(USD m)" × 1e6 | `parse_scale_suffix`, applied in `apply_mapping` | `test_scale_suffix.py` passes | P11: correct and float-safe within tolerance. **But** it applies silently, with no UI display or veto (the handoff lists that as not done); bare "(m)", "(000)" and "(k)" scale; US "MM" (million) is not recognised. The multiplier is not recorded in the audit trail | **PARTIAL** (mechanism verified; human control absent, as stated) |
| **TB-007b** lone title rows excluded | Banner rows not claims | `_row_is_title`: exactly one populated text cell | `test_title_row_exclusion.py` passes | **P1: a claim row containing only its claim reference is excluded as a "title" and never flagged as missing mandatory fields** | **PARTIAL** (false positive on real rows) |
| Session 7 perf fix (workbook cache) | Stop re-reading the workbook per sheet | `pipeline_service.load_workbook_cached` (LRU 8) | Indirect | Synthetic 26k-row / 20-sheet file: confirming all 20 sheets took 0.68–0.74 s on SQLite (3 reps) and 0.96 s on Postgres (§5). `/process` hits the cache, so `job_ingest = 0.00 s` | **VERIFIED** (for a single worker process; the cache is not shared across workers and is unsynchronised across threads) |
| Session 7 "frontend never hangs" | 30 s/120 s fetch timeouts | `lib/api.ts` AbortController | none | **Partially disproved:** list pages swallow the resulting rejection and render empty-state text (§6) | **PARTIAL** |
| Session 7 "≈12.8–16.3 s total for 26k rows / 20 sheets" | — | — | — | Synthetic 26k/20-sheet file, same stages as the handoff (upload + confirm + process): 5.6–5.8 + 0.68–0.74 + 11.0–11.4 ≈ **17.4–18.0 s** SQLite (3 reps), **19.1 s** Postgres. Same order as the claimed 12.8–16.3 s; not the user's real file | **VERIFIED locally (order of magnitude, synthetic data)**; hosted **UNVERIFIED** |
| TB-009 dedupe blocking, TB-010, TB-011, TB-012 ("already exist") | — | Prefix blocking exists; three-state not-evaluable exists; JSON audit exists | Tests pass | Dedupe is super-linear (§5); the period problem (F1) | **PARTIAL** (exist; dedupe does not scale or model periods) |
| **Not done (per handoff):** basis consistency | Detect cumulative vs this-period mixing | Absent. Worse, aliases actively merge "paid to date" into CR0126 (this-month) | — | §3.2 | **ABSENT**, and the omission causes a standard-level defect |
| Per-row multi-currency / basis binding | — | Absent; the first currency suffix wins for the sheet | — | P9 | **ABSENT** |
| Scale multiplier audit / UI veto | — | Absent | — | P11 | **ABSENT** |
| Formal three-state value type | — | Behaviour exists (`_unparseable_*` flags + NOT_EVALUABLE); no type | — | — | **PARTIAL** (as stated) |
| Vocabulary expansion | — | ~100 English aliases; no multilingual list | — | French headers map only through the structural fallback (0 fields) or AI | **ABSENT** |
| Binding confidence scoring | — | Alias score shown; AI confidence discarded (1.0) | — | P18 | **ABSENT / BROKEN for AI** |
| Real worker-process queue | — | Daemon thread | — | §5: 250k-row job 257–263 s in the web process | **ABSENT** |
| Certification format pack | — | `.xlsx/.xlsm/.xls/.csv` only; `.ods`, `.xlsb`, encrypted, and encodings untested | — | P13 (cp1252 crash) | **ABSENT** |
| Formal L1–L6 CI ladder | — | No CI at all | — | — | **ABSENT** |
| README "alembic runs automatically on container start" | — | Only in docker-compose | — | Code reading | **PARTIAL** |
| Handoff "eslint clean" | — | — | — | 5 errors | **BROKEN at HEAD** |
| Handoff "backend 18 passed" | — | — | — | 25 pass / 2 fail on a clean checkout | **PARTIAL** (environment-dependent) |
| "Payment-leakage, v5.2 template, PDF pack exist on another branch" | — | Present on `claude/great-gauss-082g8l` (`9fb63d0`), not on main | Not run | Not run | **VERIFIED to exist; function UNVERIFIED** |
| Schema docstring: "Field codes match … v5.2" | CR codes as in v5.2 | Codes are v5.2 numbers with invented `M`/`CM` suffixes. **CR0126 is used as generic "paid", but v5.2 CR0126 is "Paid this month – Indemnity"** | — | §3.2 | **BROKEN** (semantics) |

### 3.2 The v5.2 incurred-arithmetic defect (highest-severity finding)

**Primary source** (Lloyd's Coverholder Reporting Standards v5.2 User Guide,
fetched and quoted this session [B1.1]):

> CR0155 — Total Incurred as a result of any fees or claims — "The total
> amount incurred as a result of the claim and any fees paid. This can be
> calculated as follows: The sum of: 'Total paid this month indemnity',
> 'Previously paid indemnity', 'Reserve indemnity', 'Total paid this month
> fees', 'Previously paid fees', 'Reserve fees'. Or the sum of: 'Total
> Incurred Indemnity', 'Total Incurred Fees'."
>
> Claims fields include: CR0126 *Paid this month – Indemnity*; CR0128
> *Previously Paid – Indemnity*; CR0130 *Reserve – Indemnity*; CR0134
> *Total Incurred – Indemnity* (plus CR0127/0129/0131/0135 for fees).

**TrueBind** (`bordereaux/src/bordereaux/schema.py`,
`validation.py · _check_arithmetic`):
- `CR0126CM` is named "Indemnity paid (this period)", yet its aliases include
  "paid to date", "paid ytd", "cash paid ytd" and "amount paid to date".
- CR0128 (previously paid) and all fee fields are **absent** from the schema.
- The check is `incurred == paid + reserve`, with tolerance 0.01.

**Consequences:**
- A v5.2-conformant file with `paid this month = 100, previously paid =
  900, reserve = 500, total incurred = 1500` is flagged **MISMATCH**,
  because 100 + 500 ≠ 1500. Every claim with prior payments is a false
  positive. The exception rate feeds the composite score, so the grade
  falls with it.
- A file that *does* balance in TrueBind (because "paid" was mapped from a
  paid-to-date column) is correct only by accident of alias choice, and it
  stores a cumulative number in a field whose v5.2 meaning is "this month".
- The literature says a visible false positive costs trust fast
  (algorithm aversion [A3.8]). This is the headline check.

**Status: BROKEN against the standard.** It passes every existing test
because no test encodes the v5.2 definition. This is a direct instance of
"passing tests ≠ correct" [A4.3].

---

## 4. New defects found by independent probes

All results are observed output from
`probes/probe_correctness.py` and `probe_followup.py` (Appendix A) against
`eee00cf`. Severity is judged for a claims-assurance product: **S1** silent
wrong answer, **S2** visible but misleading, **S3** robustness.

| ID | Input | Observed | Expected | Severity |
|---|---|---|---|---|
| **F3** | 25k-row, 20-sheet workbook; 10 sheets with French headers (`Référence sinistre`, `Nom de l'assuré`, … `Réserve`) | Only `Réserve` alias-matches, so each French claims sheet is classed `non_claim_summary`. **12,500 of 25,000 claims (50%) leave the claim set.** Report: **grade 5 "Excellent", `score_reliable: True`, `fully_covered: True`** (also seen via HTTP in benchmark `F_multilingual`) | "Partial / needs mapping", as a fully opaque sheet already gets | **S1: the worst failure class for an assurance product.** A partly recognised sheet is treated worse than an unrecognised one |
| **P2** | 10 rows, then 600 blank rows, then 10 rows | kept 10, excluded 0, `reconciles: True`, `source_data_rows: 10` | 20 rows, or an explicit "stopped reading at row N" | **S1** |
| **P5** | Date column `03/04/2024`, `05/06/2024`, `2024-07-08` | Parsed 2024-03-04, 2024-05-06 (month-first) | The dd/mm reading (2024-04-03, 2024-06-05), or ask | **S1** |
| **P5b** | All-ambiguous dd/mm column | Parsed day-first (by list order) | Correct only for UK senders; US mm/dd senders get day/month swapped silently | **S1** (locale-dependent) |
| **P6** | `"1.234"` | 1.234 | Ambiguous: 1234 in a European file | **S1** (locale) |
| **F2** | 7-column sheet, 10 claims, then `Total, -, -, 1000, 500, 1500` | 11 claim rows; Σ incurred 3000 (true 1500) | Subtotal excluded (it is, in a 12-column sheet) | **S1** (visible as a missing-name exception, but totals are wrong) |
| **P17** | Rows "TOTAL CLAIMS", "Sum" with amounts | Kept as claims | Excluded or flagged | S1/S2 |
| **P9** | `Paid (GBP)=100`, `Reserve (EUR)=50`, `Incurred=150` | currency GBP; **arithmetic MATCH** | Not evaluable (mixed currency) | **S1** |
| **P1** | Row with only `C2` in Claim Ref | Excluded as "title"; 0 missing-mandatory exceptions | Kept and flagged missing fields | **S1** (shows in the excluded ledger, not as an error) |
| **F1** | 200 claims × 12 monthly tabs (a normal multi-period workbook) | 13,200 exact-duplicate pairs; dup rate 100%; grade 2 | Movements per period; 0 duplicates | **S2** (visible, drives users away) |
| **P7/P7b** | `Paid`, `Paid to Date`, `Amount Paid` | All proposed → CR0126 at 100%; the last one wins at apply | Flag the conflict; ask which | **S1** |
| **P10** | Claims tab keyed only by Policy Number | `non_claim_summary`, 0 rows in the claim set, `fully_covered: True` | Partial / needs review | S2 |
| **P11b** | Suffixes `m`, `k`, `000`, `per 000` | ×1e6, ×1e3, ×1e3, ×1e3 applied silently | Show and confirm (US "M" can mean thousands) | S2 |
| **P12** | Formulas without cached values | Incurred NA → 3 not evaluable | Correct refusal (good behaviour) | — |
| **P13** | cp1252-encoded CSV | `UnicodeDecodeError` → HTTP 422 with a raw Python message | Detect the encoding | S3 |
| **P13b/c** | `;`-delimited CSV; CSV with title rows | One column / garbage headers | Sniff the delimiter; detect the header like xlsx | S3 |
| **P14** | Hidden sheet "OldData", hidden row | Both ingested as claims | At least flag hidden content | S2 |
| **P18** | AI mapper returns two headers → the same field | Both `ai`, confidence 1.0 | Keep the model's confidence; flag conflicts | S2 |
| **P19** | Any `currency_inconsistency` / `date_*` / `invalid_status` finding | Persisted with `check_type=MAPPING_COMPLETENESS` (`persistence_service.py:321`); 3,446 of them in the 250k run | Correct check type | **S2** (wrong UI tab; AI triage then misattributes the whole sheet to "ingestion") |
| **P3** | 600-column sheet with key fields at col 600 | Sheet skipped: "no row in the first 50 matched" | Read, or say "columns beyond 500 not read" | S3 |

## 5. Performance forensics (LOCAL only; hosted UNVERIFIED)

Environment: 4 vCPU / 15 GB container, uvicorn with 1 worker, SQLite or local Postgres 16, synthetic workbooks, no AI key. There was a single run per configuration except B_26k (3 reps), so p95/p99 across runs are not meaningful.

| Rows (1 sheet, 10 cols) | DB | Upload s (server blocked) | Processing s | dedupe s | persist s | Summary GET s | Duplicates GET s / MB | Peak RSS MB | Poll 5xx |
|---|---|---|---|---|---|---|---|---|---|
| 1k | SQLite | 0.5 | 1.0 | 0.06 | 0.36 | 0.04 | 0.02 / 0.01 | 240 | 0 |
| 10k | SQLite | 2.3 | 4.2 | 0.44 | 3.38 | 0.50 | 0.12 / 0.21 | 321 | 0 |
| 25k | SQLite | 4.7 | 11.2 | 1.93 | 8.86 | 1.29 | 0.54 / 0.97 | 413 | 0 |
| 50k | SQLite | 9.5 | 25.0 | 6.52 | 18.0 | 2.66 | 2.0 / 3.7 | 556 | 0 |
| 100k | SQLite | — | — | — | — | — | — | — | Driver crashed on a 500 "database is locked" poll |
| 100k | Postgres | 18.8 | 68.8 | 24.6 | 43.0 | 5.7 | 10.7 / 14.2 | 865 | 0 |
| 250k | SQLite | 46.9 | 255 | 144 | 109 | 19.3 | **38.2 / 85.3** | 1,734 | **5** |
| 250k | Postgres | 46.5 | 261 | 144 | 115 | 17.6 | **52.9 / 85.3** | 1,755 | 0 |

Variants at ~25k rows (SQLite):
- **20 sheets:** upload 5.7 s, confirm 0.7 s, process 11.0 s.
- **Columns (40 / 100):** upload **18.2 / 47.6 s**, against 4.7 s at 10 columns. Cost scales with cells; ~70% is openpyxl parsing.
- **Exceptions at 100%:** summary GET 7.1 s.
- **Multilingual:** 50% of claims dropped under a grade-5 report (F3).

Not run (session stopped): the Postgres 1k–50k ladder, a 70k × 100-column upload (predicted to exceed the 120 s client timeout), the 100k SQLite rerun, and the browser test (script written, not executed). AI latency and cost were not measured (no key).

## 6. Failure matrix

| Cause | Evidence | Status |
|---|---|---|
| `async` upload route blocks the whole server | `/health` blocked 18.7 s @100k, 46.3 s @250k | Reproduced |
| Wide files: upload scales with cells | 25k × 100 cols = 47.6 s | Reproduced; client timeout extrapolated |
| SQLite lock → 500 on poll | 100k crash; 5 × 500 @250k | Reproduced |
| Unpaginated duplicates beyond the 30 s frontend timeout; no catch → the empty state claims "no duplicates" | 38–53 s / 85 MB @250k | Endpoint reproduced; UI inferred from code |
| Super-linear dedupe, slow ORM persist, 1.7 GB RAM | §5 | Reproduced |
| cp1252 CSV, long filename, re-process doubling | P13, S2, S10 | Reproduced |
| Hosted infrastructure / AI latency | No deployment, no key | Unknown |


---

## 7. The problem: how DA data actually moves

(Built from primary and industry sources. It has **not** been validated by
interviews in this phase, which is experiment X-1.)

1. **Binding authority.** A managing agent or insurer delegates underwriting
   and/or claims authority to a coverholder, MGA or TPA/DCA. The contract
   requires periodic **risk, premium and claims** reporting [B1.1].
2. **Senders prepare bordereaux** from their own systems, usually as Excel or
   CSV. **Lloyd's specifies the data, not the format** [B1.1]. Layouts differ
   by sender, class and territory, and v5.2 "often varies significantly" in
   practice [B5.4]. Local offices and LM TOM class standards add fields
   [B1.1].
3. **Transmission** by email or portal, monthly or quarterly. Reporting lags
   of 30–90 days are reported [B5.9] (T3).
4. **Receipt and ingestion.** Formerly via DDM (mandated); since 13 Sep 2024 by
   the MA's chosen BMS (VIPR, Tide, others), in-house tools, or Excel [B2.1,
   B1.2].
5. **Mapping** to the internal or v5.2 schema, with re-mapping when a sender
   changes format (claimed to be manual in incumbents by a competitor [B5.10];
   unverified).
6. **Validation:** completeness, arithmetic, dates, currency, **binder-term
   compliance** (limits, territory, class), and period-over-period
   consistency. Incumbents document binder and history checks [B5.2, B5.7].
7. **Exception management:** queries back to the sender; corrections;
   re-submission.
8. **Reconciliation** of premium to cash (credit control), of claims to
   paid amounts, and of bordereau totals to the ledger.
9. **Downstream:** claims and underwriting systems, reserving (actuarial;
   Solvency II data-quality duty [B3.1]), reinsurance, Lloyd's and
   regulatory reporting, and oversight/audit (Lloyd's DA oversight [B2.2];
   FCA outcomes monitoring [B3.2]).
10. **Oversight:** audits of coverholders; removal for failures (Lloyd's
    removes "a coverholder around every two months over behaviour concerns"
    [B2.3], headline only).

**Where quality breaks (evidence-weighted):** at step 2 (sender systems and
Excel manipulation [A1.1, A1.4, A1.6]), step 5 (semantic mapping: the
v5.2 "paid" basis ambiguity is itself an example, §3.2), step 6 (checks
missing because they are laborious [A1.5]), and step 9 (lag makes data stale
for portfolio decisions [B2.2]).

**Where provenance matters:** whenever a number is used for reserving,
reporting or oversight. The regulator's test is "complete, accurate,
appropriate" [B3.1], which requires knowing *which rows were used, which
were excluded and why*. That is precisely the ledger TrueBind already keeps.

**Where an independent assurance layer can add value** (hypothesis):
between receipt and the BMS (a pre-ingestion screen, the Bordereaux Sync
slot), and after the BMS as an evidence pack for oversight and audit.

---

## 8. Peer-reviewed research: what it implies

(Full citations in the source register, Section A.)

**Spreadsheet error** [A1.1–A1.12]
- Errors are pervasive in operational spreadsheets [A1.1, A1.4]. The
  prevalence literature is heterogeneous in its definitions, which is a
  reason for caution [A1.3].
- Humans reviewing spreadsheets find only part of the errors [A1.5].
- Silent type coercion corrupts real datasets at scale [A1.12], which is the
  same mechanism as P5/P6.
- "Data debugging" of input values is academically established [A1.8].
- *Applicability:* this supports automated, value-level checking of inbound
  bordereaux. It does not show that any particular tool, TrueBind included,
  catches more than humans. That needs X-2 and X-5.

**Trust and automation** [A3.1–A3.14]
- Design for **calibrated** reliance, not maximal reliance [A3.1].
- Automation bias makes users miss what the tool does not flag [A3.4,
  A3.5]. Training does not remove it [A3.3].
- Explanations raise acceptance even when the AI is wrong [A3.12].
  Per-case confidence helps calibration [A3.11]. Cognitive forcing reduces
  over-reliance [A3.13]. Over-reliance falls when verification is cheap
  [A3.14].
- One visible error can drive users away (algorithm aversion) [A3.8].
- *Applicability to TrueBind:*
  - (a) A green grade on a partially-read file is dangerous (P2/P10 make
    this concrete).
  - (b) "Not evaluable" and "could not verify" states are well founded and
    should be *more* prominent than the grade.
  - (c) AI confidence must be real (P18 violates this).
  - (d) False positives, as in F1 and §3.2, are adoption-critical.

**Data quality / schema matching / entity resolution** [A2.1–A2.8]
- Name-only schema matching is known to be weak [A2.4]. LLMs help bootstrap
  it, but verification effort is the cost that matters [A2.5].
- Record linkage needs explicit error-rate trade-offs and good blocking
  [A2.6–A2.8]. TrueBind has fixed thresholds and weak blocking, and it
  scales super-linearly (§5).
- Declarative checks plus monitoring over time are proven at scale
  [A2.3], which is the model for "monitor forever".

---

## 9. Industry and regulatory environment

| Question | Evidence-based answer |
|---|---|
| What is being standardised? | The **data set** (v5.2 core fields [B1.1]); optionally ACORD formats [B1.1]. Market services (DDM) offered central standardisation, but it is now elective [B1.2]. |
| What is still messy? | **Formats, layouts, semantics (paid basis, scale, currency), timeliness.** v5.2 mandates no format [B1.1]; "5.2 varies significantly" [B5.4]; lags of 30–90 days [B5.9]. |
| What is being automated? | Ingestion and mapping (every vendor markets AI), validation against binder terms (VIPR, Send), warehousing (VIPR on Snowflake). |
| Where are humans still required? | Confirming semantics, resolving queries with senders, signing off for reserving and oversight, and handling new formats. |
| What happens before DDM/BMS? | The sender's own extraction and Excel manipulation, which is where spreadsheet-error research applies. |
| What happens after? | Reserving, reinsurance, regulatory reporting, oversight: the Solvency II data-quality duty [B3.1] and FCA outcomes evidence [B3.2]. |
| Where does quality break? | Sender preparation, mapping semantics, missing checks, staleness (§7). |
| Where does provenance matter? | Reserving and oversight evidence [B3.1, B3.2]. |
| Where can independent assurance add value? | A pre-BMS screen and a post-BMS evidence pack (hypothesis, G1 in the Competitive Landscape). |
| Is today's architecture permanent? | **No.** DDM went from mandated to elective in 2024 [B2.1]. Exchange-at-source models (distriBind) aim to remove spreadsheets entirely [B5.6]. **Any TrueBind design must survive the file disappearing**: rules and evidence should apply to API or JSON submissions too. |
| Primary sources that could *not* be retrieved | Velonetic Blueprint Two DDM / DA-data-strategy pages (HTTP 403); Lloyd's 2025 Market Oversight Plan (claimed by a T4 source; not verified); LMA survey on DDM (claimed by T4; not verified); PRA "Solvency UK" data-quality text (not fetched). |

---

## 10. Competitor map (summary)

See `TRUEBIND_COMPETITIVE_LANDSCAPE.md` for full profiles. In short:

- **HIGH threat:** Charles Taylor Tide + **Bordereaux Sync** (standalone
  pre-BMS AI screen, Microsoft co-developed); **VIPR** (lifecycle breadth,
  binder- and history-aware validation, Snowflake data cloud, managed
  services, Bridgepoint-backed).
- **MEDIUM–HIGH:** Vellum (AI-native, broad data model including RI).
- **MEDIUM:** Verodat (€15k trial, the only public price), Send
  (binder-rule validation, submission schedules), Scrub AI (API cleansing),
  distriBind (exchange that removes spreadsheets).
- **Adjacent:** OneSchema and Flatfile (generic importers), Duco
  (reconciliation), Cytora/Applied (intake AI), Great Expectations, Soda,
  Monte Carlo and Deequ (DQ monitoring patterns).
- **TrueBind is behind on breadth.** Its candidate differentiator (the
  refuse-to-guess ledger) is *undocumented* by competitors, which is not
  the same as absent.

---

## 11. Gap map

| Problem | Current industry solution | Remaining pain | Who suffers | Economic cost | Frequency | Severity | Workaround | Why unsolved | Possible TrueBind role | Confidence | Gap status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Heterogeneous inbound formats | BMS ingestion + AI mapping (VIPR, Tide, Vellum…) | Re-mapping on format change (claimed [B5.10]) | DA ops analysts | Analyst hours per new/changed format (unmeasured) | Monthly × senders | Medium | Excel, templates | v5.2 mandates no format [B1.1] | Fast human-confirmed mapping with saved per-sender versions | Medium | **PARTIALLY SOLVED** |
| Semantic errors (basis, scale, currency, sign) | Validation rules in the BMS | Silent mis-binding is invisible to rule checks | Reserving, finance | Mis-stated incurred/paid (unquantified) | Unknown | **High** | Manual spot checks | Needs per-column semantic confirmation, which tools don't surface | Explicit basis/scale/currency binding with veto; v5.2 decomposition checks | Medium | **MATERIALLY UNSOLVED?** (no evidence that incumbents solve it; unverified) |
| Silent row loss / partial reads | Row counts, where done | Tools seldom prove *every* source row was accounted for | Oversight, audit | Missing claims ⇒ under-reserving | Unknown | High | Manual totals | Hard to prove absence | **Row-level ledger** (TrueBind's asset, once P2 is fixed) | Medium | **UNKNOWN** (competitors don't document it) |
| Staleness | Portals, APIs, exchange (distriBind) | Lags of 30–90 days [B5.9]; CUO "bizarre" [B2.2] | Underwriting leadership | Late portfolio action | Continuous | High | Chasing | Sender systems and incentives | Submission schedule tracking (Send has it) | Low | **PARTIALLY SOLVED** |
| Binder-term compliance | VIPR, Send documented [B5.2, B5.7] | Unknown | DA oversight | Out-of-authority risks | Monthly | High | Manual review | Contract data not machine-readable | Out of scope for now (needs contract ingestion) | Low | **PARTIALLY SOLVED** by incumbents |
| Evidence for oversight and audit | Manual packs, BMS reports | Assembling "what was checked, what wasn't" | Compliance, audit, Lloyd's oversight | Staff time; regulatory risk | Quarterly/annual | Medium–High | Excel plus screenshots | Tools optimise throughput, not evidence | **Evidence pack** from the ledger + mapping provenance + rules | Medium | **UNKNOWN → test with X-10** |
| Period-over-period consistency | VIPR "previously processed data" [B5.2]; Vellum "mix shifts" [B5.4] | Unknown depth | Claims ops | Undetected reserve movements | Monthly | Medium | Manual | Needs history per claim | Movement checks (needs a period model; TrueBind has none, F1) | Low | **PARTIALLY SOLVED** |
| Duplicate reporting | BMS duplicate checks | False positives across periods | Claims ops | Review time | Monthly | Medium | Manual | Period semantics | Period-aware dedupe | Medium | **PARTIALLY SOLVED** |
| Sender-side preparation quality | VIPR Portal, distriBind | Senders get feedback only after sending | Coverholders/TPAs | Queries, oversight risk | Monthly | Medium | Re-work | Tools are buyer-side | Readiness check (E4) | Low–Medium | **UNKNOWN → X-11** |

**Why gaps persist** (evidence-weighted):
- (1) Format freedom is by design [B1.1].
- (2) The central service was rejected by the market [B2.1], so tooling is
  fragmented.
- (3) Incumbent incentives favour throughput and breadth over proving
  absence.
- (4) Semantic ambiguity (basis, scale) needs human judgement, which tools
  either hide ("repair" [B5.1]) or skip.
- (5) Humans are poor at spotting what tools don't flag [A3.5].

**What remains unsolved, with evidence:** we can say with **medium**
confidence that *semantic* and *completeness* assurance with evidence is not
visibly offered as a product. We **cannot** say it is unsolved inside
VIPR or Tide without hands-on trials (X-9). **Overall verdict:
PARTIALLY SOLVED, with a possibly MATERIALLY UNSOLVED sub-gap (semantic and
completeness assurance with evidence) that is unproven.**

---

## 12. The true product category

Assessed in `TRUEBIND_MARKET_EXPANSION.md` §4. **Conclusion:** a
**delegated-authority data-assurance layer** (a check plus an evidence pack),
packaged first as a UI product with a managed-service option. It becomes an
assurance API later only if correctness and demand are proven. It should
**not** try to be a BMS, a DA platform or an "insurance data OS", and it
should not market itself as "AI ingestion" (commodity).

---

## 13. Does TrueBind close the gap? (per pain point)

| Pain point | Solves now | Could, with modification | Cannot | Should not try | Needs partners | Needs humans |
|---|---|---|---|---|---|---|
| Heterogeneous formats | ◐ (xlsx/xls/csv; header detection) | ✔ saved mappings, encoding/delimiter sniffing, `.ods`/`.xlsb` | | | | ✔ confirm |
| Semantic errors (basis/scale/currency) | ✖ (§3.2, P9, P11) | ✔ v5.2 decomposition; per-column basis/scale/currency confirmation | | | | ✔ must confirm |
| Silent row loss | ◐ ledger exists; P2 breaks it | ✔ remove silent truncation; report the scan extent | | | | |
| Staleness | ✖ | ◐ schedule tracking | ✖ sender behaviour | | ✔ portals/exchange | |
| Binder-term compliance | ✖ | ◐ (needs contract data) | | ✔ not now | ✔ BMS | ✔ |
| Evidence for oversight | ◐ (audit log, reconciliation, excluded rows) | ✔ evidence pack | | | | ✔ sign-off |
| Period consistency | ✖ (F1) | ✔ period model + movement rules | | | | |
| Duplicates | ◐ (exact refs; fuzzy) | ✔ period-aware, clustered | | | | ✔ review |
| Portfolio analytics | ✖ | | | ✔ (crowded) | | |
| Sender readiness | ✖ | ✔ same engine, inverted UX | | | | |

**Each proposed change: what it changes, why, how, evidence, risks, measurement**

| Feature | What it changes | Why it matters | How | Evidence | What could go wrong | Measure |
|---|---|---|---|---|---|---|
| v5.2 incurred decomposition | Arithmetic uses CR0126 + CR0128 + CR0130 (+ fees) = CR0155/CR0134 | The headline check is currently wrong | New fields, alias split, NOT_EVALUABLE when a component is unmapped | [B1.1] | Senders that report only cumulative paid; needs a "basis" choice | X-0; false-mismatch rate on X-2 files |
| Basis/scale/currency confirmation | Per-column interpretation shown and vetoable | Prevents silent magnitude and basis errors | Mapping UI shows "values interpreted as USD × 1,000,000, cumulative"; requires explicit confirmation for amount columns | [A3.13] cognitive forcing; P7, P9, P11 | Friction; reviewers click through [A3.5] | Time per confirmation (X-6); error-injection catch rate |
| No silent truncation | Scan extent reported, never dropped | Restores the ledger's truthfulness | Bounded scan reporting "stopped at row N after M blank rows; K cells beyond ignored" | P2 | Pathological files slow down | Ledger vs independent row count on X-2 |
| Period model | Claims keyed by (ref, period) | Removes F1 false duplicates; enables movement checks | Detect the period per sheet or column; ask when ambiguous | F1; VIPR does history [B5.2] | Wrong period detection | Duplicate precision (X-5) |
| Evidence pack | Exportable proof of what was and wasn't checked | Oversight and audit need it [B3.1, B3.2] | Signed PDF + JSON: reconciliation, excluded rows, mapping provenance, rules, dispositions | [A3.1] purpose/process/performance visibility | Nobody reads it | X-10 |
| Saved mappings (pre-fill, not auto-apply) | Faster repeat files | Onboarding cost dominates economics | Unit Economics §5.2 | [A2.3]; X-4 | Propagating errors | X-4 |
| Real confidence | Show the model's confidence, calibrated | Trust calibration [A3.11] | Keep the returned confidence; calibrate on labels | P18 | Poor calibration | Brier score vs labels |

---

## 14–16. Product expansion, new markets, integrations, API

**Expansion and markets:** see `TRUEBIND_MARKET_EXPANSION.md`. The
recommended order is E1 (fix the core) → E5 evidence packs and E4 sender
readiness → E2 premium → E11 monitoring. Deprioritise loss runs, SOVs,
reinsurance and portfolio intelligence. The only non-insurance adjacency
worth a probe is accounting/audit PBC intake (X-12). Everything else is
parked.

**API / platform strategy**

| Surface | Now | Later (conditional) | Reason |
|---|---|---|---|
| Upload API | Internal only; add auth | Public, once auth + tenancy exist | Senders and BMSs push files |
| Mapping API | UI only | Expose saved-mapping registry read/write to partners | Only valuable once mappings are reusable |
| Validation / "check" API | — | **Primary API product**: submit → job → result + evidence | Embeds into BMS/TPA flows (E13) |
| Reconciliation API | — | Part of the check result | — |
| Exception API | UI | Webhooks on findings; status updates back | Workflow integration |
| Audit API | CSV export | Evidence-pack retrieval (JSON + PDF) | Oversight tools |
| Export API | CSV | Warehouse push (Snowflake/Postgres) | Customers keep data in their warehouse |
| Webhooks | — | Job complete / findings | Required for async APIs |
| Connectors | — | S3/Azure Blob/SFTP drop; SharePoint/Outlook intake | Where files actually arrive |
| Embedded components | — | Not recommended (OneSchema/Flatfile own this) | — |
| Partner portal | — | Only if sender-side (E4) wins | — |
| White label | — | Only if an incumbent asks | — |

**What stays UI:** human confirmation of semantics, exception review and
sign-off. These are human judgements and must not be hidden behind an API
default. **What becomes infrastructure:** the deterministic check, the
evidence generation, and the saved-mapping registry.

**Integrations ranked** (judgement; value / feasibility / distribution /
retention / switching cost / strategic):

| Rank | Integration | Value | Feasibility | Distribution | Retention | Switching cost | Strategic | Note |
|---|---|---|---|---|---|---|---|---|
| 1 | Microsoft 365 (Outlook, SharePoint/OneDrive intake; Entra ID SSO) | High | Medium | Medium | High | Medium | High | Bordereaux arrive by email [B5.9]; the London market runs on M365 (assumption) |
| 2 | Snowflake / Postgres / Databricks export | High | High | Low | High | High | High | VIPR Data Cloud is on Snowflake [B5.2]; feed warehouses, don't replace them |
| 3 | S3 / Azure Blob / SFTP drop | Medium | High | Low | Medium | Low | Medium | Simple automation path |
| 4 | Identity providers (Entra ID, Okta via OIDC/SAML) | Required | High | — | — | — | Required | Enterprise gate |
| 5 | BMS connectors (VIPR, Tide) | High | **Low** (partnership needed) | **High** | High | High | High | Only via partnership |
| 6 | SIEM/observability (OpenTelemetry, Datadog, Sentry) | Medium | High | — | — | — | Medium | Ops and security evidence |
| 7 | Guidewire / Duck Creek / claims platforms | Medium | Low | Medium | High | High | Medium | Later; heavy integrations |
| 8 | Salesforce | Low | Medium | Low | Low | Low | Low | Not where bordereaux live |
| 9 | Google Drive | Low | High | Low | Low | Low | Low | Market skews to M365 (assumption) |
| 10 | Accounting systems | Low (for claims) | Medium | — | — | — | Low | Relevant only for premium/credit control (E2) |
| — | Lloyd's / DDM ecosystem | Uncertain | Unknown (Velonetic pages inaccessible) | — | — | — | Watch | Now elective; monitor Blueprint Two changes |

---

## 17–18. Business model, unit economics, AI economics

See `TRUEBIND_UNIT_ECONOMICS.md`. Key points:
- **Variable cost per file is cents.** Measured compute is 121–447 CPU-s
  at 100k–250k rows. LLM calls are estimated at ≈ $0.002–0.006 each.
- **People cost** (onboarding, support, sales) decides viability.
  Onboarding hours per sender is the single biggest lever.
- **Base-case hypothesis:** 30 senders × £100/sender/month → £36k/yr,
  about 60% year-1 gross margin, CAC payback about 16 months. Every input
  is an assumption to replace with X-1/X-8 data.
- **AI is justified** for proposing mappings and sheet classes and for
  narrating pre-computed aggregates. **Never** for arithmetic, counts,
  currency, scale or the pass/fail decision (§20).
- **The feedback loop ("map once") must pre-fill, never auto-commit**, with
  drift detection and no automatic cross-tenant learning (Unit Economics
  §5.2).

---

## 19. Security

**Stance:** every uploaded file is hostile. Probes S1–S10 were run over
real HTTP against `eee00cf` (uvicorn, SQLite, fresh DB; script
`probes/probe_security.py`). Guidance: OWASP File Upload [B4.1], OWASP LLM
Top 10 2025 [B4.2], openpyxl's security note [B4.3], OWASP CSV Injection
[B4.4], NIST AI RMF / GenAI profile [B3.4].

| # | Probe | Observed | Severity | Guidance | Fix |
|---|---|---|---|---|---|
| **S1** | Upload filename `../../pwned_probe.xlsx` | HTTP 200. `file_name` stored verbatim. **File written to `backend/data/pwned_probe.xlsx`, outside `uploads/{id}/`** | **Critical** (arbitrary write of `.xlsx/.csv/.xls/.xlsm` anywhere the process can write) | [B4.1]: "generate random filenames server-side" | Store as `uploads/{tenant}/{uuid}`; keep the display name only in the DB |
| **S2** | 300-character filename | HTTP 500 (`OSError: [Errno 36] File name too long`) **after** the Report row was committed, leaving an orphan `PENDING_MAPPING` report with no stored file | High (integrity) | Same | Same fix; do file I/O before the DB commit, or in one unit of work |
| **S3** | 150 MB CSV (~3.3M rows) | Accepted. 42.1 s of blocked event loop. Server RSS 216 → 788 MB | High (DoS) | [B4.1] size limits | Request-size cap at the proxy and app; row/cell budget before full parse |
| **S4** | 22.5 MB xlsx that expands to 2M rows | Accepted after 128.9 s; **peak RSS 1,521 MB** | High (DoS / memory exhaustion) | [B4.1] "calculate decompressed file sizes" | Check zip entry sizes and ratio before opening; stream rows; run in a memory-limited worker |
| **S5** | Billion-laughs entities in `sharedStrings.xml` | 200 in 0.0 s; no blow-up. The Python/expat in this environment rejects entity amplification | Low here; **environment-dependent** | [B4.3] openpyxl: "does not guard… install defusedxml" | Add `defusedxml` anyway (costless) |
| **S6** | Cells `+cmd\|' /C calc'!A0`, `@SUM(1+1)*cmd…`, `=HYPERLINK(…)` | Written **unescaped** to `/export/by-status` CSV | High (client-side code execution when an analyst opens the export in Excel) | [B4.4] | Prefix `'` on cells starting with `= + - @ \t \r`; export as `.xlsx` with cells typed as text |
| **S7** | Unauthenticated `GET /reports`, `DELETE /reports/{id}` | 200 (all reports listed); 204 (deleted) | **Critical** for any shared deployment | [B4.1] "authentication before upload" | OIDC/SSO; tenant ID on every row and query |
| **S8** | `actor: "ceo@insurer.example"` in the confirm body | Recorded verbatim in `audit_log` | High (audit integrity) | — | Actor only from the authenticated identity; append-only audit table (DB permissions) |
| **S9** | `Origin: https://evil.example` on an error | No ACAO header (default config) | OK | — | Keep `CORS_ORIGINS` explicit; never `*` together with credentials |
| **S10** | `POST /process` twice on the same report | Both accepted; **exported_rows 2 for a 1-row source** (every claim persisted twice) | High (silent double-counting) | — | Idempotent processing: delete-and-replace inside a transaction, or refuse if COMPLETE |

**Other security findings (from code, not probed):**
- Uploaded originals are kept indefinitely, unencrypted, on local disk, with
  no retention policy.
- `processing_error` shows raw exception text (file paths) to users.
- No rate limiting.
- The AI mapping call has no timeout and no per-tenant budget (OWASP LLM10).
- Headers are sent to the model and are an injection surface (LLM01), but
  output is enum-constrained and a human confirms it. Residual risk is a
  poisoned *suggestion*, not an action.
- The anthropic SDK and pandas are unpinned (supply chain, LLM03).
- Macros in `.xlsm` are never executed by openpyxl (good), but the original
  file is retained and could be re-served if a download feature is added.
- Hidden sheets are processed (P14). They could carry data the sender did
  not intend to submit.

**Security requirements before any external user uploads a real
bordereau:** fix S1, S2, S7, S8 and S10; enforce size and decompression
budgets (S3/S4); make CSV exports injection-safe (S6); add `defusedxml`;
define retention and deletion; move processing to an isolated worker.
Tenant isolation must exist before a second customer.

---

## 20. AI safety boundary

**Principle:** the LLM may *propose, classify, explain and prioritise*. A
deterministic layer decides every number and every pass/fail, and a named
human confirms every semantic binding that changes a number's meaning.

| Decision | AI may | AI must not | Deterministic owner (today → required) |
|---|---|---|---|
| Header → field mapping | Propose with its **own** confidence | Auto-commit; claim 100% | `build_mapping` → human confirm (exists; the confidence is fixed to 1.0 today, **must change**) |
| Sheet classification (claims/summary/notes) | Propose | Exclude rows on its own | `classify_sheet_status` + human confirm for non-"claims" |
| Scale multiplier / unit | Suggest the reading of a suffix | Apply it silently | `parse_scale_suffix` → **must be shown and confirmed** (currently silent) |
| Currency / FX | Point out currency cues | Convert or sum across currencies | Deterministic currency binding per column/row; FX only from a cited rate table |
| Basis (this month vs cumulative) | Suggest | Decide | Human confirmation; v5.2 decomposition rules |
| Arithmetic, reconciliation, row counts | — | Anything | `validation.py`, reconciliation (deterministic) |
| Duplicate decisions | Explain a pair | Merge or drop rows | Deterministic flags + human review (exists) |
| Narrative / triage | Summarise pre-computed numbers | Compute or restate numbers | `exception_aggregation_service` (deterministic) + post-hoc number check (exists; well designed) |
| Audit records | — | Write or alter them | `audit_service.log_action` (append-only); actor from identity (**currently from the request body**) |
| Security permissions, DB integrity | — | Anything | Application code |

**Required guards** (mapped to OWASP LLM Top 10 [B4.2]):
- **LLM01** prompt injection via headers or sheet names: treat them as data,
  keep the forced-schema output, validate returned field codes against the
  enum (already constrained), and never let AI output trigger actions.
- **LLM02:** send headers only, never cell values (true today). Document it.
- **LLM05:** validate AI output as untrusted, including enums and
  uniqueness (P18).
- **LLM06:** no tools with side effects.
- **LLM09:** the number check on narratives (exists).
- **LLM10:** timeouts, retries and per-tenant budgets (missing on mapping).
- **Model migration:** the forced `tool_choice` will 400 on Opus 5.5 /
  Fable 5.1 [B7.1 skill notes]. Plan the change before switching models.

---

## 21. Agentic software-engineering evidence → how future sessions should work

| Evidence | Implication for TrueBind sessions |
|---|---|
| Tests can pass while behaviour is wrong: 29.6% of "plausible" SWE-bench patches diverge from ground truth [A4.3]; 31% pass only via weak tests [A4.4]; OpenAI found 59.4% of audited hard Verified tasks had flawed tests and stopped reporting Verified (23 Feb 2026) [A4.5] | TrueBind's own history shows the same pattern: a green suite alongside the v5.2 arithmetic defect and P2. **Require differential/spec-derived fixtures** (e.g. quote the v5.2 definition inside the test). |
| SWE-bench Pro targets long-horizon, contamination-resistant tasks [A4.2]; third parties report reward hacking via `.git` history [B6.4] (T4) | Don't trust agent self-reports of success. Verify via independent commands in a fresh context. "SWE-bench Pro *Verified*" was **not found** as a distinct benchmark; SWE-bench Verified and SWE-bench Pro are separate. |
| Test-driven interactive generation improves correctness [A4.6] | For data-rule changes, write the failing fixture from the standard **first**, get it reviewed, then code. |
| Experienced developers were 19% slower with AI while *believing* they were 20% faster [A4.7] | Measure throughput and defect escape, not perceived speed. |
| Vendor guidance: give the agent a check it can run; explore → plan → implement; short CLAUDE.md; fresh-context adversarial review; "if you can't verify it, don't ship it" [B6.1] | Adopt `TRUEBIND_STRATEGIC_ROADMAP.md` §5 as the operating procedure. Add a short `CLAUDE.md` pointing to the hermetic test + benchmark commands and the v5.2 fixture. |

---

## 22. UX / design requirements

Design principles extracted (not copied): Lightning's *Clarity, Efficiency,
Consistency* [B6.5]; Fluent's *Built for focus* [B6.6]; Apple's
*establish hierarchy* and *consistent feedback keeps people informed and in
control* [B6.7]; Linear's *Aim for clarity (don't invent terms)*, *Say no to
busy work*, *Simple first, then powerful* [B6.8]. No primary design-system
sources were retrieved for Stripe, Revolut or Higgsfield, so nothing is
attributed to them.

Requirements, each tied to evidence:

1. **Hierarchy of truth.** "What we could not check" and "what we did not
   read" sit *above* the grade, visually. Justification: automation bias
   [A3.5]; P2 and P10 show a green-looking report over a partial read.
2. **Never render an empty state for a failed fetch.** Error, retry and
   partial states must be distinct from "none found" (§6 browser finding).
3. **Per-column interpretation cards** in mapping: sample values → parsed
   values → unit/scale/currency/basis. Forced choice for amount columns
   (cognitive forcing [A3.13]; cheap verification [A3.14]).
4. **Real confidence, never "100%" from an LLM** [A3.11]; P18.
5. **Tables built for 10⁵ rows:** server-side pagination, grouping by cause,
   bulk dispositions with reasons, virtualised lists (the Duplicates page
   renders one `<li>` per pair: 106,684 at 250k rows).
6. **Progress feedback during upload and processing**, with stage and rows
   processed (a stage field already exists server-side), since uploads take
   18–47 s at 100k–250k rows.
7. **Accessibility:** the existing WCAG-AA contrast guard (`lib/colorContrast.ts`)
   is good; extend it to keyboard-only review flows.
8. **Terminology:** use the market's words (v5.2 field names, "previously
   paid") and never invent terms (Linear [B6.8]). The current UI's "grade"
   is an invented composite. Keep it secondary.
9. **Motion:** only to show state transitions (processing → complete). There
   is no evidence it adds value for this audience. Do not invest in it.

---

## 23. Future-state product architecture (conditional on experiments)

```
                    ┌─────────────────────────── UI (review & sign-off) ───────────────────────────┐
 Sender files  ──►  │ Intake (upload / email / SharePoint / S3)                                   │
 (xlsx/xls/csv/     │   → Hostile-file gate (size, zip ratio, defusedxml, type sniff, AV)         │
  later JSON/API)   │   → Job queue ──► Worker pool (memory/time limited, per-tenant)             │
                    │        Reader (bounded, NEVER silent: scan-extent report)                   │
                    │        Sheet & header detection  ── AI proposer (headers only) ──┐          │
                    │        Binding: field + basis + scale + currency + period        │          │
                    │           ▲ saved-mapping registry (pre-fill, drift demotion)     │          │
                    │           └──── human confirmation (forced for amount semantics) ◄┘          │
                    │        DETERMINISTIC TRUTH LAYER: parse → rule packs (v5.2 claims,          │
                    │          premium, binder terms later) → reconciliation ledger →             │
                    │          period movements → duplicates (period-aware)                      │
                    │        Evidence pack (JSON + signed PDF)                                   │
                    │   → Findings store (Postgres, tenant-scoped) → Review queue (paged)        │
                    │   → Exports: warehouse push, CSV (injection-safe), API, webhooks            │
                    │ Governance: identity (OIDC), append-only audit, retention, monitoring      │
                    └────────────────────────────────────────────────────────────────────────────┘
```

**Shared engine:** claims, premium, risk, sender-readiness, monitoring and
evidence packs all use the same reader, binding, truth layer and ledger.
They differ only by **rule pack** (data, versioned) and by UI entry point.

**Technical requirements**, derived from the §5–6 measurements:
- Parse off the event loop in a separate worker process.
- Postgres only, with SQLite for tests.
- Streaming or batched COPY persistence (persist is currently 43–115 s at
  100k–250k rows).
- Server-side pagination everywhere.
- Summary computed at persist time, not per GET.
- Bounded dedupe with clusters rather than pairs.
- Money as `Numeric`/Decimal rather than float.
- A size and complexity budget per file.
- Hermetic tests plus CI.
- An SLO: a 100k-row file end-to-end in under 60 s, with no request over
  2 s during processing (a target to set; not yet achieved: measured
  132.7 s end-to-end on Postgres).

---

## 24. Moat (honest assessment)

| Candidate moat | Exists today? | Durable? | Evidence |
|---|---|---|---|
| AI mapping | Yes | **No** (commodity; every competitor markets it) | Competitive Landscape §1 |
| Refuse-to-guess ledger (not-evaluable, excluded-row reasons, reconciliation) | Yes (with defects) | **Maybe.** Easy to copy technically; hard to copy *culturally* for vendors who sell "repair" [B5.1] | §2, §4 |
| v5.2 rule correctness | **No** (§3.2) | Low (public standard) | [B1.1] |
| Per-sender saved mappings and history | No | Medium (accumulates switching cost) | [A2.3] |
| Evidence packs relied on by auditors | No | **Medium–High** if adopted (process lock-in) | X-10 |
| Network of rule packs per capacity provider (sender side) | No | High if it happens; speculative | E4 |

**Conclusion:** there is **no moat today.** The plausible moat is
*institutional trust in the evidence*, and that requires correctness first.

---

## 25. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Incumbent (Tide/Sync, VIPR) already covers the assurance slot | Medium–High | High | X-9 before positioning; partner rather than compete if confirmed |
| No willingness to pay at viable price | Medium | High | X-1/X-8 gates; managed-service fallback |
| Correctness defects discovered by a prospect (e.g. §3.2) | **High if demoed today** | **Critical** (algorithm aversion [A3.8]) | Stop demos until X-0 passes |
| Access to real files blocked by confidentiality | High | High | NDA, anonymisation, on-prem or VPC option |
| Long enterprise sales cycles | High (assumption) | High | Managed-service pilots; sender-side PLG test |
| Security incident (hostile files, no auth) | Medium | High | §19 remediations before any external file |
| Market shift to exchange-at-source (no files) | Low–Medium over 3 years | Medium | Rules and evidence engine independent of file format |
| Agent-driven development repeats "green tests, wrong behaviour" | High (it has happened) | High | §21 procedure |
| Single developer / AI-only codebase maintainability | Medium | Medium | Hermetic CI, short handoffs |

---

## 26–28. Experiments and roadmaps

See `TRUEBIND_STRATEGIC_ROADMAP.md`:
- **Experiments:** X-0 (v5.2 conformance) through X-13 (hosted
  performance), each with hypothesis, test, sample, metric, pass/fail and
  decision.
- **12-month plan:** 0–30 days (correctness + reliability + honesty +
  recruiting) → 30–90 (real files, period model, worker queue, auth) →
  3–6 months (paid pilots, premium, evidence pack) → 6–12 months
  (monitoring, warehouse, API if pulled). Each stage is gated.
- **3-year plan:** Year 1 reliability + evidence (high confidence it is the
  right focus); Year 2 platform + integrations (conditional); Year 3
  network / adjacency (speculative).

---

## 29. Open questions

1. Do Tide/Bordereaux Sync or VIPR already produce a row-level "not
   read / not verified" ledger? (X-9)
2. How many hours per month does a DA team actually spend per coverholder
   file, and who owns the budget? (X-1)
3. What share of real claims bordereaux report paid *this month* versus
   *paid to date*, and with fees? (X-2). This determines how often §3.2
   bites.
4. Is the buyer the MA (receiver) or the coverholder/TPA (sender)? (X-1,
   X-11)
5. Will auditors accept an automated evidence pack? (X-10)
6. What does the hosted environment look like (provider, instance size,
   DB)? No deployment was found (no Vercel team; the only Supabase project
   is inactive and unrelated). (X-13)
7. Current Lloyd's DA data strategy after DDM became elective: Velonetic
   pages were inaccessible (403). Is any new mandate or API standard coming?
8. Does the leakage / governance / v5.2-template work on
   `claude/great-gauss-082g8l` function? (Not run.)

---

## 30. Final evidence-based conclusion

**What the evidence supports:**
- The problem is real, regulatory-anchored and durable: format freedom by
  standard [B1.1], 39% of Lloyd's GWP through delegation [B2.2], the
  Solvency II data-quality duty [B3.1], and human error in spreadsheets
  [A1].
- The post-DDM market is choosing tools now [B2.1].
- The HCI literature supports a product that makes *what was not verified*
  more visible than a score [A3].

**What the evidence does not support:**
- That TrueBind is currently correct: it is wrong on the v5.2 headline
  check (§3.2) and has several silent-loss or coercion paths (§4).
- That it is reliable at the file sizes a DA team sees: event-loop
  blocking, SQLite lock errors, 85 MB unpaginated responses, and an
  empty-state lie in the UI (§5–6).
- That it is differentiated from incumbents: Bordereaux Sync occupies the
  slot, and AI mapping is table stakes.
- That anyone will pay: no customer evidence exists.

**The strongest version of the company the evidence points to** is a
narrow, **standard-correct, refuse-to-guess assurance layer for
delegated-authority data**:
- It feeds existing BMSs and warehouses.
- It sells *evidence* (what was read, bound, checked and not checked, and
  who confirmed it), not "AI ingestion".
- It starts with claims (then premium) for London-market DA teams, possibly
  through a managed-service wedge.
- It keeps sender-side readiness and audit evidence packs as the two cheap,
  testable expansions.

This is a **hypothesis with medium–low confidence**, not a conclusion that
TrueBind will work.

**What would change this conclusion:**
- If X-9 shows incumbents already provide row-level non-verification
  evidence, the assurance positioning collapses. Pivot to integration or
  partnership, or to the sender side.
- If X-1/X-8 find no budget owner, stop or become a service.
- If X-2 shows real files break the engine in ways that can't be bounded,
  the engine needs a re-architecture before any market test.

---

## Appendix A: probe outputs (verbatim excerpts)

```
PROBE P1 claim-ref-only row | kept rows: 2 | excluded: [(3, 'title', 'C2')] | missing_mandatory exceptions: 0
PROBE P2 data after 600-blank gap | source data rows written: 20 | kept: 10 | excluded: 0 | reconciles: True | source_data_rows reported: 10
PROBE P3 >500 cols | columns read: 0 | 'Claim Ref' present: False | skipped: True no row in the first 50 matched enough known fields to be a header row
PROBE P4 header at row 50 | skipped=False header_idx=49 kept_rows=5 reason=None
PROBE P4 header at row 51 | skipped=True header_idx=0 kept_rows=0 reason=no row in the first 50 matched enough known fields to be a header row
PROBE P5 dd/mm + 1 ISO value | parsed: ['2024-03-04', '2024-05-06', '2024-07-08'] (dd/mm intent: 2024-04-03, 2024-06-05)
PROBE P5b dd/mm all-ambiguous column | parsed: ['2024-04-03', '2024-06-05']
PROBE P6 amount '1.234' -> 1.234 | '1,234' -> 1234.0 | '12,5' -> 12.5 | 'EUR 1,000' -> None | '0.5m' -> None | '(1,000)' -> -1000.0
PROBE P7 two cols -> same field | paid value: 900.0 | any warning: none raised
PROBE P7b fuzzy proposals: {'Paid': ('CR0126CM', 100), 'Paid to Date': ('CR0126CM', 100), 'Amount Paid': ('CR0126CM', 100)}
PROBE P9 GBP paid + EUR reserve | currency assigned: GBP | arithmetic match count: 1 | mismatch: 0
PROBE P10 policy-keyed claims tab | status: ['non_claim_summary'] | rows in claim set: 0 | grade: 1 | score_reliable: False | fully_covered: True
PROBE P11 scaled 0.1+0.2 vs 0.3 (m) | paid: 100000.0 reserve: 200000.0 incurred: 300000.0 | match: 1 mismatch: 0
PROBE P11b scale token false positives: {'m': 1000000.0, 'M': 1000000.0, 'k': 1000.0, '000': 1000.0, 'per 000': 1000.0, 'months': None, 'GBP': None}
PROBE P12 formula cells w/o cached values | incurred parsed: [<NA>, <NA>, <NA>] | not_evaluable: 3
PROBE P13 cp1252 CSV | EXCEPTION: UnicodeDecodeError 'utf-8' codec can't decode byte 0xe9 in position 35: invalid continuation byte
PROBE P13b semicolon CSV | columns: ['Claim Ref;Insured Name;Paid']
PROBE P13c CSV with title rows | columns: ['Bordereau for Q1 2024', 'Unnamed: 1', 'Unnamed: 2'] | skipped: False
PROBE P14 hidden row + hidden sheet | sheets read: ['Visible', 'OldData'] | rows: [2, 1]
PROBE P17 subtotal variants | kept claim refs: ['C1', 'Total', 'TOTAL CLAIMS', 'Sum', 'C2'] | excluded: []
PROBE P18 stub AI maps 2 headers to same field | results: [('Ref Sinistre', 'CR0104M', 1.0, 'ai'), ('Numéro', 'CR0104M', 1.0, 'ai')]
F1 realistic 200 claims x 12 monthly tabs | rows 2400 | exact pairs 13200 | probable pairs 0 | dup rate % 100.0 | grade 2 | pipeline 0.62s
F1b same 200 claims, one tab | exact 0 | probable 0 | grade 5
F2 totals row, 7 cols | claim rows kept 11 (10 real) | excluded [] | sum incurred 3000.0 (true 1500)
F2 totals row, 12 cols | claim rows kept 10 (10 real) | excluded ['subtotal'] | sum incurred 1500.0 (true 1500)
P19 (Postgres, after the 250k run): SELECT extra->>'rule', count(*) FROM validation_results WHERE check_type='MAPPING_COMPLETENESS' → currency_inconsistency | 3446
```

## Appendix B
Raw run data and scripts were in the session scratchpad and were not committed. §5 is the retained record.

