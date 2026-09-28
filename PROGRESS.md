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

Remaining tasks (acceptance criteria written in full when each starts):
- P1.4c frontend: MFA sign-in step + Settings (organisation, members, security, SSO).
- P1.5 Storage: S3-compatible adapter (boto3; MinIO in tests), SSE, SHA-256 on write, no delete path; report delete → soft delete (D5).
- P1.6 Money: `Numeric(18,2)` + currency, Decimal at the API boundary (D1); per-cell ambiguous-date flag (D9).
- P1.7 Jobs: Redis wake-ups + idempotency keys + retries on the existing DB queue (D6); 50k-row workbook < 120 s without blocking the API.
- P1.8 Observability: JSON logs with request IDs + PII scrubber, Sentry (env-gated, scrubbed), `/healthz` `/readyz`.
- P1.9 Audit: every new event type chained; tamper-detection test on PostgreSQL and SQLite.
