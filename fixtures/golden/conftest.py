"""Golden module suites run the real application end to end (upload, map,
process, check) with the backend's own test harness: its database set-up,
per-test clean state and the signed-in `api` client."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_PATH = Path(__file__).resolve().parents[2] / "truebind-web" / "backend" / "tests" / "conftest.py"
_spec = importlib.util.spec_from_file_location("backend_conftest", _PATH)
assert _spec is not None and _spec.loader is not None
backend_conftest = importlib.util.module_from_spec(_spec)
sys.modules["backend_conftest"] = backend_conftest
_spec.loader.exec_module(backend_conftest)

pytest_sessionstart = backend_conftest.pytest_sessionstart
_clean_state = backend_conftest._clean_state
api = backend_conftest.api
db = backend_conftest.db
