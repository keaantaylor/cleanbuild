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

### P1.2 Roles, permissions, organisation, members, invitations (D4) — done
Acceptance (tests in `tests/test_org_members.py`, 12):
- [x] Roles OWNER/ADMIN/ANALYST/VIEWER/SENDER with an explicit server-side matrix; unknown/legacy roles get nothing — `test_permission_matrix_is_explicit`.
- [x] REVIEWER → ANALYST data migration, reversible; tenants gain `org_type` + `require_2fa` — `test_reviewer_role_migrates_to_analyst` (upgrade + downgrade).
- [x] Viewers read but cannot write; senders cannot read provider data (reports, overview, audit, members, alerts) — `test_viewer_reads_but_cannot_write`, `test_sender_cannot_read_provider_data`.
- [x] Invite → accept (new user sets password; existing user proves theirs, keeps profile) — `test_owner_invites_analyst_who_can_work`, `test_existing_user_accepts_with_their_own_password`.
- [x] Tokens single-use (404 on reuse), expiring (410), revocable (404) — `test_invitation_tokens_are_single_use_expiring_and_revocable`.
- [x] Admins cannot grant/modify/remove owners (403); the last owner cannot be demoted/removed (409) — `test_admin_cannot_touch_owners_and_last_owner_is_protected`.
- [x] Removing a member revokes their sessions immediately (401) — `test_removed_member_is_signed_out_everywhere`.
- [x] Cross-tenant member/invitation IDs → 404 — `test_cross_tenant_member_ids_are_404`.
- [x] INVITATION_CREATED/ACCEPTED/REVOKED, ROLE_CHANGED, SETTINGS_CHANGED, MEMBER_REMOVED audited with before/after; chain intact — `test_membership_and_settings_changes_are_audited`.
- [x] Org settings need org:manage; invalid org type → 422 — `test_org_settings_need_org_manage`.

Implementation: `app/security/permissions.py`, `app/routes/org.py` (strict), migration `0006` (invitations with PostgreSQL RLS that exposes a row only inside its tenant or to the holder of its token hash), `require(Permission)` dependency; every legacy data route now requires `data:read` (senders locked out), report deletion requires `data:delete` (owner/admin; previously any writer). `/auth/me` adds `permissions`, `tenant.org_type`, `tenant.require_2fa` (additive). OpenAPI: +9 operations (46 → 55) under `/api/v1/org` and `/api/v1/auth/invitations/accept`, snapshot updated intentionally.
Harness: strict ruff config moved to `scripts/ruff-strict.toml` (FastAPI `Depends` whitelisted for B008); mypy strict config generated per run so legacy `app.*` modules reached through imports are not held to --strict (they have the ratchet). Legacy mypy ratchet tightened 105 → 102 (three `Tenant | None` accesses guarded).

### P1.3 Tenant-isolation suite + RLS on identity tables — done
Acceptance (tests in `tests/test_isolation_all_endpoints.py`, 5):
- [x] Every operation with a path id (37 today, derived from the live OpenAPI document), called by another organisation's owner with tenant A's ids, returns 404, leaks no marker, and changes nothing — `test_every_id_endpoint_is_404_for_another_tenant`.
- [x] Every tenant-data list/overview GET shows none of A's markers, ids or emails — `test_every_list_endpoint_hides_other_tenants`.
- [x] Self-enforcing: a new endpoint with a path id or request body fails the suite until an isolation case is added (asserts inside the walker).
- [x] Body-carried ids cannot target another tenant — `test_body_only_writes_cannot_target_another_tenant`.
- [x] PostgreSQL: every table with `tenant_id` has RLS enabled + FORCED and a policy — `test_every_tenant_table_has_forced_rls_and_a_policy`.
- [x] Identity rows (memberships, sessions) are visible only in-tenant, to their own user, or to the holder of the session token — `test_identity_rows_are_visible_only_to_their_tenant_user_or_token_holder`.

