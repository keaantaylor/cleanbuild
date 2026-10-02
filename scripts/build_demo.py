"""Build the public demo (/demo) from a generated sample bordereau.

Generates a synthetic 500-row file with planted problems (no real data), runs
it through the real API in-process, and writes:
  frontend/public/demo/Sample_Bordereau.xlsx            the file as "received"
  frontend/public/demo/Sample_Bordereau_REVIEWED.xlsx   annotated workbook
  frontend/public/demo/Sample_Bordereau_CORRECTED.xlsx  corrected copy
  frontend/lib/demo-report.json                          health view + query letter

    truebind-web/backend/.venv/Scripts/python scripts/build_demo.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "truebind-web" / "backend"
FRONT = ROOT / "truebind-web" / "frontend"
tmp = Path(tempfile.mkdtemp(prefix="truebind-demo-"))
os.environ.update({"TRUEBIND_NO_DOTENV": "1", "TRUEBIND_ENV": "test", "ALLOW_SIGNUP": "1", "TRUEBIND_EMBEDDED_WORKER": "0",
                   "DATABASE_URL": f"sqlite:///{tmp / 'demo.db'}", "TRUEBIND_DATA_DIR": str(tmp / "data"),
                   "TRUEBIND_STORAGE_DIR": str(tmp / "objects")})
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "tests" / "fixtures"))
os.chdir(BACKEND)

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from generate_bordereau import generate  # noqa: E402

cfg = Config(str(BACKEND / "alembic.ini"))
cfg.set_main_option("script_location", str(BACKEND / "migrations"))
command.upgrade(cfg, "head")

from app.main import app  # noqa: E402
from app.worker import run_pending_jobs_inline  # noqa: E402

src = tmp / "Sample_Bordereau.xlsx"
key = generate(500, src, seed=26)
c = TestClient(app)
r = c.post("/api/v1/auth/signup", json={"email": "demo@example.com", "password": "correct horse battery staple",
                                        "display_name": "Demo", "organisation": "Sample Coverholder Ltd"})
H = {"X-CSRF-Token": r.json()["csrf_token"]}
rid = c.post("/api/v1/reports/upload", files={"file": (src.name, src.read_bytes(),
             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}, headers=H).json()["id"]
run_pending_jobs_inline()
for s in c.get(f"/api/v1/reports/{rid}/sheets").json():
    if s["status"] == "SKIPPED":
        continue
    m = c.get(f"/api/v1/reports/{rid}/sheets/{s['id']}/mapping").json()
    c.post(f"/api/v1/reports/{rid}/sheets/{s['id']}/mapping", headers=H,
           json={"mappings": {f["field_code"]: f["source_column"] for f in m["fields"]}})
c.post(f"/api/v1/reports/{rid}/process", headers=H)
run_pending_jobs_inline()
report = c.get(f"/api/v1/reports/{rid}").json()
assert report["status"] == "COMPLETE", report
summary = c.get(f"/api/v1/reports/{rid}/summary").json()["summary"]
letter = c.get(f"/api/v1/reports/{rid}/query-letter").json()
out = FRONT / "public" / "demo"
out.mkdir(parents=True, exist_ok=True)
shutil.copy(src, out / "Sample_Bordereau.xlsx")
(out / "Sample_Bordereau_REVIEWED.xlsx").write_bytes(c.get(f"/api/v1/reports/{rid}/export/annotated.xlsx").content)
(out / "Sample_Bordereau_CORRECTED.xlsx").write_bytes(c.get(f"/api/v1/reports/{rid}/export/corrected.xlsx").content)
demo = {
    "file_name": "Sample_Bordereau.xlsx", "rows": summary["reconciliation"]["exported_rows"],
    "sheets_total": summary["sheets_total"], "sheets_processed": summary["sheets_processed"],
    "planted_problems": len(key["planted"]), "health_view": summary["health_view"],
    "skipped_sheets": summary.get("skipped_sheets", []) + summary.get("non_claim_summary_sheets", []),
    "query_letter": {"subject": letter["subject"], "body": letter["body"], "items": letter["items"]},
}
(FRONT / "lib" / "demo-report.json").write_text(json.dumps(demo, indent=1, default=str), encoding="utf-8")
print(f"demo built: {demo['rows']} rows, verdict {demo['health_view']['verdict']}, "
      f"{demo['health_view']['counts']['errors']} errors, {demo['health_view']['counts']['warnings']} warnings")
