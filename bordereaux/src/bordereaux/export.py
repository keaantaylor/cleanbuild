"""Segregated export: one sheet per claim status, sorted by date of loss."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import schema

_DISPLAY_COLUMNS = {f.code: f"{f.code} - {f.name}" for f in schema.FIELDS}
_SHEET_ORDER = ["open", "reopened", "closed", "other", "unspecified"]
_MAX_SHEET_NAME = 31  # Excel limit


def segregate(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Split df into one frame per claim status, each sorted by date of
    loss (nulls last). Rows with a missing/invalid status land in an
    'unspecified' bucket rather than being silently dropped."""
    status = df[schema.STATUS_CODE].fillna("unspecified")
    valid = set(schema.FIELDS_BY_CODE[schema.STATUS_CODE].enum_values)
    status = status.where(status.isin(valid) | (status == "unspecified"), "unspecified")

    groups: dict[str, pd.DataFrame] = {}
    for value in list(dict.fromkeys(_SHEET_ORDER + sorted(status.unique()))):
        mask = status == value
        if not mask.any():
            continue
        sheet = df[mask].sort_values(schema.LOSS_DATE_CODE, na_position="last").reset_index(drop=True)
        groups[value] = sheet
    return groups


def write_segregated_export(df: pd.DataFrame, out_path: str | Path) -> None:
    groups = segregate(df)
    out_path = Path(out_path)
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        for status, sheet in groups.items():
            renamed = sheet.rename(columns=_DISPLAY_COLUMNS)
            renamed.to_excel(writer, sheet_name=status[:_MAX_SHEET_NAME], index=False)
