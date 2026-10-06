# TrueBind: working notes for Claude Code

Claims-bordereaux integrity: map, validate, reconcile, audit. Branch `unify` = origin/main's look and pages
(Nocturne, live on www.truebind.ie) plus the Phase 1–5 engine and features from `frontend-redesign`.
Main's existing pages and styles are never removed or replaced; new features are added inside them.

## Repo map
- `bordereaux/`: the engine (Python). Rules, validation, reconcile. Don't touch for front-end work.
- `truebind-web/backend/`: FastAPI. `app/routes/*` (all under `/api/v1`), `app/schemas/reports.py`, `app/models/*`, `app/services/*`.
- `truebind-web/frontend/`: Next.js 16.3, React 19. Read `node_modules/next/dist/docs/` before using a Next API you're unsure of (see frontend/AGENTS.md).
  - `app/(marketing)` public site, `app/(dashboard)` the app (behind `components/auth/AuthGate`), `app/login`, `app/invite`, `app/onboarding`, `app/sender`.
  - `lib/api.ts`: the only way to call the backend. `lib/types.ts`: response types.
  - UI: `components/nocturne/*` (app), `components/site/*` (marketing), Tailwind v4 + `styles/globals.css` + `styles/nocturne.css`, Phosphor icons.
  - Phase 1–5 surfaces: report page views Health report · Review issues (`review-queue.tsx`) · Workbook (`workbook-grid.tsx`) · Trail (`trail.tsx`); `/senders` (sender memory).
- `docs/design/`: `FRONTEND_SPEC.md`, `FRONTEND_PLAN.md` and `landing-mockup.pdf` describe the abandoned Session 0 redesign (reference only); `review/<session>/` screenshots.

## Run and test on Windows (Git Bash)
- API: `cd truebind-web/backend && .venv/Scripts/python -m alembic upgrade head && .venv/Scripts/python -m uvicorn app.main:app --port 8000` (SQLite in the data dir when `DATABASE_URL` is unset).
- Both: `.\dev.ps1` from the repo root (API :8000 in its own window, web :3000). The user often has these running already: reuse them, don't kill them.
- Front-end checks, once per session at the end: `npm run lint && npx tsc --noEmit && npm run test && npm run build`.
- Visual review: `PLAYWRIGHT_CHROMIUM_EXECUTABLE=C:/Users/keala/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe npx playwright test -c playwright.visual.config.ts tests/visual/<session>.spec.ts` against the running dev app; saves to `docs/design/review/<session>/`.
- e2e: build with `MSYS_NO_PATHCONV=1 NEXT_PUBLIC_API_URL=/api/v1 npm run build`, set
  `PLAYWRIGHT_CHROMIUM_EXECUTABLE` to `ms-playwright/chromium-1243/chrome-win64/chrome.exe`, then `npx playwright test <spec>`.
  Playwright starts the API on :8765 and `next start` on :3100 itself.
- Backend tests: `.venv/Scripts/python -m pytest -q`; `test_worker_survives_child_that_exceeds_memory` always fails on Windows (needs Linux).
- Migrations: production is at `0020_leads`; 0021–0024 chain on top. Test with an explicit `DATABASE_URL` (backend/.env sets one).

## Design rules
- The look is Nocturne (origin/main): dark by default with a light toggle, mint accent `#34d399`, Inter. Main wins on look, every time.
- Colours come from the tokens in `styles/globals.css` / `nocturne.css` (`--text`, `--muted`, `--line`, `--accent`, `--ok`…); no new hex values in components.
- New screens copy main's patterns: `tb-card`, `tb-btn`, `tb-input`, `tb-pill`, `PageHeader`/`StatusPill`/`EmptyState`/`ErrorState` from `nocturne/ui`.
- Every screen: loading, empty, error and permission states; viewer role hides write actions; works at 390px; keyboard reachable.

## Honesty
- No invented customers, logos, testimonials, percentages or time-saved figures. Sample data is labelled "Sample".

## Working rules (the user pays per token)
- Read broadly only in planning; afterwards read only what the task needs.
- Remove nothing that exists on origin/main without the user's explicit OK.
- If instructions conflict with the real code, say so. Don't silently work around it.
- Run lint, typecheck, tests and build once, at the end. If the same error fails twice, stop and report.
- Reply format: what changed, test output tail (≤20 lines), screenshot paths plus the exact local URL to open, what's next. No file dumps.
- Commit at the end of each session (end messages with the Co-Authored-By line). Never push, merge or deploy unless asked.
- Never touch `C:\Users\keala\cleanbuild` (the user's own checkout with uncommitted work).
- Git stash is shared across worktrees: don't use bare `git stash`.
