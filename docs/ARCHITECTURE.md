# TrueBind — architecture (current state, P0 baseline)

Written at the start of Platform V1 (branch `feat/platform-v1`, base `main` @ `af6b5da`).
It describes what the code does **today**; the target design lives in the phase plan
(PROGRESS.md) and is added here as each phase lands.

## 1. Components

| Component | Path | Tech | Role |
|---|---|---|---|
| Engine | `bordereaux/src/bordereaux` | Python 3.11, pandas, openpyxl/xlrd, rapidfuzz, pandera | Pure library: read workbook → detect sheets/headers → propose mapping → validate → dedupe → health report. No I/O beyond reading the file it is given. |
| API | `truebind-web/backend/app` | FastAPI, SQLAlchemy 2, Alembic, psycopg 3 | Tenancy, auth, uploads, jobs, persistence of engine output, review workflow, exports, audit. |
| Worker | `truebind-web/backend/app/worker.py` | multiprocessing (spawn) | Claims jobs from the `jobs` table; runs each in a child process with memory + wall-clock limits and a leased heartbeat. Embedded in the API process when `TRUEBIND_EMBEDDED_WORKER=1`. |
| Web | `truebind-web/frontend` | Next.js 16 (App Router, Turbopack), React 19, CSS modules | Marketing page, login/sign-up, dashboard (overview, upload + mapping review, reports, exceptions, duplicates, audit, exports, inbox, alerts, to-do, automations). |
| Legacy UI | `bordereaux/app.py` | Streamlit | Original single-user MVP; not deployed. |

## 2. Data flow (upload → report)

1. `POST /api/v1/reports/upload` — `security/file_guard.py` checks size, signature (xlsx/xlsm/xls/csv), zip-bomb ratios, sheet/row/cell caps. The file is written once to object storage under a server-generated key (`tenants/<tenant>/reports/<report>/source.<kind>`), SHA-256 recorded on the report row. An `INGEST` job is enqueued.
2. Worker → `job_handlers.ingest`: engine `load_workbook` + `propose_mapping_for_workbook`; per-sheet header detection and alias/fuzzy mapping (AI fallback via Anthropic when `ANTHROPIC_API_KEY` is set, bounded by `AI_MAX_CALLS_PER_REPORT` / `AI_TIME_BUDGET_S`). Proposals are stored in `sheets` + `mappings` with `mapping_state ∈ {MAPPED_BY_ALIAS, MAPPED_BY_AI, UNMAPPED, MANUAL}` and a review state.
3. User reviews and confirms each sheet (`POST .../sheets/{id}/mapping`); every confirmation/override is audited.
4. `POST .../process` enqueues `PROCESS`: engine `run_workbook_pipeline` with the confirmed mapping → canonical rows, validation results (incl. `NOT_EVALUABLE` when inputs are missing), duplicates vs development, health score. Persisted to `claim_rows`, `validation_results`, `excluded_rows`, `leakage_flags`, report summary; alerts and obligations derived.
   Duplicate detection is bounded: the probable (fuzzy) check first counts candidate row pairs (same name block, loss dates within 3 days) and, above `MAX_PROBABLE_CANDIDATE_PAIRS` (2,000,000), is not run and is reported under `not_assessed_checks` in coverage and the summary, with the score marked provisional (P1.7).
   Unsafe requests (`upload`, `process`) accept an `Idempotency-Key` (per organisation, 24 h, table `idempotency_keys` with RLS); jobs retry up to `JOB_MAX_ATTEMPTS`; with `REDIS_URL` an enqueue wakes an idle worker after COMMIT (`services/job_signal.py`), otherwise the worker polls. The database queue stays the source of truth.
   Channels (P2): every file, whatever its channel (web upload, API, e-mail via Postmark or SES/SNS), passes one intake gate (`services/intake_service.py`). Outputs go by download, SMTP, signed webhooks (Standard Webhooks HMAC, retries with backoff, replay, SSRF guard) or SFTP (pinned host key, atomic rename). ECB reference rates convert exactly in Decimal. AI (column suggestions and triage narratives) goes only through `app/ai/providers.py`, EU/UK providers only, with headers plus masked samples.
5. Review: exceptions/duplicates get review states; exports (CSV claims/exceptions/audit) and e-mail deliveries (`deliveries`) are audited.

## 3. HTTP API (46 operations; frozen in `scripts/openapi-snapshot.json`)

- **Auth**: `POST /auth/signup|login|logout`, `GET /auth/me` — HttpOnly session cookie (`auth_sessions`, hashed token), CSRF double-submit token (`X-CSRF-Token`), login rate limit (`security/ratelimit.py`, in-process).
- **Reports**: list/get/upload/delete/cancel/retry/process, sheets + mapping, claims, exceptions (+ review), duplicates (+ review), excluded rows, jobs, audit, summary, CSV exports, deliveries, obligations, AI exception summary.
- **Ops**: `/overview`, `/work-queue`, `/alerts` (+ acknowledge), `/obligations`, `/channels`, `/deliveries`, `/templates`, `/audit` (+ `/audit/verify`), `/system/status`.
- **Health**: `/health`, `/health/ready`.

## 4. Database (19 tables, Alembic 0001–0005)

`tenants, users, memberships, auth_sessions, jobs, worker_heartbeats, reports, sheets, mappings, claim_rows, validation_results, excluded_rows, leakage_flags, exception_summaries, obligations, alerts, deliveries, templates, audit_log`.