Implementation: migration `0007_identity_rls` (memberships: tenant OR `app.user_id`; auth_sessions: tenant OR `app.session_token_hash`; writes always in-tenant); `database.set_identity()` sets those GUCs per transaction; session lookup and sign-in set them before reading. Found while building it: other tests inject probe routes (`/__boom`) into the shared app; the walker ignores `/__*`.

### P1.4a TOTP two-factor authentication — done
Acceptance (tests in `tests/test_mfa.py`, 8):
- [x] Setup returns secret + otpauth URI; enable with a valid code returns 10 unique recovery codes; seed stored encrypted (HKDF-derived Fernet key per purpose), recovery codes only as hashes — `test_setup_enable_and_login_with_totp`.
- [x] With 2FA on, the password alone creates no session: login returns a 5-minute encrypted challenge; wrong code 401, right code signs in — same test.
- [x] Codes cannot be replayed (last-used step recorded) — `test_codes_cannot_be_replayed`.
- [x] Recovery codes work once and their use is audited — `test_recovery_code_works_once`.
- [x] Challenges are tamper-evident and expire — `test_challenge_tokens_expire_and_are_bound`.
- [x] Wrong codes count towards lockout; the password step does not reset the counter — `test_wrong_codes_lock_the_account`.
- [x] Org enforcement: password-only sessions of a 2FA-requiring org get 403 (`X-TrueBind-Reason: mfa_setup_required`) everywhere except me/logout/2FA setup; completing setup upgrades the session; disabling is refused while required — `test_org_enforcement_confines_members_until_set_up`.
- [x] Disable needs a valid code; enabling revokes the user's other sessions; MFA_SETUP_STARTED/ENABLED/DISABLED audited — `test_disable_needs_a_code_and_enable_revokes_other_sessions`, `test_setup_is_refused_when_already_enabled`.

Existing-test change (evidence): `test_org_members.py::test_membership_and_settings_changes_are_audited` turned on `require_2fa` with an owner who had no 2FA, then kept using that session. Under enforcement that owner is (correctly) confined to setup, so the test failed on the next call. Rather than weaken enforcement, `PATCH /org` now refuses (409) to require 2FA unless the acting admin's own session used it — an admin can no longer lock everyone out by accident. The test now asserts that 409, sets up the owner's 2FA, then continues with every original assertion unchanged. `test_mfa.py`'s enforcement test does the same.

P1.3 test adjusted (evidence): `test_identity_rows_are_visible_only_to_their_tenant_user_or_token_holder` checked the token-hash path on a DB session that still had a user id bound; 0008 intentionally lets a user see their own sessions, so that check now runs on a fresh session with no user bound, and a new assertion covers the user path. Every original assertion is kept.

Implementation: `app/security/crypto.py`, `app/security/mfa.py`, `app/routes/mfa.py` (strict); migration `0008_mfa` (`user_mfa`, `auth_sessions.auth_method`, users may see their own sessions for revocation); login returns `MeOut | MfaChallengeOut`; `/auth/me` adds `mfa {enabled, required, setup_required}`. OpenAPI: +5 operations under `/api/v1/auth/2fa`.

