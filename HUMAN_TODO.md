# Human to-do

Things only a person with the right account, contract, payment method or authority can do.
Nothing here has been done by the build agent. Kept current every phase; P10 completes it.

## Now (carried over from deployment)
- [ ] **Render `cleanbuild-1` is still in development mode on SQLite** (data lost on restart). In Render → cleanbuild-1 → Environment set `DATABASE_URL` (Internal Database URL of the Render Postgres), `TRUEBIND_ENV=production`, `TRUEBIND_EMBEDDED_WORKER=1`, then redeploy. Confirm the log line `env=production database=postgresql+psycopg://***@…`.
- [ ] After your account exists on Postgres: set `ALLOW_SIGNUP=false` (the site is public on truebind.ie).
- [ ] **DNS for truebind.ie** at your registrar: `A @ 76.76.21.21`, `CNAME www cname.vercel-dns.com` (already added to the Vercel project). The domain did not resolve at all on 2026-09-25 — confirm the .ie registration completed.
- [ ] Review/merge PR keaantaylor/cleanbuild#12 (frontend API-origin hardening).

## Accounts (needed from P1/P2 onwards — details added as each phase lands)
- [ ] Render env: add `SECRET_KEY` (>= 32 random chars, e.g. `python -c "import secrets;print(secrets.token_urlsafe(48))"`) before deploying Platform V1 — production refuses to start without it.
- [ ] Sentry project (DSN) — P1.
- [ ] Object storage: AWS S3 (eu-west-2 London / eu-west-1 Dublin) or Cloudflare R2 (EU jurisdiction) bucket for originals with **versioning on**, **default encryption (SSE-S3 or KMS)**, **block public access**, optional **Object Lock (compliance mode)**, and a **lifecycle rule** expiring `tenants/*/originals/` after the agreed retention (docs/RETENTION.md). Create an access key limited to `s3:PutObject`, `s3:GetObject`, `s3:HeadObject` on that bucket (no delete permission). Then set `STORAGE_BACKEND=s3`, `S3_BUCKET`, `S3_REGION`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` (and `S3_ENDPOINT_URL` for R2) on Render.
- [ ] Redis (Render Key Value or Upstash, EU) — P1.
- [ ] SSO (per customer, optional): register an app in the customer's Microsoft Entra ID (or WorkOS). Redirect URI = `<PUBLIC_API_URL>/api/v1/auth/sso/callback` (shown in Settings → SSO); grant `openid email profile`; give TrueBind the issuer URL (`https://login.microsoftonline.com/<tenant-id>/v2.0`), client id and secret. Also set `PUBLIC_API_URL` and `PUBLIC_APP_URL` on Render. Domain ownership is not yet verified by DNS — only configure domains the organisation owns.
- [ ] Postmark (inbound + outbound) and DNS for the inbound domain (MX, SPF, DKIM, DMARC) — P2.
- [ ] Azure OpenAI (EU region, zero data retention approved) or AWS Bedrock (eu-west-2/eu-central-1) — P2.
- [ ] Stripe account (Invoicing, bank transfer) — P9.
- [ ] Render paid plan (web + worker + Redis + Postgres with backups) — P10.

## Assurance (P10)
- [ ] Cyber Essentials Plus assessment; ISO 27001 / SOC 2 readiness — policies will be drafts only.
- [ ] Independent penetration test.
- [ ] Legal review of the DPA template and policies.
