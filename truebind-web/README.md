# Truebind Web (Next.js + FastAPI redesign)

A from-scratch redesign of the Truebind bordereaux tool: a Next.js/TypeScript
frontend and a FastAPI backend, replacing the Streamlit build in
`../bordereaux/` (kept as-is and still fully working — this is a separate,
parallel effort, not a migration in place). This covers **Phase 0** of the
redesign brief: the full upload → mapping → health report → exceptions →
duplicates → audit → to-do flow, backed by a real database.

## Why a separate backend instead of a rewrite

The core pipeline (multi-sheet ingestion, header-row detection, column
mapping, validation, deduplication, health-report scoring) is **not
reimplemented here**. `backend/app/services/pipeline_service.py` imports
`bordereaux` directly — the same already-tested package the Streamlit app
uses — because that logic has zero Streamlit-specific coupling and already
carries its own passing test suite. The FastAPI layer's job is persistence
and HTTP, not re-deriving business rules that were already fixed once.

## Project layout

```
truebind-web/
├── backend/                  FastAPI app
│   ├── app/
│   │   ├── models/           SQLAlchemy models (reports, sheets, mappings,
│   │   │                     claim_rows, validation_results, leakage_flags,
│   │   │                     obligations, alerts, templates, audit_log)
│   │   ├── schemas/          Pydantic request/response models
│   │   ├── services/         pipeline_service (bridges to bordereaux),
│   │   │                     persistence_service, audit_service, export_service
│   │   └── routes/           upload, mapping, reports, exceptions, duplicates,
│   │                         obligations, alerts, audit, templates
│   ├── migrations/           Alembic
│   └── tests/                pytest -- walks the real upload -> confirm ->
│                              process flow through the API and checks the
│                              persisted numbers against a direct call into
│                              bordereaux.pipeline on the same fixture
├── frontend/                 Next.js 16 App Router + TypeScript
│   ├── app/(dashboard)/      upload, reports, exceptions, duplicates, audit, todo
│   ├── components/           ui/ (design-system atoms), layout/, upload/,
│   │                         report/, exceptions/, duplicates/
│   ├── lib/                  api client, types, colorContrast validator
│   └── styles/                design tokens (variables.css) + globals
└── docker-compose.yml         postgres + backend + frontend, for local dev
```

## Running locally

### Option A — Docker Compose (recommended, matches production shape)

Requires Docker Desktop.

```bash
cd truebind-web
docker compose up --build
```

- Frontend: http://localhost:3000
- Backend API docs: http://localhost:8000/docs
- Postgres: localhost:5432 (user/pass/db: `truebind`/`dev`/`truebind`)

The backend runs `alembic upgrade head` automatically on container start.

### Option B — one command, natively (recommended for development)

Windows (PowerShell): `./dev.ps1`   ·   macOS/Linux: `./dev.sh`

This creates `backend/.env` from `backend/.env.example` if missing, runs the
database migrations, starts the API **with the job worker embedded**
(http://127.0.0.1:8000, docs at `/docs`), waits for `/health/ready`, then
starts the frontend (http://localhost:3000).

Prerequisites: Python 3.11+ with `pip install -r backend/requirements.txt`
(a `backend/.venv` is used automatically if present) and Node 20+.

**One database, always.** The API, the worker, each job's child process and
Alembic all read `backend/.env`, so they cannot drift onto different
databases. The default is `backend/data/truebind-mvp.db`. The legacy
`backend/data/truebind.db` is never opened unless you point `DATABASE_URL`
at it explicitly.

**Jobs are processed by a worker, never by the web request.** In development
the worker runs inside the API process (`TRUEBIND_EMBEDDED_WORKER=1`, the
default outside production); each job still runs in its own isolated child
process. In production set `TRUEBIND_ENV=production` and run
`python -m app.worker` as separate processes (as many as you need). If no
worker is alive, the UI says so instead of showing "queued" indefinitely
(`GET /api/v1/system/status`).

Manual equivalent:
```bash
cd truebind-web/backend && cp .env.example .env && alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000     # API + embedded worker
cd ../frontend && npm install && npm run dev
```

Open http://localhost:3000/login and create an account (self-service sign-up
is enabled outside production; set `ALLOW_SIGNUP=0` to disable).

**MVP limitations (internal testing only):** local-disk file storage; the
login rate limiter is in-memory (single process); in Docker Compose the app
connects as the Postgres superuser, which bypasses Row Level Security (the
application's own tenant filtering still applies — use a non-superuser role,
as the test suite does, to get database-enforced isolation).

## Tests

```bash
cd truebind-web/backend
pip install -r requirements-dev.txt
pytest tests/ -v                  # SQLite
# PostgreSQL (RLS + append-only audit tests run too); the role must NOT be a superuser:
TRUEBIND_TEST_DATABASE_URL=postgresql+psycopg://USER:PASS@localhost:5432/DB pytest tests/
```

```bash
cd truebind-web/frontend
npx tsc --noEmit      # typecheck
npm run build          # full production build, also runs the design-system
                        # contrast validator (lib/colorContrast.ts) at
                        # module-evaluation time -- the build fails loudly
                        # if any color pair drops below WCAG AA
```

## What's built (Phase 0) vs. deferred

**Built:** upload (drag-and-drop, multi-sheet), per-sheet mapping
confirmation with a real column picker and sample values, the full
validation/health-report pipeline persisted per row (not just a summary),
an Exceptions workspace with obligation-raising, a Duplicates review screen
with a real accept/reject/flag workflow (`review_status`, audit-logged —
Truebind never auto-merges), a filterable Audit log with CSV export, and a
cross-report Alerts/To-do inbox.

**Deferred, matching the brief's own phasing:**
- Payment-leakage detection, the sourced Lloyd's v5.2 template, and the
  governance-review-pack PDF export exist in the Streamlit build's `PR #3`
  branch (`claude/great-gauss-082g8l`) but not yet here — porting them is
  natural follow-up work, not started in this pass.
- Sanctions/PEP screening and technical account reconciliation are Phase 2
  of the *original* redevelopment brief and were never in scope here either.
- Auth: every action logs as a single `web_user` actor, same limitation as
  the Streamlit build. Not addressed before a real multi-user deployment.
- Production deployment (Render/Railway) — this covers local dev only.