### P1.4b OIDC single sign-on — done
Acceptance (unit: `tests/test_sso.py`, 9; end to end against mock-oauth2-server: `tests/integration/test_sso_mock_idp.py`, 7):
- [x] One OIDC connection per organisation (issuer, client id, write-only encrypted client secret, domains, JIT, default role ≠ OWNER); secret never returned or audited — `test_owner_configures_sso_and_secret_is_write_only`.
- [x] A domain can be claimed by one organisation only (409); config needs org:manage — `test_domains_are_claimed_once_and_config_needs_org_manage`.
- [x] Start resolves the IdP from the e-mail domain and redirects with state, nonce and S256 PKCE; unknown/disabled → 404 — `test_start_redirects_with_state_nonce_and_pkce`.
- [x] ID tokens need an asymmetric signature from the issuer's JWKS, the right iss/aud/nonce, a subject and an unexpired lifetime; HS256, unsigned and foreign-key tokens are rejected — `test_valid_id_token_is_accepted`, `test_id_token_claims_are_enforced` (4), `test_id_token_signature_and_algorithm_are_enforced`.
- [x] Full flow against a real IdP: JIT member with default role, audited LOGIN_SUCCEEDED(method=sso) + SSO_USER_PROVISIONED — `test_jit_sign_in_creates_member_with_default_role`.
- [x] Refused: asserted e-mail outside the connection's domains, `email_verified: false`, unknown user without JIT — no session — `test_refused_sign_ins_create_no_session` (3).
- [x] An account that exists in another organisation is never pulled in by JIT — `test_existing_account_elsewhere_is_not_captured_by_jit`.
- [x] Missing/forged state cookie → refused — `test_callback_without_the_start_cookie_is_refused`.
- [x] SSO sessions satisfy an organisation's 2FA requirement (MFA is the IdP's job) — `test_sso_session_satisfies_org_2fa_requirement`.

Implementation: `app/security/oidc.py` (Authlib OAuth2Client for the authorize/token steps, joserfc for ID-token validation — `authlib.jose` is deprecated), `app/routes/sso.py`, migration `0009_sso` (RLS: in-tenant, or the single domain / connection being looked up before sign-in). Isolation walker: SSO start/callback are public flows. OpenAPI: +5 operations.

### P1.4c Frontend: sign-in second step, SSO, invitations, Settings — done
Acceptance:
- [x] Sign-in handles the 2FA challenge (code or recovery code), shows plain-English SSO errors, and offers "Sign in with single sign-on" — e2e `members-and-2fa.spec.ts` (wrong code rejected, right code signs in); unit `auth.test.ts` (every SSO error code has a message, never the raw code).
- [x] Invitation acceptance page `/invite?token=` — e2e: the invitee joins as ANALYST.
- [x] Settings (Organisation · Members · Security · Single sign-on), permission-aware from `/auth/me`: invite with role help text, change roles, remove members, revoke invitations, 2FA setup with QR + manual key + one-time recovery codes, SSO configuration with the callback URL to register — e2e covers invite → accept → 2FA on → sign out → sign in with a code.
- [x] A 403 `mfa_setup_required` anywhere sends the user to Settings → Security.
- [x] Built from the existing design system (PageHeader, Panel, Pill, Tabs, Modal, Button, tokens only); selects use explicit `<label for>` so their accessible names are exact (found by the e2e test).

Known limitation: SENDER users land in the standard dashboard, where data pages return 403. The sender portal (P8) gives them their own navigation.

### P1.5 Immutable originals, S3 storage, soft delete (D5) — done
Acceptance (unit `tests/test_storage.py`, 7; MinIO `tests/integration/test_s3_storage.py`, 3):
- [x] Originals are write-once and content-addressed (`tenants/<t>/originals/<sha256>.<kind>`); identical bytes are idempotent; the same file uploaded twice shares one object — `test_originals_are_content_addressed_and_idempotent`, `test_same_file_uploaded_twice_shares_one_immutable_original`.
- [x] The storage interface has no delete/overwrite/remove method on either backend — `test_storage_has_no_delete_or_overwrite_path`.
- [x] Every read verifies SHA-256; a tampered original is refused (job fails `source_tampered`, never parsed) — `test_tampered_original_is_refused`, `test_read_verifies_the_hash`.
- [x] Keys are validated (no traversal) — `test_keys_are_validated`.
- [x] S3 (MinIO): SSE AES256 on every object, SHA-256 in metadata, conditional `If-None-Match: *` so a different body can never replace a key, full upload → ingest → process on S3 — `test_objects_are_encrypted_hashed_and_write_once`, `test_full_workflow_on_s3`.
- [x] Deleting a report or its retention expiring is a soft delete: 404, gone from lists/overview/alerts/follow-ups/deliveries, invisible to a fresh session (the worker), audited — original byte-identical afterwards, also on S3 — `test_delete_is_soft_and_keeps_the_original`, `test_retention_expiry_is_soft_and_keeps_the_original`, `test_full_workflow_on_s3`.

