"""Load a raw bordereau file and apply a confirmed column mapping to
produce a canonical DataFrame keyed by the Section 3 field codes."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .schema import FIELDS, FIELDS_BY_CODE

# Tried in order; whichever format parses the most values for a given
# column wins. A final flexible-parser pass catches anything left over.
_DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%b-%Y", "%Y/%m/%d", "%d.%m.%Y"]


def load_raw(path: str | Path) -> pd.DataFrame:
    """Read a bordereau file as-is, all columns as strings (so numeric
    formatting, leading zeros etc. aren't mangled before mapping)."""
    path = str(path)
    if path.lower().endswith(".csv"):
        return pd.read_csv(path, dtype="string")
    return pd.read_excel(path, dtype="string", engine="openpyxl")


def _best_date_parse(series: pd.Series) -> pd.Series:
    non_null = series.dropna()
    if non_null.empty:
        return pd.to_datetime(series, errors="coerce")

    target = int(non_null.shape[0])
    best_parsed = None
    best_score = -1
    for fmt in _DATE_FORMATS:
        parsed = pd.to_datetime(series, format=fmt, errors="coerce")
        score = int(parsed.notna().sum())
        if score > best_score:
            best_score, best_parsed = score, parsed
        if best_score == target:
            break  # every non-null value parsed; no need for a flexible fallback

    if best_score < target:
        fallback = pd.to_datetime(series, format="mixed", errors="coerce")
        fallback_score = int(fallback.notna().sum())
        if fallback_score > best_score:
            return fallback
    return best_parsed


def apply_mapping(raw: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    """mapping: {source_column_name: field_code}. Source columns absent
    from the mapping are dropped; canonical fields absent from the mapping
    come back as all-null columns so downstream code can always rely on
    every field code being present."""
    out = pd.DataFrame(index=raw.index)

    for source_col, code in mapping.items():
        if source_col not in raw.columns or code not in FIELDS_BY_CODE:
            continue
        spec = FIELDS_BY_CODE[code]
        series = raw[source_col].astype("string").str.strip()
        series = series.mask(series == "", pd.NA)

        if spec.dtype == "date":
            out[code] = _best_date_parse(series)
        elif spec.dtype == "decimal":
            out[code] = pd.to_numeric(series, errors="coerce")
        elif spec.dtype == "enum":
            out[code] = series.str.lower()
        elif spec.dtype == "currency":
            out[code] = series.str.upper()
        else:
            out[code] = series

    for f in FIELDS:
        if f.code not in out.columns:
            out[f.code] = _empty_column(f.dtype, len(out), out.index)

    return out[[f.code for f in FIELDS]]


def _empty_column(dtype: str, length: int, index) -> pd.Series:
    """An all-null column of the right dtype for a field the caller's
    mapping doesn't cover, so pandera can coerce it like any other."""
    if dtype == "date":
        return pd.Series([pd.NaT] * length, index=index, dtype="datetime64[ns]")
    if dtype == "decimal":
        return pd.Series([np.nan] * length, index=index, dtype="float64")
    return pd.Series([pd.NA] * length, index=index, dtype="string")
