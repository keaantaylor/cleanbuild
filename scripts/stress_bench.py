"""Stress benchmark: upload -> map -> confirm -> process, timed per stage.

Runs the real API in-process (FastAPI TestClient) and executes the queued jobs
inline, against a throwaway database (SQLite by default, or PostgreSQL when
BENCH_DATABASE_URL is set). Records wall time per phase, the job's own stage
timings and the process's peak memory, and saves the report summary,
exceptions and duplicates so accuracy can be scored afterwards.

Usage:
  python scripts/stress_bench.py --label before FILE [FILE ...] --out docs/stress-pass/bench_before.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "truebind-web" / "backend"
ap = argparse.ArgumentParser()
ap.add_argument("files", nargs="+")
ap.add_argument("--label", default="run")
ap.add_argument("--out", required=True)
ap.add_argument("--dump", help="folder to save each report's summary/exceptions/duplicates JSON")
ap.add_argument("--deliverables", action="store_true", help="also time the annotated workbook, corrected copy and query letter")
args = ap.parse_args()
OUT = Path(args.out).resolve()
DUMP = Path(args.dump).resolve() if args.dump else None
FILES = [Path(f).resolve() for f in args.files]

tmp = Path(tempfile.mkdtemp(prefix="truebind-bench-"))
os.environ.update({
    "TRUEBIND_NO_DOTENV": "1", "TRUEBIND_ENV": "test", "ALLOW_SIGNUP": "1", "TRUEBIND_EMBEDDED_WORKER": "0",
    "DATABASE_URL": os.environ.get("BENCH_DATABASE_URL") or f"sqlite:///{tmp / 'bench.db'}",
    "TRUEBIND_DATA_DIR": str(tmp / "data"), "TRUEBIND_STORAGE_DIR": str(tmp / "objects"),
    "MAX_UPLOAD_MB": "100",
})
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

import psutil  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

cfg = Config(str(BACKEND / "alembic.ini"))
cfg.set_main_option("script_location", str(BACKEND / "migrations"))
command.upgrade(cfg, "head")

from app.main import app  # noqa: E402
from app.worker import run_pending_jobs_inline  # noqa: E402

proc = psutil.Process()


class Peak:
    """Samples this process's resident memory every 50 ms."""

    def __init__(self) -> None:
        self.peak = 0
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.is_set():
            self.peak = max(self.peak, proc.memory_info().rss)
            time.sleep(0.05)

    def __enter__(self):
        self.peak = proc.memory_info().rss
        self._t.start()
        return self

    def __exit__(self, *a):
        self._stop.set()
        self._t.join()


c = TestClient(app, raise_server_exceptions=True)
r = c.post("/api/v1/auth/signup", json={"email": "bench@example.com", "password": "correct horse battery staple",
                                        "display_name": "Bench", "organisation": "Bench Org"})
assert r.status_code == 201, r.text
H = {"X-CSRF-Token": r.json()["csrf_token"]}

results = []
for f in FILES:
    rec: dict = {"file": f.name, "label": args.label}
    t_all = time.perf_counter()
    with Peak() as peak:
        t = time.perf_counter()
        up = c.post("/api/v1/reports/upload", files={"file": (f.name, f.read_bytes(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}, headers=H)
        assert up.status_code == 202, up.text
        rid = up.json()["id"]
        rec["upload_s"] = round(time.perf_counter() - t, 2)
        t = time.perf_counter()
        run_pending_jobs_inline()
        rec["ingest_s"] = round(time.perf_counter() - t, 2)
        rep = c.get(f"/api/v1/reports/{rid}").json()
        if rep["status"] != "WAITING_FOR_REVIEW":
            rec.update(status=rep["status"], error=rep.get("job"))
            results.append(rec)
            print(json.dumps(rec)[:400])
            continue
        t = time.perf_counter()
        sheets = c.get(f"/api/v1/reports/{rid}/sheets").json()
        rec["sheets"] = [{"name": s["sheet_name"], "status": s["status"]} for s in sheets]
        for s in sheets:
            if s["status"] == "SKIPPED":
                continue
            m = c.get(f"/api/v1/reports/{rid}/sheets/{s['id']}/mapping").json()
            choices = {fl["field_code"]: fl["source_column"] for fl in m["fields"]}
            rr = c.post(f"/api/v1/reports/{rid}/sheets/{s['id']}/mapping", json={"mappings": choices}, headers=H)
            assert rr.status_code == 200, rr.text
        pr = c.post(f"/api/v1/reports/{rid}/process", headers=H)
        assert pr.status_code in (200, 202), pr.text
        rec["confirm_s"] = round(time.perf_counter() - t, 2)
        t = time.perf_counter()
        run_pending_jobs_inline()
        rec["process_s"] = round(time.perf_counter() - t, 2)
    rec["total_s"] = round(time.perf_counter() - t_all, 2)
    rec["peak_rss_mb"] = round(peak.peak / 1024 / 1024)
    rep = c.get(f"/api/v1/reports/{rid}").json()
    rec["status"] = rep["status"]
    jobs = c.get(f"/api/v1/reports/{rid}/jobs").json()
    rec["jobs"] = [{"kind": j["kind"], "status": j["status"], "metrics": j.get("metrics")} for j in jobs]
    if rep["status"] == "COMPLETE":
        summ = c.get(f"/api/v1/reports/{rid}/summary").json()
        s = summ["summary"]
        rec["rows"] = rep.get("rows_total")
        rec["counts"] = {k: s.get(k) for k in ("missing_mandatory_rows", "arithmetic_mismatches", "arithmetic_not_evaluable",
                                              "exact_duplicates", "probable_duplicates", "development_pairs", "composite_score")}
        hv = summ.get("summary", {}).get("health_view") or {}
        rec["health_view"] = {"verdict": hv.get("verdict"), "counts": hv.get("counts"),
                              "duplicates": hv.get("duplicates")}
        if args.deliverables:
            rec["deliverables"] = {}
            for key, url in (("annotated", f"/api/v1/reports/{rid}/export/annotated.xlsx"),
                             ("corrected", f"/api/v1/reports/{rid}/export/corrected.xlsx"),
                             ("query_letter", f"/api/v1/reports/{rid}/query-letter")):
                t = time.perf_counter()
                with Peak() as dpeak:
                    resp = c.get(url)
                rec["deliverables"][key] = {"status": resp.status_code, "seconds": round(time.perf_counter() - t, 2),
                                            "bytes": len(resp.content), "peak_rss_mb": round(dpeak.peak / 1024 / 1024)}
                if DUMP and key != "query_letter" and resp.status_code == 200:
                    DUMP.mkdir(parents=True, exist_ok=True)
                    (DUMP / f"{f.stem}.{args.label}.{key}.xlsx").write_bytes(resp.content)
        if DUMP:
            DUMP.mkdir(parents=True, exist_ok=True)
            ex = c.get(f"/api/v1/reports/{rid}/exceptions", params={"limit": 100000}).json()
            du = c.get(f"/api/v1/reports/{rid}/duplicates").json()
            (DUMP / f"{f.stem}.{args.label}.json").write_text(json.dumps({"report": rep, "summary": summ, "exceptions": ex,
                                                                           "duplicates": du}, default=str), encoding="utf-8")
    results.append(rec)
    print(json.dumps({k: v for k, v in rec.items() if k not in ("jobs", "sheets")}), flush=True)

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
