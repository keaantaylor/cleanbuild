"""Parse once: cache the parsed workbook from the mapping (INGEST) job so the
PROCESS job does not read the spreadsheet again.

Parsing is the slowest single step on large files (about 60% of processing
time for 30,000 rows), and both jobs used to do it. The parsed sheets are
stored as gzip-compressed JSON next to the original (a *derived* object, see
storage.py), keyed by the original's SHA-256 and a format version. JSON, not
pickle: a cache read can never execute code. Any problem reading the cache
(missing, older format, corrupt) simply falls back to parsing the original.
"""

from __future__ import annotations

import dataclasses
import gzip
import json
import logging
import math
from typing import Any

import pandas as pd
from bordereaux.ingest import ExcludedRow, SheetData

from .storage import derived_key, get_store

log = logging.getLogger("truebind.jobs")


def _parser_fingerprint() -> str:
    """Changes whenever the parser's code changes, so a cache written by an
    older version is never reused after a deploy."""
    import hashlib
    from pathlib import Path

    import bordereaux.ingest as ingest_mod
    import bordereaux.pipeline as pipeline_mod

    h = hashlib.sha256()
    for mod in (ingest_mod, pipeline_mod):
        h.update(Path(mod.__file__ or "").read_bytes())
    return h.hexdigest()[:8]


FORMAT = f"parsed-v1-{_parser_fingerprint()}"


def _cell(v: Any) -> Any:
    if v is None or v is pd.NA or (isinstance(v, float) and math.isnan(v)):
        return None
    return v if isinstance(v, (str, int, float, bool)) else str(v)


def dumps(sheets: list[SheetData]) -> bytes:
    out = []
    for s in sheets:
        d: dict[str, Any] = {}
        for f in dataclasses.fields(s):
            v = getattr(s, f.name)
            if f.name == "raw":
                d["raw"] = {"columns": [str(c) for c in v.columns],
                            "rows": [[_cell(x) for x in row] for row in v.itertuples(index=False, name=None)],
                            "dtypes": {str(c): str(t) for c, t in v.dtypes.items()}}
            elif f.name == "excluded_rows":
                d["excluded_rows"] = [dataclasses.asdict(er) for er in v]
            else:
                d[f.name] = v
        out.append(d)
    return gzip.compress(json.dumps({"format": FORMAT, "sheets": out}, ensure_ascii=False).encode("utf-8"), 6)


def loads(data: bytes) -> list[SheetData]:
    doc = json.loads(gzip.decompress(data).decode("utf-8"))
    if doc.get("format") != FORMAT:
        raise ValueError("parse cache format changed")
    sheets = []
    for d in doc["sheets"]:
        raw = d.pop("raw")
        df = pd.DataFrame(raw["rows"], columns=raw["columns"]) if raw["rows"] else pd.DataFrame(columns=raw["columns"])
        for col, dtype in raw["dtypes"].items():
            if col in df.columns and str(df[col].dtype) != dtype:
                df[col] = df[col].astype(dtype)
        d["excluded_rows"] = [ExcludedRow(**er) for er in d.get("excluded_rows", [])]
        sheets.append(SheetData(raw=df, **d))
    return sheets


def save(db: Any, tenant_id: str, source_sha256: str, sheets: list[SheetData]) -> None:
    """Best effort: a failure here only means PROCESS parses again."""
    try:
        get_store().put_derived(derived_key(tenant_id, source_sha256, FORMAT), dumps(sheets), db=db)
    except Exception:  # noqa: BLE001
        log.warning("parse cache not saved for %s", source_sha256[:12], exc_info=True)


def load(db: Any, tenant_id: str, source_sha256: str) -> list[SheetData] | None:
    try:
        data = get_store().get_derived(derived_key(tenant_id, source_sha256, FORMAT), db=db)
        return loads(data) if data else None
    except Exception:  # noqa: BLE001
        log.warning("parse cache unreadable for %s; parsing the original", source_sha256[:12], exc_info=True)
        return None
