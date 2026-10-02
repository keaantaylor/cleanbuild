"""Phase 8 verification: generate bordereaux with planted problems (500, 2,000 and
10,000 rows), run each through the real API (stress_bench.py, with the
deliverables), and score recall, false positives and count agreement
(score_run.py). Writes docs/stress-pass/verify_phase8.json.

    truebind-web/backend/.venv/Scripts/python scripts/verify_pass.py [--sizes 500 2000 10000]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
sys.path.insert(0, str(ROOT / "truebind-web" / "backend" / "tests" / "fixtures"))
sys.path.insert(0, str(ROOT / "scripts"))
from generate_bordereau import generate  # noqa: E402
from score_run import score  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--sizes", nargs="+", type=int, default=[500, 2000, 10000])
ap.add_argument("--out", default=str(ROOT / "docs" / "stress-pass" / "verify_phase8.json"))
args = ap.parse_args()

work = Path(tempfile.mkdtemp(prefix="truebind-verify-"))
files = []
for n in args.sizes:
    f = work / f"Generated_{n}_rows.xlsx"
    generate(n, f, seed=n)
    files.append(f)
bench = work / "bench.json"
subprocess.run([PY, str(ROOT / "scripts" / "stress_bench.py"), "--label", "verify", "--deliverables", "--dump",
                str(work), "--out", str(bench), *map(str, files)], check=True, env=os.environ.copy(),
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
runs = json.loads(bench.read_text(encoding="utf-8"))
results = []
for f, run in zip(files, runs):
    dump = json.loads((work / f"{f.stem}.verify.json").read_text(encoding="utf-8"))
    key = json.loads(f.with_suffix(".answers.json").read_text(encoding="utf-8"))
    s = score(dump, key)
    results.append({
        "file": f.name, "claim_rows": key["claim_rows"], "total_s": run["total_s"], "process_s": run.get("process_s"),
        "peak_rss_mb": run["peak_rss_mb"], "deliverables": run.get("deliverables"), "recall": s["recall"],
        "planted": s["planted"], "found": s["found"], "missed": s["missed"], "false_positives": s["false_positives"],
        "false_positives_by_rule": s["false_positives_by_rule"], "agreement": s["agreement"],
        "health_view": run.get("health_view"),
    })
    print(json.dumps({k: results[-1][k] for k in ("file", "total_s", "recall", "planted", "found", "false_positives")}))
Path(args.out).write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
