# Blockers

Open items that stopped or limited a task. Each: what failed, what was tried, hypothesis, what unblocks it.

## B1 — verify.py not executed on Windows (open, non-blocking)
- **What**: the harness is written to be cross-platform (pure Python driver, `shutil.which` resolves `npx.cmd`/`npm.cmd`, pathlib, Windows gitleaks zip in `--install-tools`), but this build environment is Linux only, so it has never been run under PowerShell.
- **Risk**: path quoting in the Playwright `webServer` command (`"<python>" -m ...`) and Docker Desktop's compose `--wait` behaviour.
- **Unblock**: run `python scripts\verify.py --fast` then `--full` once on a Windows machine with Docker Desktop; log results here.

## B2 — async route bodies are not traced by coverage in this app (tooling limitation, not a product defect)
Evidence (P2 gate, 2026-09-28). Under pytest (pytest-cov or `coverage run -m pytest`) and in a plain script importing `app.main`, lines after the first `await` in async functions are reported as not executed, even when they provably ran. A request to `/api/v1/inbound/email/postmark` returned 400 "Body must be JSON" from inside `_json_body`, yet lines 72-80 were reported missing. A minimal FastAPI app with the same shape is fully traced (100%). The difference is in this app's middleware/runtime stack; the root cause was not found within the attempt budget.
Impact: async routes (inbound provider webhooks, the observability middleware, exception handlers) are under-reported. Their behaviour is covered by tests (`tests/test_inbound_email.py`, `tests/test_observability.py`). The coverage baseline is not lowered for this. New P2 code was brought over the line with genuine edge-case tests (`tests/test_channel_edges.py`).
Next step for a human or a later session: bisect the middleware stack (the observability `app.middleware("http")` wrapper, then CORS, then the size/security middleware) with the probe `coverage run` script to find the layer that breaks tracing after `await`.
