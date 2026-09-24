#!/usr/bin/env bash
# TrueBind local development: one command starts everything that is needed.
#   API + job worker (embedded) on http://127.0.0.1:8000   (docs: /docs)
#   Frontend on http://localhost:3000
# Both backend processes read backend/.env, so they always share ONE database
# (default backend/data/truebind-mvp.db; the legacy data/truebind.db is never touched).
set -euo pipefail
root="$(cd "$(dirname "$0")" && pwd)"
cd "$root/backend"
[ -f .env ] || { cp .env.example .env; echo "Created backend/.env from .env.example"; }
PY="${PYTHON:-$( [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3 )}"
"$PY" -m alembic upgrade head
"$PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 &
API_PID=$!
trap 'kill $API_PID 2>/dev/null || true' EXIT
for _ in $(seq 60); do curl -sf http://127.0.0.1:8000/health/ready >/dev/null && break; sleep 0.5; done
cd "$root/frontend"
[ -d node_modules ] || npm install
npm run dev