- **Tenancy**: every tenant-owned table has `tenant_id`; the app scopes each query via the request `Context`; on PostgreSQL migration `0002_pg_security` enables + FORCEs Row-Level Security with a `tenant_isolation` policy keyed on `current_setting('app.tenant_id')` (set per transaction by `database.set_tenant`). Cross-tenant IDs return 404 (tests: `test_tenant_isolation.py`, `test_rls_pg.py`).
- **Audit**: `audit_log` rows are hash-chained per tenant (`services/audit_service.py`: `entry_hash = SHA-256(prev_hash + canonical JSON)`), verified by `GET /audit/verify`; on PostgreSQL a trigger rejects UPDATE/DELETE.
- **Roles**: `OWNER, ADMIN, REVIEWER, VIEWER` (`models/identity.py`).
- **Money**: stored as `Float` in `claim_rows` and computed as pandas `float64` in the engine (see Discrepancies).

## 5. Configuration

`app/config.py` reads environment variables at import (plus `backend/.env` outside production unless `TRUEBIND_NO_DOTENV`). Key vars: `DATABASE_URL`, `TRUEBIND_ENV`, `TRUEBIND_EMBEDDED_WORKER`, `ALLOW_SIGNUP`, `CORS_ORIGINS`, `COOKIE_SECURE`, `SESSION_TTL_HOURS`, upload/job limits, `ANTHROPIC_API_KEY`, `SMTP_*`. Production refuses to start without a PostgreSQL `DATABASE_URL`.

## 6. Storage

`services/storage.py` — `LocalObjectStore` (atomic temp-file + rename, 0600, strict key regex). No S3 adapter yet. `retention_service.py` and `DELETE /reports/{id}` remove stored source files.

## 7. Tests (baseline, 2026-09-28)

| Suite | Command | Result |
|---|---|---|
| Engine | `pytest bordereaux/tests` | 86 passed |
| Backend (SQLite) | `pytest truebind-web/backend/tests -m "not integration"` | 121 passed, 4 skipped (PostgreSQL-only) |
| Backend (PostgreSQL, non-superuser, RLS live) | same with `TRUEBIND_TEST_DATABASE_URL` | 124 passed, 1 skipped (SQLite-only case) |
| Golden regression | `bordereaux/tests/test_boundary_fixture.py` on `test_boundary_cases.xlsx` | 8 passed — 10/10 sheets, 320 rows, 38 arithmetic mismatches, 16 duplicate pairs (32 rows), 68 missing-mandatory rows (48 + 26, 6 overlap), 0 false positives |
| Frontend | eslint, `tsc --noEmit` | clean (no unit/e2e tests existed; P0 adds vitest + Playwright) |

## 8. Deployment (today)

- Frontend: Vercel project `cleanbuild` (`cleanbuild-psi.vercel.app`; custom domain `truebind.ie` added, DNS pending). Browser calls `/api/v1` on the frontend origin; `next.config.ts` rewrites to `TRUEBIND_API_ORIGIN`.
- API: Render web service `cleanbuild-1` (Docker, `truebind-web/backend/Dockerfile`, `start.sh` runs `alembic upgrade head` then uvicorn with the embedded worker).
- Database: Render PostgreSQL (the service was still on SQLite at last check — see HUMAN_TODO.md).

## 9. Verification harness (added in P0)

`scripts/verify.py --fast | --full` (see its docstring); services in `docker-compose.test.yml`:
postgres (non-superuser `truebind_app`), redis, minio (`pgsty/minio` community build — upstream stopped publishing images), mailpit, sftpgo, mock-oauth2-server, stripe-mock, and a stdlib webhook receiver (`scripts/testenv/webhook_receiver.py`). Quality ratchet + baselines: `scripts/quality.json`.

## 10. Discrepancies between the Platform V1 brief and the code

Logged in PROGRESS.md; each is resolved in the phase named.

| # | Brief says | Code does | Resolution |
|---|---|---|---|
| D1 | Money is Decimal + ISO 4217 | `Float` columns; engine float64 with 0.01 tolerance | P1: new `Numeric(18,2)` storage + Decimal at the API boundary; engine arithmetic stays float with tolerance, quantised to Decimal on persist (golden unchanged). New modules (P3+) compute in Decimal. |
| D2 | NOT_ASSESSED | Engine/API use `NOT_EVALUABLE` | Same semantics; new `Finding.assessment` uses `NOT_ASSESSED`, legacy values mapped 1:1. |
| D3 | Tri-state mapping | 4 states (adds `MANUAL` = user-chosen) | `MANUAL` is a user decision, not a proposal source; it is treated as confirmed. Tri-state holds for proposals. |
| D4 | Roles owner/admin/analyst/viewer/sender | OWNER/ADMIN/REVIEWER/VIEWER | P1: REVIEWER → analyst (data migration), add sender. |
| D5 | Originals immutable, no delete path | `DELETE /reports/{id}` and retention delete source files | P1: storage has no delete; report deletion becomes a soft delete; retention moves to bucket lifecycle policy (documented), never app code. |
| D6 | Redis + worker | DB-backed job queue (leases, SKIP-LOCKED-style claims) + spawn worker | Brief: keep the existing worker. P1 keeps the DB queue as the source of truth; Redis is used for rate limiting/lockout and job wake-ups. |
| D7 | AI via EU-region, zero-retention provider behind an interface | Direct Anthropic API | P2: provider interface (Azure OpenAI EU, Bedrock EU), masking, fake provider; direct Anthropic path removed. |
| D8 | pydantic-settings config | raw `os.environ` | P1. |
| D9 | Ambiguous dates flagged | Column-level disclosure when *every* value is ambiguous; mixed columns follow the winning format | P3/P4 rules consume a per-cell `date_ambiguous` flag added in P1. |
