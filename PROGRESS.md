# TrueBind Platform V1 — progress (source of truth)

Branch: `feat/platform-v1`. Resume rule: read this file, BLOCKERS.md and HUMAN_TODO.md, then continue
from the first unticked task. Verify: `python scripts/verify.py --fast | --full` with the backend venv
Python (`truebind-web/backend/.venv`).

## Status

| Phase | State |
|---|---|
| P0 Recon & harness | **done** — gate green (see evidence) |
| P1 Platform foundation | next |
| P2 Channels & integrations | pending |
| P3 Binder compliance | pending |
| P4 Leakage & overpayment | pending |
| P5 Sanctions screening | pending |
| P6 Scorecard | pending |
| P7 Audit pack | pending |
| P8 Sender pre-flight portal | pending |
| P9 Billing & entitlements | pending |
| P10 Production readiness | pending |

---

## P0 — Recon & harness (no behaviour change)

### P0.1 Architecture + baseline
Acceptance:
- [x] `docs/ARCHITECTURE.md` describes modules, data flow, endpoints, tables, tests, deployment — file exists, 10 sections.
- [x] Baseline recorded (below), measured before any change.

Baseline (untouched `main` @ af6b5da, 2026-09-28):
- Engine: 86 passed. Backend SQLite: 121 passed, 4 skipped (PostgreSQL-only). Backend PostgreSQL (non-superuser, RLS live): 124 passed, 1 skipped (SQLite-only).
- Golden regression (`test_boundary_fixture.py`): 10/10 sheets, 320 rows, 38 arithmetic mismatches, 16 duplicate pairs = 32 rows, 68 missing-mandatory rows (48 claim ref + 26 insured, 6 overlap), 0 false positives, 0 not-evaluable.
- Frontend: eslint clean, tsc clean, npm audit 0. No frontend unit or e2e tests existed.
- Lint: 11 findings under ruff's minimal ruleset (E4/E7/E9/F); mypy (non-strict) 105 errors in 17 legacy files.
- Coverage (engine + backend on PostgreSQL): 89.69 %.

### P0.2 Harness
Acceptance:
- [x] `scripts/verify.py --fast`: ruff (legacy minimal ruleset + strict ruleset/format on new modules), mypy (strict on new modules, ratchet on legacy), engine + backend unit tests, eslint, tsc, vitest — `verify --fast` PASS.
- [x] `--full`: docker-compose.test.yml services (8), fresh-DB `upgrade head → downgrade -1 → upgrade head`, backend suite on real PostgreSQL + service integration tests, golden fixtures, `next build`, Playwright e2e (on PostgreSQL), pip-audit, npm audit --audit-level=high, bandit -ll, gitleaks (history + uncommitted + staged), coverage gate (total ≥ baseline, changed lines ≥ 85 %), OpenAPI snapshot diff — `verify --full` PASS.
- [x] One-screen summary, `verify-report.json`, non-zero exit on failure — shown in the runs below.
- [x] Windows: pure-Python driver, `shutil.which` for npx/npm (resolves `.cmd`), pathlib paths, `--install-tools` fetches the Windows gitleaks zip. (Not executed on Windows in this environment — see BLOCKERS B1.)
- [x] Existing golden regression wired as the `golden` step (plus any `fixtures/golden/*/test_*.py`).

Tests added: `truebind-web/frontend/tests/unit/lib.test.ts` (8 vitest), `tests/e2e/golden-flow.spec.ts` (Playwright: sign-up → upload golden workbook → confirm all → report asserts 38 arithmetic mismatches / 0 not-evaluable → exceptions → sign-out → API 401), `truebind-web/backend/tests/integration/test_services.py` (7: every compose service reachable and functional — SMTP→Mailpit delivery, OIDC discovery, stripe-mock, webhook round-trip, Redis PING, MinIO, SFTPGo).

