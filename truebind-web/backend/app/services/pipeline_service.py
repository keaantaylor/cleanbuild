"""Wraps the existing, already-tested bordereaux pipeline (ingest, mapping,
validation, dedupe, report) for the FastAPI layer.

Deliberate reuse decision: the redesign brief's own section 2.4 called
this "re-implement your existing Python logic as FastAPI services", but
ingest.py/mapping.py/validation.py/dedupe.py/report.py/schema.py have zero
Streamlit coupling -- they are already pure pandas/dataclass code with
their own passing test suite (bordereaux/tests/test_phase{2..6}.py,
test_boundary_fixture.py). Re-implementing them from scratch would mean
carrying the same bugs the earlier fix-spec pass already found and fixed
a second time. This module is the only place that imports `bordereaux`;
everything above it talks to these thin wrappers instead."""

from __future__ import annotations

from pathlib import Path

from bordereaux import dedupe, mapping as mapping_mod, pipeline as bpipeline, report as report_mod, schema
from bordereaux.ingest import SheetData
from bordereaux.mapping import MappingBatchResult, MappingSuggestion
from bordereaux.pipeline import SheetMappingProposal, WorkbookProcessResult

FIELDS = schema.FIELDS
FIELDS_BY_CODE = schema.FIELDS_BY_CODE
REQUIRED_CODES = schema.REQUIRED_CODES


def load_workbook(path: str | Path) -> list[SheetData]:
    return bpipeline.load_workbook(path)


def propose_mapping_for_workbook(sheets: list[SheetData]) -> list[SheetMappingProposal]:
    """AI mapper is intentionally left as None here (build_mapping falls
    back to alias-only + a reported ai_unavailable_reason when no
    ANTHROPIC_API_KEY is set) -- same degrade-gracefully behavior as the
    Streamlit build, not a regression."""
    return bpipeline.propose_mapping_for_workbook(sheets)


def field_suggestions_by_code(proposal_mapping: MappingBatchResult) -> dict[str, MappingSuggestion | None]:
    """Invert "one suggestion per source column" into "one suggestion per
    canonical field" (or None if no column mapped to that field at all) --
    what the mapping-confirmation screen actually renders, one row per
    canonical field, not one row per raw header."""
    by_field: dict[str, MappingSuggestion] = {}
    for s in proposal_mapping.suggestions:
        if s.field_code:
            by_field[s.field_code] = s
    return {f.code: by_field.get(f.code) for f in FIELDS}


def sample_values(raw_df, source_column: str, limit: int = 3) -> list[str]:
    if source_column not in raw_df.columns:
        return []
    values = raw_df[source_column].dropna().astype(str).unique().tolist()
    return values[:limit]


def run_workbook_pipeline(
    sheets: list[SheetData],
    confirmed_mappings: dict[str, dict[str, str]],
    proposals: list[SheetMappingProposal],
    source_name: str = "",
) -> WorkbookProcessResult:
    return bpipeline.run_workbook_pipeline(sheets, confirmed_mappings, proposals, source_name=source_name)


def find_duplicates(canonical_df):
    return dedupe.find_duplicates(canonical_df)


def build_health_report(*args, **kwargs) -> "report_mod.HealthReport":
    return report_mod.build_health_report(*args, **kwargs)


def write_health_report_pdf(health, out_path):
    report_mod.write_health_report_pdf(health, out_path)


def write_health_report_excel(*args, **kwargs):
    report_mod.write_health_report_excel(*args, **kwargs)
