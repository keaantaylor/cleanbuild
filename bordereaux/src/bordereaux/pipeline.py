"""High-level orchestration shared by the CLI script and the Streamlit
app: load a raw file, propose a mapping, ingest against a confirmed
mapping, validate, dedupe, and build the health report. Kept UI-free so
both entry points reuse exactly the same logic (Section 6: every mapping
decision logged the same way regardless of front end)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from . import dedupe, export, ingest, report, validation
from .mapping import AIMapper, MappingSuggestion, audit_trail, build_mapping
from .pandera_schema import CANONICAL_SCHEMA


@dataclass
class ProcessResult:
    canonical: pd.DataFrame
    exceptions: pd.DataFrame
    duplicates: pd.DataFrame
    health: "report.HealthReport"
    suggestions: list[MappingSuggestion]


def propose_mapping(raw: pd.DataFrame, ai_mapper: AIMapper | None = None) -> list[MappingSuggestion]:
    return build_mapping(list(raw.columns), ai_mapper=ai_mapper)


def run_pipeline(raw: pd.DataFrame, confirmed_mapping: dict[str, str],
                  source_name: str = "") -> ProcessResult:
    canonical = ingest.apply_mapping(raw, confirmed_mapping)
    CANONICAL_SCHEMA.validate(canonical)

    exceptions = validation.validate(canonical)
    duplicates = dedupe.find_duplicates(canonical)
    health = report.build_health_report(canonical, exceptions, duplicates, source_name=source_name)

    return ProcessResult(
        canonical=canonical,
        exceptions=exceptions,
        duplicates=duplicates,
        health=health,
        suggestions=[],
    )


def process_path(path: str | Path, confirmed_mapping: dict[str, str]) -> ProcessResult:
    raw = ingest.load_raw(path)
    return run_pipeline(raw, confirmed_mapping, source_name=Path(path).name)


def write_outputs(result: ProcessResult, out_dir: str | Path, stem: str) -> dict[str, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    segregated_path = out_dir / f"{stem}_segregated.xlsx"
    export.write_segregated_export(result.canonical, segregated_path)

    health_path = out_dir / f"{stem}_health_report.xlsx"
    report.write_health_report_excel(result.health, result.exceptions, result.duplicates,
                                      result.canonical, health_path)

    health_pdf_path = out_dir / f"{stem}_health_report.pdf"
    report.write_health_report_pdf(result.health, health_pdf_path)

    return {"segregated": segregated_path, "health": health_path, "health_pdf": health_pdf_path}
