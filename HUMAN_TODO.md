# Human to-do

Things only a person with the right account, contract, payment method or authority can do.
Nothing here has been done by the build agent. Kept current every phase; P10 completes it.

## Now (carried over from deployment)
- [ ] **Render `cleanbuild-1` is still in development mode on SQLite** (data lost on restart). In Render → cleanbuild-1 → Environment set `DATABASE_URL` (Internal Database URL of the Render Postgres), `TRUEBIND_ENV=production`, `TRUEBIND_EMBEDDED_WORKER=1`, then redeploy. Confirm the log line `env=production database=postgresql+psycopg://***@…`.
- [ ] After your account exists on Postgres: set `ALLOW_SIGNUP=false` (the site is public on truebind.ie).
- [ ] **DNS for truebind.ie** at your registrar: `A @ 76.76.21.21`, `CNAME www cname.vercel-dns.com` (already added to the Vercel project). The domain did not resolve at all on 2026-09-25 — confirm the .ie registration completed.
- [ ] Review/merge PR keaantaylor/cleanbuild#12 (frontend API-origin hardening).

## Accounts (needed from P1/P2 onwards — details added as each phase lands)
- [ ] Sentry project (DSN) — P1.
- [ ] Object storage: Cloudflare R2 or AWS S3 (London/Dublin) bucket + access key — P1.
- [ ] Redis (Render Key Value or Upstash, EU) — P1.
- [ ] Microsoft Entra ID app registration or WorkOS (SSO) — P1.
- [ ] Postmark (inbound + outbound) and DNS for the inbound domain (MX, SPF, DKIM, DMARC) — P2.
- [ ] Azure OpenAI (EU region, zero data retention approved) or AWS Bedrock (eu-west-2/eu-central-1) — P2.
- [ ] Stripe account (Invoicing, bank transfer) — P9.
- [ ] Render paid plan (web + worker + Redis + Postgres with backups) — P10.

## Assurance (P10)
- [ ] Cyber Essentials Plus assessment; ISO 27001 / SOC 2 readiness — policies will be drafts only.
- [ ] Independent penetration test.
- [ ] Legal review of the DPA template and policies.
