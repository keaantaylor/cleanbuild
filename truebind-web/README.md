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

### Option B — run each service natively

**Backend** (Python 3.11+):
```bash
cd truebind-web/backend
pip install -r requirements.txt   # installs ../../bordereaux as an editable dep too
alembic upgrade head              # creates data/truebind.db (SQLite) by default
TRUEBIND_EMBEDDED_WORKER=1 uvicorn app.main:app   # API + job worker in one process
```

Uploads are processed by the job worker, not the web request. Either set
`TRUEBIND_EMBEDDED_WORKER=1` as above, or run `python -m app.worker` in a
second terminal (run several for parallelism). Without a worker, uploads
stay `QUEUED`.

**Frontend** (Node 20+):
```bash
cd truebind-web/frontend
npm install
cp .env.local.example .env.local   # points at http://localhost:8000/api/v1
npm run dev
```

Open http://localhost:3000/login and create an account (self-service sign-up
is enabled outside production; set `ALLOW_SIGNUP=0` to disable). Then:
upload → wait for "Reading your workbook…" → confirm each sheet's mapping →
"Proceed to health report" → report, exceptions, duplicates, CSV exports.

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
