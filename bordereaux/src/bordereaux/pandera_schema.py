"""Pandera schema for the canonical (post-mapping) claims DataFrame.

Enforces column-level type and nullability per Section 3. The
row-level business rules from Section 8 (arithmetic, date ordering,
cross-row currency consistency, "at least one of paid/reserve") are
deliberately not expressible as simple column checks and instead live
in validation.py, whose output is the row-level exception report the
health report is built from.
"""

from __future__ import annotations

import pandas as pd
import pandera.pandas as pa

from .schema import FIELDS

# No enum-domain checks here: an unexpected claim status (e.g. "Pending",
# "+cmd") is a row-level `invalid_status` finding in validation.py. As a
# schema check it used to raise SchemaError and abort the WHOLE file over
# one cell (found by the export-injection test, 2026-09-24).
_CHECKS: dict = {}

_DTYPE_MAP = {
    "string": pd.StringDtype(),
    "enum": pd.StringDtype(),
    "currency": pd.StringDtype(),
    "date": "datetime64[ns]",
    "decimal": "float64",
}


def build_schema() -> pa.DataFrameSchema:
    # Nullability/"required" enforcement is deliberately NOT done here:
    # a missing mandatory field should show up as a row-level exception
    # in the health report (validation.py), not abort the whole file.
    # This schema only checks and coerces column types.
    columns = {}
    for f in FIELDS:
        columns[f.code] = pa.Column(
            _DTYPE_MAP[f.dtype],
            nullable=True,
            checks=_CHECKS.get(f.code),
            coerce=True,
        )
    return pa.DataFrameSchema(columns, strict=False)


CANONICAL_SCHEMA = build_schema()
