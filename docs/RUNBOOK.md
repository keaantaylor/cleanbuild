# TrueBind — operations runbook

For whoever runs TrueBind in production. Nothing here has been executed against production by the build
agent: the platform was built and tested on the `feat/platform-v1` branch only. The accounts and decisions
still needed are in `HUMAN_TODO.md`.

## 1. What runs where

| Part | Where | Notes |
|---|---|---|
| Web app (Next.js) | Vercel, project `cleanbuild`, root `truebind-web/frontend` | Proxies `/api/v1/*` to the API (`TRUEBIND_API_ORIGIN`), so browser cookies stay first-party. |
| API (FastAPI) | Render web service `truebind-api` (Docker, Frankfurt) | `start.sh`: `alembic upgrade head`, then uvicorn with proxy headers. Health: `/healthz` (process), `/readyz` (database reachable and on the Alembic head). |
| Job worker | Render background worker `truebind-worker` (same image, `python -m app.worker`) | Each job runs in a memory- and time-limited child process. With `TRUEBIND_EMBEDDED_WORKER=1` the API runs the worker itself (small deployments only). |
| PostgreSQL 16 | Render Postgres (Frankfurt), point-in-time recovery on paid plans | Row-level security on every tenant table (set per transaction from the session). |
| Redis | Render Key Value / Upstash EU | Job wake-ups only. If it is down, jobs still run, by polling. |
| Object storage | S3 (eu-west-1/2) or R2 (EU) | Write-once originals, SHA-256 checked on every read. |
| Outbound | SMTP, webhooks, SFTP, Stripe, ECB feed, Azure OpenAI / Bedrock (EU/UK) | Each is configured only by environment and Settings; every one reports "not configured" rather than pretending. |

## 2. Deploying

1. Merge to `main` only after `python scripts/verify.py --full` is green on the branch. The run writes `verify-report.json`.
2. Render builds the image. The pre-deploy/start step runs `alembic upgrade head`. Migrations are additive (new tables and nullable columns), so the previous release keeps working against the new schema while traffic moves over.
3. Watch `/readyz` return 200, then check Sentry for new issues (EU project) and the access log (JSON, one line per request with `request_id`).
4. The Vercel deploy of the frontend is independent. Old and new frontends both work against the new API because every API change so far has been additive (see the OpenAPI snapshot `scripts/openapi-snapshot.json`).

### Rolling back
- Application: in Render, redeploy the previous successful deploy; in Vercel, "Promote" the previous deployment.
- Database: do not run `alembic downgrade` in production unless the release notes say it is safe. Downgrades drop the new tables and lose their data. Prefer rolling the application back and leaving the additive schema in place.

## 3. Configuration and secrets

- Every setting and its default is listed in `truebind-web/backend/.env.example`. Production refuses to start without PostgreSQL, a `SECRET_KEY` of at least 32 characters and secure cookies.
- Secrets live only in the Render and Vercel environment settings, never in the repository. The history is scanned with gitleaks on every `verify --full`.
- `SECRET_KEY` derives separate encryption keys for each stored secret: webhook signing secrets, the SFTP password and key, TOTP seeds and SSO client secrets. **Changing `SECRET_KEY` makes those stored values unreadable** and signs everyone out. There is no dual-key rotation yet. If the key must change (for example, it leaked), plan it: change the key, then have each organisation re-enter its SFTP credentials and SSO secret, create new webhook endpoints and re-enrol 2FA. This is a known limitation.
- Stripe: use test-mode keys until go-live. The webhook secret belongs to the one endpoint `<PUBLIC_API_URL>/api/v1/billing/webhook`.

## 4. Backups and restore

- PostgreSQL: enable daily backups and point-in-time recovery on the Render plan. Test a restore to a scratch database once a quarter, and after any schema change, with:
  1. restore to a new Render database;
  2. `DATABASE_URL=<scratch> alembic current` (it must print the head revision);
  3. start an API against it with `TRUEBIND_EMBEDDED_WORKER=0` and call `/readyz`, then `GET /api/v1/audit/verify` as an owner. The audit hash chain must verify intact.
- Object storage: bucket versioning on, and Object Lock in compliance mode if the retention policy allows it. The database stores each original's SHA-256, so a restored object that does not match is refused, never silently used.
- Legacy local data: `truebind-web/backend/data/truebind.db` is a pre-platform SQLite file. Keep it as it is; do not delete or overwrite it.

## 5. Routine operations

| When | What |
|---|---|
| Daily (automatic with `FX_AUTO_REFRESH=true`) | ECB reference rates, refreshed every 6 h by the worker. Settings → Channels shows the latest fixing. |
| Weekly, and on every designation notice | Load the current sanctions lists (Settings → Sanctions lists), then run the sanctions check again on open reports. |
| Monthly | Review Sentry, the failed-job count (Operations page), webhook deliveries marked EXHAUSTED, and the retention job's log lines. |
| Each new binder year | Add the binder (Settings → Binders) and assign new reports to it. |

## 6. Incidents

1. **Triage.** Is `/readyz` failing? Is the database reachable? Look up the `request_id` from the user's error message (every 500 shows a correlation id) in the logs and in Sentry.
2. **Jobs stuck.** Check the worker service is running. Jobs left RUNNING by a dead worker are reclaimed automatically after the lease expires and retried up to `JOB_MAX_ATTEMPTS`.
3. **Suspected data exposure.** Tenant isolation is enforced in the application layer and again by PostgreSQL RLS. Preserve logs, rotate credentials (see §3 for `SECRET_KEY` consequences), and export the audit trail (`GET /api/v1/audit`, and the audit pack per report). The chain verification (`GET /api/v1/audit/verify`) shows whether audit history was altered.
4. **Stripe webhook failures.** Stripe retries for days. Events are applied once per event id, so replaying from the Stripe dashboard is safe.
5. Record the incident, its timeline and follow-ups. Notify affected organisations and, where personal data is involved, assess the breach against UK GDPR within 72 hours.

## 7. Performance envelope (measured by `verify --full`)

- 50,000-row workbook, end to end on PostgreSQL, API and worker, including all check modules: 35–53 s depending on the machine. Health probes stay under 0.2 s while it runs. The budget is 120 s.
- Adversarial 50k workbook: finishes by declaring the probable-duplicate check NOT_ASSESSED instead of running unbounded.
- Sanctions screening: 20,000 names against 20,000 list entries in about 1 s.
