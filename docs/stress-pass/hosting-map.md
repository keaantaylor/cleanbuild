# TrueBind hosting map (checked 2026-10-01)

| Part | Provider | Plan / size | Region | Evidence |
|---|---|---|---|---|
| Website (Next.js) and the `/api/v1` proxy | Vercel, project `cleanbuild`, team keaantaylors-projects | Fluid compute, basic build machine; plan not readable via API | Functions in `iad1` (Washington DC, US East); static pages served from Vercel's global edge | Vercel project API |
| API + embedded job worker (FastAPI) | Render web service | `free` in render.yaml (0.1 CPU, 512 MB RAM, sleeps after 15 min idle); **dashboard value not visible from here** | `frankfurt` in render.yaml; **dashboard value not visible from here** | render.yaml only |
| Database (PostgreSQL 17) | Render | `free` in render.yaml (1 GB, no backups, expires after 30 days); you reported "PLAN-NAME", so unconfirmed | **Virginia, USA** (host `…virginia-postgres.render.com`) | Live connection, 2026-10-01 |
| Uploaded originals | Before this pass: the API instance's local disk (ephemeral: wiped on restart, redeploy or sleep) | n/a | Same as the API | `STORAGE_BACKEND` unset → `local` |
| Uploaded originals (after this pass) | The PostgreSQL database (`stored_blobs`, Row Level Security) | uses database space | Database region | `STORAGE_BACKEND` unset in production → `db` |
| Email (SMTP), inbound email, AI provider, S3 | Not configured | — | — | Settings → Channels shows the live state |

## Mismatch with the public pages

The privacy and security pages say data is hosted in the EU. The database is in Virginia (USA) and Vercel's
functions run in iad1 (USA). Options (need approval):

1. **Move to Frankfurt** (keeps the EU claim): create a Frankfurt PostgreSQL on Render, restore the verified
   backup into it, point the API at it, set Vercel's function region to `fra1`. A Render paid database plan is
   needed for backups and to avoid the free plan's 30-day expiry.
2. **Correct the wording** (no infrastructure change): say data is hosted with Render and Vercel in the United
   States, with the EU-US Data Privacy Framework / standard contractual clauses as the transfer basis.
