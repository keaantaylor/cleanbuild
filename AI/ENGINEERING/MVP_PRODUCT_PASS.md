# MVP hardening, performance and productisation pass (2026-09-24)

Branch `claude/truebind-mvp-hardening`. Everything below was measured on the
running system (API + worker + production frontend build, Chromium via
Playwright), not inferred from code. The user's real file
`Truebind_StressTest_450rows (1).xlsx` was not available in this environment;
the 450-row, 3-sheet replica in `bordereaux/tests/regression_fixtures/` was
used instead.

## Root causes

| Symptom | Root cause | Fix |
|---|---|---|
| Upload sat "queued" for 7+ minutes | The API only enqueues jobs. `TRUEBIND_EMBEDDED_WORKER` defaulted to off, so with `uvicorn app.main:app` alone nothing consumed the queue and nothing said so. On Windows a worker would also have crashed (`import resource`, `signal.SIGKILL`). | Embedded worker on by default outside production; loud startup warning when off; worker liveness registry + `/system/status`; UI shows "Processing service unavailable" after ~4 s; Windows-safe worker; `dev.ps1` / `dev.sh`. |
| API and worker could use different databases | Each process resolved `DATABASE_URL` from its own shell; the default was `data/truebind.db` (the legacy database). | `backend/.env` read by every process (API, worker, job children, Alembic); relative SQLite paths resolved against `backend/`; default `data/truebind-mvp.db`; legacy DB never opened implicitly. |
| `Can't resolve '@vercel/turbopack-next/internal/font/google/font'` | `next/font/google` fetches fonts at compile time; when that fails Turbopack cannot resolve its internal font module. | Self-hosted Inter + Space Grotesk via `next/font/local` (`app/fonts/`, OFL). No network dependency. |
| Blank white screens | No `loading.tsx` / error boundaries; the auth gate rendered bare text; a Suspense fallback of `null`; any API error on `/auth/me` redirected to login; `localhost` vs `127.0.0.1` made the session cookie cross-site. | Route loading skeletons, error / global-error / not-found boundaries, shaped app skeleton while the session is checked, explained + retryable "API unreachable" state, API base follows the page hostname. |

## Performance (450-row, 3-sheet workbook; live API + embedded worker)

| Stage | Time |
|---|---|
| Upload acknowledged | 0.01–0.03 s |
| Queue → RUNNING (worker poll 0.5 s) | 0.15–0.36 s |
| Parse (3 sheets, 450 rows) | 0.29 s |
| Mapping proposal (AI calls: 0 — every header matched by alias) | 0.00 s |
| Upload → mapping review **visible in the browser** | **0.85 s** |
| Process job: parse 0.33 s · mapping 0.11 · validation 0.04 · dedupe 0.06 · report 0.01 · persist 0.05 | 0.61–0.68 s |
| "Produce health report" click → report **rendered in the browser** | **2.15 s** |
| File chosen → report rendered, including user clicks | **3.42 s** |

Worker children are now pre-warmed (the next job's isolated process imports
pandas/openpyxl/engine while idle): measured cold child start 0.97 s per job,
i.e. ~2 s per report removed from the critical path (more on Windows, where
process spawn is slower). Isolation is unchanged: one fresh process per job,
same memory and time limits.

Not optimised in this pass: openpyxl parsing is ~0.11 ms/row (120k rows took
13.7 s to read). It is the dominant cost for very large files.

## Failure modes verified on the running system

| Scenario | Result |
|---|---|
| No worker running | Top bar "Processing service unavailable"; upload shows the same after 4.3 s; work queue item CRITICAL; nothing waits silently. |
| Worker started later | Standalone `python -m app.worker` claimed the queued job 60 ms after start; the open page advanced to mapping review by itself (2.3 s). |
| API + worker SIGKILLed mid-ingest, API restarted | Job recovered 20 ms after restart (dead same-host PID detected), requeued, completed on attempt 2; every step in the audit trail. Worker-lost retries now run immediately. |
| Dead worker on another host | Recovered once its check-ins go stale (2 × 20 s), before lease expiry. |
| Timeout / memory limit / child crash | Job FAILED with a customer-safe message (tests). |
| AI unavailable / failing / slow | Deterministic mapping; AI stage bounded by `AI_TIME_BUDGET_S` (default 30 s) and a per-report call cap. |
| Interrupted AI narrative | Marked FAILED on API start (unchanged, still tested). |
| Parser failure, empty workbook, over-limit workbook | Useful FAILED states (tests). |
| E-mail export without SMTP | Recorded `NOT_CONFIGURED`, alert raised; never reported as sent. |

## Product surfaces added

Overview (command centre), Inbox, Intake (live processing view + mapping
review), Work queue, Reports workspace (overview / sheets / lineage / outputs),
Exceptions action centre (what happened · why it matters · evidence · next
step · decision · follow-up), Duplicate intelligence (exact / probable / needs
period / development), Exports & deliveries, Automations (channels + pipeline;
planned connectors marked planned), Alerts, Audit trail (readable, hash-chain
verified).

Backend: `/overview`, `/work-queue`, `/system/status`, `/channels`,
`/deliveries`, `/reports/{id}/deliveries`, `/reports/{id}/jobs`,
`PATCH /reports/{id}/exceptions/{vr}`; lifecycle alerts; evidence-backed
recommendations in every report summary; migrations 0004 (worker registry),
0005 (report provenance, deliveries with RLS).

## Remaining work

- Real inbound connectors (e-mail inbox, SFTP, cloud folder, scheduled
  import) — the UI lists them as planned; none are implemented.
- Webhook / SFTP outbound; e-mail needs SMTP settings to send.
- Premium, claims-only schema: premium bordereaux metrics are not produced
  (the canonical schema is claims).
- Large-file parsing speed (openpyxl read-only); a streaming/columnar reader
  would be needed for 100k+ row files to meet interactive targets.
- Windows: no per-job memory limit (no RLIMIT_AS); run workers on Linux in
  production.
- Rate limiting is per process (in-memory).
- Verification against the user's real `Truebind_StressTest_450rows (1).xlsx`
  and the other named workbooks.
