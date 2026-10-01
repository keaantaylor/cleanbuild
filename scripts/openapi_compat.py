"""Is the current API an additive change of the frozen snapshot?

Reports removed operations, removed schema properties and properties that
became required (each would break an existing client). Exit 1 if any.
With --update, writes the current document as the new snapshot when the
change is additive.

Usage (repo root): truebind-web/backend/.venv/Scripts/python scripts/openapi_compat.py [--update]
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAP = ROOT / "scripts" / "openapi-snapshot.json"
sys.path.insert(0, str(ROOT / "truebind-web" / "backend"))
os.environ.setdefault("TRUEBIND_NO_DOTENV", "1")
os.environ.setdefault("TRUEBIND_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.chdir(ROOT / "truebind-web" / "backend")

from app.main import app

cur = json.loads(json.dumps(app.openapi(), sort_keys=True))
old = json.loads(SNAP.read_text(encoding="utf-8"))


def ops(doc):
    return {f"{m.upper()} {p}" for p, o in doc.get("paths", {}).items() for m in o if m != "parameters"}


problems = []
removed_ops = sorted(ops(old) - ops(cur))
problems += [f"operation removed: {o}" for o in removed_ops]
old_s = old.get("components", {}).get("schemas", {})
cur_s = cur.get("components", {}).get("schemas", {})
for name, sch in old_s.items():
    if name not in cur_s:
        problems.append(f"schema removed: {name}")
        continue
    gone = set(sch.get("properties", {})) - set(cur_s[name].get("properties", {}))
    problems += [f"{name}.{p} removed" for p in sorted(gone)]
    newly_required = set(cur_s[name].get("required", [])) - set(sch.get("required", []))
    problems += [f"{name}.{p} became required" for p in sorted(newly_required)]

added_ops = sorted(ops(cur) - ops(old))
added_props = sorted(f"{n}.{p}" for n, s in cur_s.items() if n in old_s
                     for p in set(s.get("properties", {})) - set(old_s[n].get("properties", {})))
print(json.dumps({"operations_before": len(ops(old)), "operations_after": len(ops(cur)), "added_operations": added_ops,
                  "added_properties": added_props, "added_schemas": sorted(set(cur_s) - set(old_s)),
                  "breaking": problems}, indent=1))
if problems:
    sys.exit(1)
if "--update" in sys.argv:
    SNAP.write_text(json.dumps(cur, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print("snapshot updated")
