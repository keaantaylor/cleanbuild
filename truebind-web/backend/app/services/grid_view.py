"""Inline workbook preview: the source sheet's cells, page by page, with the
review colour of each cell (the same colours as the annotated workbook) and
the finding text for amber and red cells.

The original values are read from the stored file once and cached (gzip JSON,
derived from the file's SHA-256), so paging through a 10,000-row sheet never
re-reads the workbook. Colours come from the stored findings per page.
"""

from __future__ import annotations

import datetime as dt
import gzip
import json
from collections import defaultdict

from sqlalchemy.orm import Session

from ..models.reports import ClaimRow, ExcludedRow, Report, Sheet, ValidationResult
from .deliverables import RESULT, _col_index, load_original, report_facts, _ws_for
from .storage import derived_key, get_store

MAX_COLS = 60
MAX_CELL = 200


def _show(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, (dt.datetime, dt.date)):
        return v.isoformat()[:19].replace("T", " ").removesuffix(" 00:00:00")
    s = str(v)
    return s if len(s) <= MAX_CELL else s[: MAX_CELL - 1] + "…"


def _cached_values(db: Session, report: Report, sheet_names: list[str]) -> dict[str, list[list[str | None]]]:
    key = derived_key(report.tenant_id, report.source_sha256 or "0" * 64, "grid-v1")
    store = get_store()
    blob = store.get_derived(key, db=db)
    if blob is not None:
        cached = json.loads(gzip.decompress(blob))
        if all(n in cached for n in sheet_names):
            return cached
    wb, _ = load_original(db, report)
    out: dict[str, list[list[str | None]]] = {}
    for name in sheet_names:
        ws = _ws_for(wb, name)
        if ws is None:
            continue
        rows = []
        for r in ws.iter_rows(max_col=MAX_COLS, values_only=True):
            rows.append([_show(v) for v in r])
        while rows and not any(rows[-1]):
            rows.pop()
        out[name] = rows
    store.put_derived(key, gzip.compress(json.dumps(out).encode()), db=db)
    return out


def grid_page(db: Session, report: Report, sheet: Sheet, offset: int, limit: int) -> dict:
    names = [s.sheet_name for s in db.query(Sheet).filter(Sheet.report_id == report.id, Sheet.status == "CONFIRMED")]
    values = _cached_values(db, report, names or [sheet.sheet_name]).get(sheet.sheet_name, [])
    ncols = min(max((len(r) for r in values), default=0), MAX_COLS)
    header_row = (sheet.header_row_index or 0) + 1
    first, last = offset + 1, min(offset + limit, len(values))

    claim_rows = {int(r) for (r,) in db.query(ClaimRow.source_row_number).filter(
        ClaimRow.report_id == report.id, ClaimRow.sheet_id == sheet.id,
        ClaimRow.source_row_number.between(first, last))}
    structural = set()
    for e in db.query(ExcludedRow).filter(ExcludedRow.report_id == report.id, ExcludedRow.sheet_name == sheet.sheet_name):
        for r in range(e.row_number, e.row_number + min(e.row_count or 1, 100000)):
            if first <= r <= last:
                structural.add(r)
    facts = report_facts(db, report).get(sheet.sheet_name) if sheet.status == "CONFIRMED" else None
    notes: dict[tuple[int, int | None], list[dict]] = defaultdict(list)
    if facts is not None:
        for r in range(first, last + 1):
            for f in facts.findings.get(r, []):
                notes[(r, _col_index(facts, f.field_code))].append(
                    {"result": RESULT.get(f.status, f.status), "status": f.status, "label": f.label,
                     "text": f.sentence, "fix": f.fix})
    rows = []
    for r in range(first, last + 1):
        cells = values[r - 1] if r - 1 < len(values) else []
        kind = ("header" if r == header_row else "structural" if r in structural or r < header_row
                else "claim" if r in claim_rows else "other")
        row_notes = notes.get((r, None), [])
        out_cells = []
        for c in range(1, ncols + 1):
            cell_notes = notes.get((r, c), [])
            tone = None
            if kind in ("header", "structural"):
                tone = "grey"
            elif kind == "claim":
                tone = ("err" if any(n["status"] == "FAIL" for n in cell_notes) else "warn" if cell_notes else "ok")
            out_cells.append({"v": cells[c - 1] if c - 1 < len(cells) else None, "tone": tone, "notes": cell_notes})
        rows.append({"row": r, "kind": kind, "cells": out_cells, "row_notes": row_notes})
    return {"sheet_id": sheet.id, "sheet_name": sheet.sheet_name, "total_rows": len(values), "columns": ncols,
            "header_row": header_row, "offset": offset, "rows": rows}
