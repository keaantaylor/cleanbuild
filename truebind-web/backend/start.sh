#!/bin/sh
# Container entrypoint for hosted deployments (Render, Railway, Fly...):
# apply migrations, then serve. The embedded job worker starts with the API
# when TRUEBIND_EMBEDDED_WORKER=1. --proxy-headers makes the client IP (used
# by login/sign-up rate limits) come from X-Forwarded-For set by the host's
# load balancer instead of being the balancer's own address.
set -e
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
  --proxy-headers --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-*}"
