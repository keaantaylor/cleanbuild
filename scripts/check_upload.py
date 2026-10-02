"""Upload one workbook through the real API in-process, process it, and check
the inline review grid is colour-coded. Prints a one-line summary.

    truebind-web/backend/.venv/Scripts/python scripts/check_upload.py FILE.xlsx
"""

from __future__ import annotations

import collections
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "truebind-web" / "backend"
src = Path(sys.argv[1]).resolve()
tmp = Path(tempfile.mkdtemp(prefix="truebind-check-"))
os.environ.update({"TRUEBIND_NO_DOTENV": "1", "TRUEBIND_ENV": "test", "ALLOW_SIGNUP": "1", "TRUEBIND_EMBEDDED_WORKER": "0",
                   "DATABASE_URL": f"sqlite:///{tmp / 'c.db'}", "TRUEBIND_DATA_DIR": str(tmp / "data"),
                   "TRUEBIND_STORAGE_DIR": str(tmp / "objects")})
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

cfg = Config(str(BACKEND / "alembic.ini"))
cfg.set_main_option("script_location", str(BACKEND / "migrations"))
command.upgrade(cfg, "head")
from app.main import app  # noqa: E402
from app.worker import run_pending_jobs_inline  # noqa: E402

t0 = time.perf_counter()
c = TestClient(app)
H = {"X-CSRF-Token": c.post("/api/v1/auth/signup", json={"email": "c@example.com", "password": "correct horse battery staple",
                                                          "display_name": "C", "organisation": "C"}).json()["csrf_token"]}
rid = c.post("/api/v1/reports/upload", files={"file": (src.name, src.read_bytes(), "application/octet-stream")}, headers=H).json()["id"]
run_pending_jobs_inline()
sheets = c.get(f"/api/v1/reports/{rid}/sheets").json()
for s in sheets:
    if s["status"] != "SKIPPED":
        m = c.get(f"/api/v1/reports/{rid}/sheets/{s['id']}/mapping").json()
        c.post(f"/api/v1/reports/{rid}/sheets/{s['id']}/mapping", headers=H,
               json={"mappings": {f["field_code"]: f["source_column"] for f in m["fields"]}})
c.post(f"/api/v1/reports/{rid}/process", headers=H)
run_pending_jobs_inline()
rep = c.get(f"/api/v1/reports/{rid}").json()
assert rep["status"] == "COMPLETE", rep["status"]
tones = collections.Counter()
for s in c.get(f"/api/v1/reports/{rid}/sheets").json():
    if s["status"] != "CONFIRMED":
        continue
    off = 0
    while True:
        g = c.get(f"/api/v1/reports/{rid}/sheets/{s['id']}/grid", params={"offset": off, "limit": 500}).json()
        for r in g["rows"]:
            for cell in r["cells"]:
                tones[cell["tone"]] += 1
        off += 500
        if off >= g["total_rows"]:
            break
hv = c.get(f"/api/v1/reports/{rid}/summary").json()["summary"]["health_view"]
print(f"{src.name}: COMPLETE in {time.perf_counter() - t0:.1f}s; verdict {hv['verdict_label']}; "
      f"{hv['counts']['errors']} errors, {hv['counts']['warnings']} warnings; grid cells by colour {dict(tones)}")
