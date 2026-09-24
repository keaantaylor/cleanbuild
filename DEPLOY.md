# Deploying TrueBind

Two pieces:

| Piece | Host | Config |
|---|---|---|
| API + job worker + PostgreSQL | Render | `render.yaml` (Blueprint) |
| Web app | Vercel | project root `truebind-web/frontend` |

The browser only talks to the Vercel domain. `next.config.ts` rewrites
`/api/v1/*` to the API, so the session cookie is first-party and no CORS or
cross-site cookie settings are needed.

## 1. API on Render

1. render.com → **New → Blueprint** → pick this repository (branch `main`).
2. Accept the plan. It creates `truebind-db` (Postgres) and `truebind-api`
   (Docker, `truebind-web/backend/Dockerfile`). On every start the container
   runs `alembic upgrade head`, then the API with its embedded worker.
3. Optional: set `ANTHROPIC_API_KEY` for AI-assisted column mapping (headers
   only are sent). Without it, mapping is deterministic.
4. Note the service URL, e.g. `https://truebind-api.onrender.com`. Check
   `https://<that>/health/ready` returns `{"status":"ready"}`.

## 2. Web app on Vercel

Project settings:

- Root directory: `truebind-web/frontend` (framework: Next.js)
- Environment variables (Production and Preview):
  - `NEXT_PUBLIC_API_URL` = `/api/v1`
  - `TRUEBIND_API_ORIGIN` = the Render URL from step 1 (no trailing slash)

Both are read at build time, so redeploy after changing them.

## 3. First login

`ALLOW_SIGNUP=true` in `render.yaml`, so use **Sign up** on the login page to
create your organisation. Each sign-up gets its own isolated tenant. When your
team's accounts exist, set `ALLOW_SIGNUP=false` on the Render service.

## Free-tier limits (Render)

- The API sleeps after 15 minutes without traffic. The first request after
  that takes roughly a minute while it wakes.
- 512 MB RAM: fine for workbooks of a few thousand rows. Use the Starter plan
  or above for large files.
- No persistent disk: uploaded source files live on the container's disk and
  are lost on restart or redeploy. Reports, findings and audit trails are
  in Postgres and survive. A file whose source is lost before it is processed
  fails with "The uploaded file is no longer available. Upload it again."
  Attach a Render disk (paid) at `/app/data` to keep source files.
- The free Postgres database expires after 30 days. Upgrade it to keep data.
