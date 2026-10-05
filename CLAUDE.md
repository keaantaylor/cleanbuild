# TrueBind: working notes for Claude Code

Claims-bordereaux integrity: map, validate, reconcile, audit. Branch `rebuild` holds backend Phases 1–5;
the front-end redesign happens on `frontend-redesign` (from `rebuild`), one session at a time.

## Repo map
- `bordereaux/`: the engine (Python). Rules, validation, reconcile. Don't touch for front-end work.
- `truebind-web/backend/`: FastAPI. `app/routes/*` (all under `/api/v1`), `app/schemas/reports.py`, `app/models/*`, `app/services/*`.
- `truebind-web/frontend/`: Next.js 16.3, React 19. Read `node_modules/next/dist/docs/` before using a Next API you're unsure of (see frontend/AGENTS.md).
  - `app/(marketing)` public site, `app/(dashboard)` the app (behind `components/auth/AuthGate`), `app/login`, `app/invite`, `app/onboarding`, `app/sender`.
  - `lib/api.ts`: the only way to call the backend. `lib/types.ts`: response types.
  - New UI: `styles/tokens.css`, `components/ds/*` (CSS Modules; read `components/ds/index.ts` only), `components/layout/{MarketingShell,AppShell}`, `lib/flags.ts`, `lib/statusMeta.ts`. `/design-system` shows every component.
  - Old UI being replaced: `components/nocturne/*`, `components/site/*` (Tailwind v4). `nocturne/ui.tsx` now wraps ds components.
  - Kept on purpose: Tailwind (old screens), Phosphor icons (the mockup uses them), IBM Plex Mono. No new dependencies without a concrete reason.
- `docs/design/`: `landing-mockup.pdf` (visual source of truth), `FRONTEND_SPEC.md` (spec), `FRONTEND_PLAN.md` (screens, endpoints, sessions, gaps), `review/<session>/` (screenshots).

## Run and test on Windows (Git Bash)
- API: `cd truebind-web/backend && .venv/Scripts/python -m alembic upgrade head && .venv/Scripts/python -m uvicorn app.main:app --port 8000` (SQLite in the data dir when `DATABASE_URL` is unset).
- Both: `.\dev.ps1` from the repo root (API :8000 in its own window, web :3000). The user often has these running already: reuse them, don't kill them.
- Front-end checks, once per session at the end: `npm run lint && npx tsc --noEmit && npm run test && npm run build`.
- Visual review: `PLAYWRIGHT_CHROMIUM_EXECUTABLE=C:/Users/keala/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe npx playwright test -c playwright.visual.config.ts tests/visual/<session>.spec.ts` against the running dev app; saves to `docs/design/review/<session>/`.
- e2e: build with `MSYS_NO_PATHCONV=1 NEXT_PUBLIC_API_URL=/api/v1 npm run build`, set
  `PLAYWRIGHT_CHROMIUM_EXECUTABLE` to `ms-playwright/chromium-1243/chrome-win64/chrome.exe`, then `npx playwright test <spec>`.
  Playwright starts the API on :8765 and `next start` on :3100 itself.
- Backend tests (only if a backend file changes, which it shouldn't): need a chmod shim on Windows (originals are 0o400);
  `test_worker_survives_child_that_exceeds_memory` always fails on Windows.

## Design rules
- Marketing (`data-theme="dark"`) matches `docs/design/landing-mockup.pdf`. The app uses the same language on light.
- Colours only from `styles/tokens.css`; no hex anywhere else. Every text/background pair is in `lib/colorContrast.ts` and passes WCAG AA.
- Inter for UI, IBM Plex Mono for codes, cell values and hashes. Tabular numbers, right-aligned in tables.
- Hierarchy from type and space, not colour. Colour means status, highlight or the one brand blue.
- App: no gradients, glows, glass, icon-circle card grids, score rings, emoji, exclamation marks or em dashes in copy. Marketing keeps the PDF's subtle glows (`--glow-*`).
- One primary button per view. Sentence case. Uppercase only for eyebrows.
- System codes (`BND_OVER_AUTHORITY`) appear small and mono *under* a plain label, never instead of one.
- Status words go through `statusMeta()`. Grades never headline alone; never "Excellent" while breaches are open or required fields unmapped.
- Screens never compute a verdict; they call `lib/verdict.ts`.
- Every screen: loading, empty, error and permission states; viewer role hides write actions; 390px with no sideways scroll;
  keyboard-complete with visible focus; drawers/modals trap and return focus.

## Honesty
- No invented customers, logos, testimonials, percentages or time-saved figures. Sample data is labelled "Sample".
- Claims that need backend work stay behind `claims` in `lib/flags.ts` (see FRONTEND_PLAN.md, Gaps).

## Working rules (the user pays per token)
- Read broadly only in planning. In a session, read only what that session needs (FRONTEND_PLAN.md lists it).
- Front end only. Never change backend behaviour; record backend gaps in FRONTEND_PLAN.md.
- If the spec conflicts with the real code, say so. Don't silently work around it.
- Run lint, typecheck, tests and build once, at the end. If the same error fails twice, stop and report.
- Reply format: what changed, test output tail (≤20 lines), screenshot paths plus the exact local URL to open, what's next. No file dumps.
- Commit at the end of each session (end messages with the Co-Authored-By line). Never push, merge or deploy unless asked.
- Never touch `C:\Users\keala\cleanbuild` (the user's own checkout with uncommitted work).
- Git stash is shared across worktrees: don't use bare `git stash`.