Existing tests changed (evidence — both encoded behaviour that non-negotiable #7 forbids or renamed):
- `test_workflow.py::test_delete_removes_file_and_data_but_keeps_audit` asserted the original file was removed and derived rows deleted. Replaced by `test_delete_hides_report_keeps_original_and_audit`: original exists and is byte-identical, report hidden from queries and API, audit entry present.
- `test_upload_security.py::test_path_traversal_filename_cannot_escape_storage` asserted the stored name was `source.xlsx`. The security property (the uploaded name never reaches the path; the file stays inside storage) is unchanged and still asserted; the name is now the content's SHA-256, which the test checks exactly.

Implementation: `app/services/storage.py` (strict; `LocalObjectStore` creates 0400 files via `link()` so a key can never be replaced; `S3ObjectStore` via boto3), migration `0010_report_soft_delete`, one ORM rule in `models/reports.py` hides soft-deleted reports and the alerts/obligations/deliveries that point at them (`include_deleted` opt-in). Upload stores the original before the DB transaction, so a failed transaction leaves an unused immutable object instead of deleting one. `docs/RETENTION.md` documents that physical purge is an operator lifecycle rule. docker-compose.test.yml: MinIO gets a test-only KMS key for SSE. Legacy mypy ratchet 100 → 98.

### P1.6 Money as exact decimals (D1) — done
Acceptance (`tests/test_money.py`, 14):
- [x] One normalisation at the boundary: 2 dp, ROUND_HALF_UP; float artefacts vanish (0.1+0.2 → 0.30); NaN/∞/non-numbers → NULL — `test_to_money_normalises_once` (10 cases).
- [x] Every money column (10 on claim rows, `validation_results.delta`, `leakage_flags.amount_exposure`) uses the `Money` type; no money-like Float column remains anywhere in the schema — `test_every_money_column_uses_the_money_type`.
- [x] Persisted amounts are exact Decimals, currency kept per row; the API carries the exact 2-dp value — `test_persisted_amounts_are_exact_decimals`.
- [x] SQL aggregation stays exact (10 × 0.10 at stake = 1.00, not 0.9999…) — `test_money_aggregation_is_exact`.
- [x] PostgreSQL columns are `numeric(18,2)` — `test_postgres_columns_are_numeric_18_2`.
- [x] Golden regression unchanged (verify `golden` step).

Existing test changed (evidence): `test_audit_and_exports.py::test_exports_neutralise_formula_injection_and_keep_lineage` expected the CSV text `-50.0`; money now exports as the exact decimal `-50.00`. The property under test (a negative amount is not formula-escaped) is unchanged and now asserted both ways.

Scope note (D1): the engine still computes in float with its 0.01 tolerance; values become exact money once, when persisted. New modules (P3+) compute in Decimal from the start. SQLite (development only) stores the quantised value as REAL and converts back through text, so application code only sees 2-dp Decimals. Ambiguous-date flagging (D9) moves to P3, where the binder rules consume dates. Legacy mypy ratchet 98 → 97.

### P1.7 Jobs: 50k rows, bounded checks, retries, idempotency keys, Redis wake-ups (D6) — done
Acceptance:
- [x] A generated 50,000-row workbook goes upload → review → COMPLETE through the real API and worker on PostgreSQL in < 120 s, while `/health/ready` answers in < 1 s throughout — `scripts/perf_50k.py` (verify `perf` step, realistic shape, with Redis wake-ups).
- [x] A hostile 50,000-row workbook (every insured "Insured N", every loss in one month: ~10^8 probable-duplicate candidate pairs) also completes in budget, with the probable-duplicate check reported **not assessed**, never "0" — verify `perf` step, adversarial shape; engine `tests/test_dedupe_budget.py` (4).
- [x] The candidate-pair count equals what the pairwise loop visits; under the budget results are unchanged; over it no probable pairs are emitted, exact duplicates still are, and the reason carries both numbers — `test_candidate_pair_count_matches_the_comparison_loop`, `test_within_budget_is_assessed_and_unchanged`, `test_over_budget_is_not_assessed_not_silently_clean`.
- [x] A not-assessed check reaches coverage (statement + provisional score), the stored summary (`not_assessed_checks`, `probable_duplicates: null`, `coverage_statement`), the overview count and the report page ("Not assessed", reason in the caveat) — `test_not_assessed_check_reaches_coverage_and_reliability`, backend `tests/test_check_coverage.py` (2), vitest `tests/unit/coverage.test.ts` (2).
- [x] Retry limit is the `JOB_MAX_ATTEMPTS` setting, stamped on each job — `test_retry_limit_comes_from_settings`.
- [x] A PROCESS job that dies after writing its results is retried and ends with exactly a clean run's results (nothing partial after the failed attempt, nothing duplicated after the retry) — `test_process_failing_mid_save_is_retried_without_partial_or_duplicate_results`.
- [x] `Idempotency-Key` on `POST /reports/upload` and `/reports/{id}/process`: replay with `Idempotent-Replayed: true` and nothing created; different request with the same key → 422; per organisation; malformed → 400; a failed request does not burn its key; an expired key is new — 8 tests in `tests/test_jobs_reliability.py`; table `idempotency_keys` has forced RLS (covered by the existing `test_every_tenant_table_has_forced_rls_and_a_policy`).
- [x] Redis wake-ups: sent on COMMIT only (never for a rolled-back enqueue), a waiting worker wakes at once, waiting times out quietly, backlog bounded; without `REDIS_URL` a no-op and the worker polls — `tests/integration/test_job_signal_redis.py` (4, compose Redis), `test_wake_signal_without_redis_is_a_no_op`.

Root cause of the first perf failure (evidence): the first 50k run never finished (killed after 4 m 20 s). A stack dump of the job child (py-spy) showed it in `bordereaux/dedupe.py:_compare_block`. My first fixture named every insured "Insured N" (one 2-letter block) with every loss date in one month, so the fuzzy pairwise check had ~1.75 × 10^8 pairs to visit. The engine had no bound for that input, so a hostile or odd file could hold a worker for up to the 30-minute job timeout. Fix: count candidate pairs first (vectorised), refuse above `MAX_PROBABLE_CANDIDATE_PAIRS` = 2,000,000 with an explicit not-assessed coverage entry, cache each name pair's fuzzy score and each row's normalised policy reference (results identical; 90 engine tests unchanged). The realistic fixture then does 181,896 candidate pairs in 1.8 s.

Measured (PostgreSQL, embedded worker, this container): realistic 38.8 s total (ingest 12.0 s; PROCESS parse 11.0 s, pipeline 2.9 s, persist 11.5 s; peak RSS 412 MB); probe max 0.020 s, p95 0.011 s. Adversarial 32.5 s, probable-duplicate check not assessed; probe max 0.021 s.

Evidence — `verify --full` PASS (338 s): ruff/mypy clean (legacy 93/93); engine 90; vitest 16; migrations round-trip to 0012; backend on PostgreSQL 227 passed (incl. integration); golden 8; next build; e2e 2; perf realistic 37.3 s (probe max 0.022 s), adversarial 33.5 s (check not assessed); security clean; coverage 91.09% total, 94.78% of changed lines; OpenAPI 65 operations.

API contract (intentional, additive): optional `Idempotency-Key` header parameter on `POST /api/v1/reports/upload` and `POST /api/v1/reports/{report_id}/process`; nothing removed. Snapshot accepted with `--update-openapi`.

First `verify --full` run failed (evidence): 6 idempotency tests failed on PostgreSQL only; the first keyed request got 409 "still in progress". Root cause: `rowcount` of the ORM-enabled `INSERT … ON CONFLICT DO NOTHING` is not reliable on psycopg, so a fresh insert looked like a conflict. Fix: `RETURNING id` (a row only when this request inserted the key). Reproduced from the verify log, then 20/20 of the affected suites passed on PostgreSQL before re-running verify.

Setting default changed (evidence): `JOB_MAX_ATTEMPTS` was declared with default 3 in P1.1, but nothing read it. Jobs always ran with the model default of 2, and `test_job_system.py::test_expired_lease_is_requeued_then_failed_never_stuck` asserts 2. The setting is now wired and its default is 2, the tested behaviour; `.env.example` said 3 and now says 2. The reaper's "interrupted twice" message now states the real count. Legacy mypy ratchet 97 → 93 (an `or {}` guard in `/overview` removed four existing errors).

### P1.8 Observability — done
Acceptance (`tests/test_observability.py`, 17):
- [x] A request ID on every request (a valid incoming `X-Request-ID` is kept, anything else replaced), echoed in the response and on every log line of that request — `test_request_id_is_echoed_and_on_every_log_line`.
- [x] JSON log lines (ts, level, logger, message, request_id, exc_info) when `LOG_JSON` is on (default in production) — same test.
- [x] Personal data never reaches a log line: e-mails, bearer tokens, key=value secrets, card/account/phone digit runs, IBANs masked; ordinary text untouched — `test_scrub_masks_personal_data` (7), `test_scrub_keeps_ordinary_text`, `test_log_lines_never_carry_an_email`.
- [x] Unhandled error → 500 whose `correlation_id` is the request ID, no internal detail; traceback (scrubbed) in the log only — `test_unhandled_error_is_correlated_and_opaque`.
- [x] Sentry only with `SENTRY_DSN`; `send_default_pii` off, cookies/headers/body dropped, user reduced to id, every string scrubbed, proven through a real SDK transport — `test_sentry_is_off_without_a_dsn`, `test_sentry_events_are_scrubbed_before_sending`, `test_sentry_sends_scrubbed_events_through_its_transport`.
- [x] `/healthz` needs no dependencies; `/readyz` checks database + schema at Alembic head, 503 otherwise without leaking detail — `test_healthz_needs_no_dependencies`, `test_readyz_checks_database_and_migrations`, `test_readyz_is_503_when_the_database_is_down`. `/health` and `/health/ready` keep their original responses (existing probes and `test_readiness_endpoint` unchanged).

Root cause found on the way: `migrations/env.py` called `fileConfig()` (default `disable_existing_loggers=True`, root WARNING) whenever migrations ran in-process, silencing the application's loggers for the rest of the process. It now configures logging only when run from the CLI, and never disables existing loggers.

Process note (the user asked for everything today): from here on each task runs `verify --fast` and is committed on green; `verify --full` runs at every phase gate and must be green before the next phase starts. PROGRESS.md records both.

### P1.9 Audit coverage and tamper detection — done
Acceptance (`tests/test_audit_coverage.py`, 9 on PostgreSQL, 8 + 1 PG-only skip on SQLite):
- [x] Every state-changing operation in the OpenAPI document (29: POST/PATCH/DELETE) is called successfully in one scenario and each call adds an audit entry; an operation added later without an audited step fails the test; the chain verifies intact afterwards — `test_every_state_change_is_audited_and_the_chain_holds`.
- [x] Gap found and fixed: requesting an AI exception summary wrote no audit entry (only its completion did). It now writes `AI_SUMMARY_REQUESTED`.
- [x] PostgreSQL refuses UPDATE/DELETE on `audit_log` (append-only trigger) — `test_database_refuses_to_edit_or_delete_audit_rows`.
- [x] With the trigger lifted by the table owner, editing actor, action, payload, timestamp or the stored hash breaks the chain at that entry; deleting an entry breaks it at the next; renumbering is caught — `test_editing_any_field_breaks_the_chain_at_that_entry` (5), `test_deleting_an_entry_breaks_the_chain`, `test_verify_detects_tampering_directly`.

### P1 phase gate
- Self-review against the non-negotiables: tri-state mapping untouched; NOT_ASSESSED used for the new bounded check (P1.7); golden unchanged; money Decimal (P1.6); isolation app-layer + RLS on every tenant table incl. `idempotency_keys` (existing forced-RLS test); audit chain + coverage + tamper tests (P1.9); originals immutable (P1.5); secrets only from env, `.env.example` current; no PII in logs/Sentry (P1.8); nothing deployed.
- Greps: no TODO/FIXME/XXX in app or engine code; no bare `except:`; the only `print(` is the engine's interactive CLI confirmation (`bordereaux/mapping.py:confirm_mapping_cli`, intended); remaining `Float` columns are scores/percentages, not money; no secret-shaped strings except a clearly fake test fixture in the scrubber test.
- Unscoped queries: enforced by the OpenAPI isolation walker (every endpoint, cross-tenant → 404) and forced RLS on every table with `tenant_id`.
- API contract (intentional, additive): `GET /healthz`, `GET /readyz`; snapshot accepted with `--update-openapi`.
- gitleaks flagged two fake values in the P1.8 scrubber test (already pushed in fce06c5). Reviewed as false positives: listed by exact fingerprint in `.gitleaksignore`, marked `gitleaks:allow` inline; history not rewritten.
- Gate evidence — `verify --full` PASS (345 s): ruff/mypy clean (legacy 93/93); engine 90; vitest 16; migrations round-trip; backend on PostgreSQL 253 passed; golden 8; next build; e2e 2; perf realistic 35.7 s / adversarial 29.4 s (probe max 0.035 s); security clean; coverage 91.42% (baseline ratcheted 89.69 → 91.42), 94.46% of changed lines; OpenAPI 67 operations.
- Summary: (1) P1 delivered settings, roles/invitations, isolation + RLS, TOTP/SSO, immutable S3 originals, exact money, job reliability, observability and a verified audit trail. (2) 50k rows in ~37 s with the API unaffected. (3) One engine gap closed (unbounded fuzzy duplicate check → bounded, NOT ASSESSED when over budget). (4) One audit gap closed (AI summary requests). (5) Open for humans: SECRET_KEY, Sentry DSN, S3 bucket, Redis, separate migration role (HUMAN_TODO.md).

## P2 — Channels (in progress)

### P2.1 E-mail intake (Postmark, SES) — done
Acceptance (`tests/test_inbound_email.py`, 11):
- [x] Private inbound address per organisation, created/rotated with org:manage and audited; a rotated address stops working; viewers can see but not rotate — `test_unknown_or_rotated_address_is_dropped`, `test_inbound_settings_need_the_right_role`.
- [x] Postmark attachments become reports through the same file gate as uploads (`intake_service`, now also used by the upload route), channel "email", sender recorded, INGEST queued, audited with channel and sender — `test_postmark_attachment_becomes_a_report`.
- [x] Provider retries create nothing new (one idempotency key per message + attachment) — `test_provider_retries_create_nothing_new`.
- [x] Bad/missing Basic credentials 401, unconfigured 503 — `test_credentials_and_configuration`.
- [x] Unknown address acknowledged and dropped without revealing anything — `test_unknown_or_rotated_address_is_dropped`.
- [x] Rejected attachments audited with channel, reported back — `test_rejected_attachment_is_audited_and_reported`.
- [x] Mail lands only in the addressed organisation — `test_mail_lands_only_in_the_addressed_organisation`.
- [x] SES via SNS: signature verified against a trusted AWS certificate URL, allowed topic, SignatureVersion 1 (SHA1) and 2 (SHA256); tampering, wrong key, foreign certificate URL, other topic and unknown versions refused — `test_ses_signed_notification_is_ingested` (2), `test_ses_forgeries_are_refused`, `test_sns_certificate_url_must_be_aws`.
- [x] All three new operations covered by the audit coverage walker (P1.9 guard caught them).

### P2.2 SMTP outbound — done
- [x] A delivery request sends the export through a real SMTP server; message, recipient, subject and CSV attachment arrive; delivery DELIVERED and audited — `tests/integration/test_smtp_mailpit.py` (compose Mailpit).

### P2.3 Webhooks (signed, retried, replayable) — done
Acceptance (`tests/test_webhooks.py`, 14; `tests/integration/test_webhook_receiver.py`):
- [x] Admin registers an https endpoint for chosen events; `whsec_` secret shown once, stored encrypted; create/delete audited; unknown events refused — `test_register_endpoint_secret_shown_once_and_audited`, `test_unknown_events_are_refused`.
- [x] SSRF guard at creation and before every send: http, URL credentials, private/loopback/link-local targets, other schemes refused; redirects never followed — `test_unsafe_targets_are_refused` (5), `test_failures_back_off_then_give_up`.
- [x] report.waiting_for_review / report.completed / report.failed queued for subscribers only, never sent in the request — `test_report_events_are_queued_for_subscribers_only`, `test_failed_report_emits_report_failed`.
- [x] Standard Webhooks signing (webhook-id, webhook-timestamp, `v1,` HMAC-SHA256); receivers verify; tampered body, stale timestamp, wrong secret fail — `test_deliveries_are_signed_and_verifiable`; proven over real HTTP to the compose receiver.
- [x] Non-2xx retried with growing backoff, EXHAUSTED after WEBHOOK_MAX_ATTEMPTS with an alert; no further automatic sends — `test_failures_back_off_then_give_up`.
- [x] Replay keeps the message id and is audited; test ping — `test_replay_resends_with_the_same_message_id`, `test_test_ping_is_delivered`.
- [x] Isolation: other organisations get 404 (walker ids added) — `test_webhooks_are_isolated_between_organisations`, `test_every_id_endpoint_is_404_for_another_tenant`; all six operations in the audit coverage walker.

### P2.4 SFTP delivery — done
Acceptance (`tests/test_sftp.py`, 4; `tests/integration/test_sftp_sftpgo.py`, 3 against compose SFTPGo):
- [x] One destination per organisation; pinned SHA256 host key required; exactly one of password / private key; no ".." in the folder; host name restricted; secrets write-only and encrypted, absent from responses and audit — `test_destination_saved_without_exposing_secrets`, `test_destination_validation`.
- [x] Viewers cannot change it; other organisations see null — `test_viewers_cannot_change_it_and_other_orgs_cannot_see_it`.
- [x] Honest outcomes: NOT_CONFIGURED without a destination, FAILED ("Could not reach") when unreachable — `test_sftp_delivery_outcomes_are_recorded_honestly`.
- [x] Real server: connection test passes with the right key; delivery writes the export (temp name, then renamed into place) and is DELIVERED — `test_delivery_to_a_real_server`.
- [x] Wrong pinned key: nothing sent, FAILED "does not match" — `test_wrong_pinned_key_sends_nothing`.
- [x] Auto-delivery on report completion (claims + exceptions CSV) — `test_auto_delivery_on_completion`.
- [x] PUT/DELETE/test covered by the audit walker; `GET /org/sftp` returns null (200) when unset, so the isolation walker's list check applies.

Remaining tasks (acceptance criteria written in full when each starts):
