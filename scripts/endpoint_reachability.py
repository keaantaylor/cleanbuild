"""Endpoint reachability check: every API operation is routed and does not crash.

Runs the backend in-process (FastAPI TestClient) against a throwaway SQLite
database, signs up an owner, then calls every operation in the OpenAPI
document with placeholder path values and a minimal body.

An operation is REACHABLE when the response is not:
  - 405 (method not routed),
  - 404 with FastAPI's bare {"detail": "Not Found"} (path not routed),
  - 5xx (the handler crashed).
Any other status (200, 201, 204, 400, 401, 403, 404 with a message, 409, 422, 429...)
proves the route exists and the handler ran its own checks.

Usage (from the repo root):  truebind-web/backend/.venv/Scripts/python scripts/endpoint_reachability.py [--json out.json]
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(sys.argv[sys.argv.index("--json") + 1]).resolve() if "--json" in sys.argv else None
BACKEND = ROOT / "truebind-web" / "backend"
tmp = Path(tempfile.mkdtemp(prefix="truebind-reach-"))
os.environ.update({
    "TRUEBIND_NO_DOTENV": "1", "TRUEBIND_ENV": "test", "ALLOW_SIGNUP": "1", "TRUEBIND_EMBEDDED_WORKER": "0",
    "DATABASE_URL": f"sqlite:///{tmp / 'reach.db'}", "TRUEBIND_DATA_DIR": str(tmp / "data"),
    "TRUEBIND_STORAGE_DIR": str(tmp / "objects"),
})
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

cfg = Config(str(BACKEND / "alembic.ini"))
cfg.set_main_option("script_location", str(BACKEND / "migrations"))
command.upgrade(cfg, "head")

from app.main import app  # noqa: E402

PLACEHOLDER = "00000000-0000-4000-8000-000000000000"
client = TestClient(app, raise_server_exceptions=False, follow_redirects=False)
me = client.post("/api/v1/auth/signup", json={"email": "reach@example.com", "password": "correct horse battery staple",
                                               "display_name": "Reach", "organisation": "Reach Org"})
assert me.status_code == 201, me.text
csrf = me.json()["csrf_token"]

results = []
for path, ops in sorted(app.openapi()["paths"].items()):
    for method in ops:
        if method == "parameters":
            continue
        url = path
        for seg in [s for s in path.split("/") if s.startswith("{")]:
            url = url.replace(seg, PLACEHOLDER)
        kw: dict = {"headers": {"X-CSRF-Token": csrf}}
        if method in ("post", "put", "patch"):
            kw["json"] = {}
        r = client.request(method.upper(), url, **kw)
        bare_404 = r.status_code == 404 and r.headers.get("content-type", "").startswith("application/json") and r.json() == {"detail": "Not Found"}
        # 503 with a reason is a deliberate "feature not configured on this server" answer, not a crash.
        not_configured = r.status_code == 503 and "not configured" in r.text.lower()
        ok = r.status_code != 405 and (r.status_code < 500 or not_configured) and not bare_404
        results.append({"method": method.upper(), "path": path, "status": r.status_code, "reachable": ok,
                        "note": "not configured on this server" if not_configured else ""})

bad = [r for r in results if not r["reachable"]]
nc = [r for r in results if r.get("note")]
print(f"operations: {len(results)} | reachable: {len(results) - len(bad)} (of which {len(nc)} answer 'not configured on this server') | not reachable: {len(bad)}")
for r in bad:
    print(f"  NOT REACHABLE {r['method']} {r['path']} -> {r['status']}")
if OUT:
    OUT.write_text(json.dumps(results, indent=1), encoding="utf-8")
sys.exit(1 if bad else 0)