Behaviour-neutral cleanups (needed for a green lint gate): removed 9 unused imports/one unused f-string, 2 unused locals (engine `validation.py` `paid_components_used`, a test's `dev`). `pipeline_service.mapping_mod` is a re-export (kept, `noqa`).

Harness decisions (recorded so they are not mistaken for weakening):
- **Legacy vs strict quality.** Existing code is held to ruff E4/E7/E9/F and a mypy error ceiling of 105 (may only fall). Every new module is added to `scripts/quality.json → strict_paths` and must pass the broad ruleset, `ruff format` and `mypy --strict` with zero errors.
- **Timing tests vs coverage.** Two engine tests assert wall-clock bounds. They gate in `engine-tests` (run without coverage). The separate coverage-collection run deselects them because line tracing slows the code under test — the scenario they measure is untraced. Nothing is skipped from the gate.
- **Coverage baseline** 89.69 % (total, engine + backend on PostgreSQL); changed lines vs `origin/main` must be ≥ 85 %.
- **Images**: Docker Hub rate-limits anonymous pulls here, so compose uses ECR Public / GHCR mirrors where they exist; MinIO uses `pgsty/minio` (upstream MinIO no longer publishes server images).
- **Dependencies**: vitest 5.0.2 (3.x had a critical advisory), `@types/node` 22 (vitest peer), `@playwright/test` 1.56.1 (matches the pre-installed Chromium 1194), setuptools ≥ 83 (PYSEC-2026-3447). QA tools pinned in `requirements-dev.txt`.

Evidence — `verify --full` (see verify-report.json of the commit run): all 14 steps OK; engine 86 passed; backend on PostgreSQL 131 passed / 1 skipped (124 + 7 integration); golden 8 passed; e2e 1 passed on PostgreSQL; security clean; coverage 89.69 % (baseline); OpenAPI snapshot 46 operations.

### P0 gate
- [x] verify --full green on the untouched product.
- [x] Self-review: no product behaviour changed (diff = harness, tests, docs, 11 lint-only deletions); grep for float money / unscoped queries / TODO / print / bare except / secrets in the P0 diff: none introduced (prints only in the CLI `verify.py`, allow-listed).
- [x] Docs: ARCHITECTURE.md, this file, BLOCKERS.md, HUMAN_TODO.md.

**P0 summary.** The product was already further along than the brief assumed: hash-chained audit, PostgreSQL RLS, a leased job worker and tri-state mapping exist. A one-command harness now proves it end to end against real services, including the golden 320-row regression through the browser. Nine brief/code discrepancies (D1–D9, ARCHITECTURE.md §10) are scheduled into P1–P3, the largest being float money (D1) and deletable originals (D5). Legacy code is held by ratchets; new code is strict. Docker Hub rate limits and the MinIO image change were worked around with mirrors.

---

## P1 — Platform foundation (in progress)

### P1.1 Settings (D8) — done
Acceptance:
- [x] Every setting typed and env-driven; defaults equal pre-P1 values — `test_settings.py::test_defaults_match_pre_p1_behaviour`.
- [x] Production: safe defaults (secure cookies, no sign-up, no embedded worker) — `test_production_defaults_are_safe`.
- [x] Production refuses missing/SQLite `DATABASE_URL`, missing/short `SECRET_KEY`, `COOKIE_SECURE=false`, wildcard CORS — `test_production_rejects_unsafe_configuration` (6 cases).
- [x] Malformed values fail loudly (pre-P1 silently fell back to defaults: deliberate behaviour change) — `test_malformed_values_fail_loudly`.
- [x] Secrets are `SecretStr`, absent from repr/dump — `test_secrets_are_not_shown_in_repr`.
- [x] `.env.example` documents every setting and holds no secret values — `test_env_example_documents_every_setting`.
- [x] Legacy `app.config` constants unchanged for existing callers — full backend suite green.

Implementation: `app/settings.py` (strict: ruff full ruleset + format + mypy --strict with the pydantic plugin via `scripts/mypy-strict.ini`); `app/config.py` is now a thin view. New settings for later P1 tasks are declared now so `.env.example` is complete: `SECRET_KEY`, `PUBLIC_APP_URL/API_URL`, `STORAGE_BACKEND`, `S3_*`, `REDIS_URL`, `JOB_MAX_ATTEMPTS`, `LOG_LEVEL/JSON`, `SENTRY_*`, `TOTP_ISSUER`, `LOGIN_LOCKOUT_*`.
Harness: tests may use literal fake secrets (S105/S106 allowed under `tests/`).
Human: production now requires `SECRET_KEY` (HUMAN_TODO).

Remaining tasks (acceptance criteria written in full when each starts):
- P1.2 Roles + memberships model: owner/admin/analyst/viewer/sender, permission matrix, REVIEWER→analyst migration (D4).
- P1.3 Tenant-isolation suite over every endpoint (another tenant's IDs → 404), RLS on every new table.
- P1.4 Auth: TOTP 2FA (per-org enforcement), login lockout (Redis-backed), OIDC SSO via Authlib against mock-oauth2-server.
- P1.5 Storage: S3-compatible adapter (boto3; MinIO in tests), SSE, SHA-256 on write, no delete path; report delete → soft delete (D5).
- P1.6 Money: `Numeric(18,2)` + currency, Decimal at the API boundary (D1); per-cell ambiguous-date flag (D9).
- P1.7 Jobs: Redis wake-ups + idempotency keys + retries on the existing DB queue (D6); 50k-row workbook < 120 s without blocking the API.
- P1.8 Observability: JSON logs with request IDs + PII scrubber, Sentry (env-gated, scrubbed), `/healthz` `/readyz`.
- P1.9 Audit: every new event type chained; tamper-detection test on PostgreSQL and SQLite.
