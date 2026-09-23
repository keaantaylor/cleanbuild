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

from collections import OrderedDict
from pathlib import Path

from bordereaux import dedupe, mapping as mapping_mod, pipeline as bpipeline, report as report_mod, schema
from bordereaux.ingest import SheetData
from bordereaux.mapping import MappingBatchResult, MappingSuggestion
from bordereaux.pipeline import SheetMappingProposal, WorkbookProcessResult

FIELDS = schema.FIELDS
FIELDS_BY_CODE = schema.FIELDS_BY_CODE
REQUIRED_CODES = schema.REQUIRED_CODES

# TB-001: the same classification bordereaux.pipeline uses to decide
# whether a sheet's rows are emitted as claims at all -- reused here
# rather than re-derived, so the sheet-status the API reports for an
# already-processed report can never drift from the mapping-state
# machine that actually produced its data.
classify_sheet_status = report_mod.classify_sheet_status


def load_workbook(path: str | Path, source_stem: str | None = None) -> list[SheetData]:
    return bpipeline.load_workbook(path, source_stem=source_stem)


# Perf fix (profiling brief): the mapping-confirmation screen calls GET
# .../headers and GET .../mapping once PER SHEET, and each one used to
# call load_workbook() fresh -- re-reading and re-parsing the ENTIRE
# workbook from disk just to answer one sheet's question. Measured on a
# 20-sheet/26,000-row file: ~3.4s per call x 19 sheets = 64.7s spent on
# nothing but redundant re-reads, the dominant cost of the whole upload
# flow (bordereaux's own ingest is ~3.4s total, not per call). The
# uploaded file is immutable once stored, so there is no invalidation
# concern; bounded to a handful of most-recently-touched reports so a
# long-running server doesn't accumulate memory across many unrelated
# uploads that finished processing long ago.
_WORKBOOK_CACHE_MAXSIZE = 8
_workbook_cache: "OrderedDict[str, list[SheetData]]" = OrderedDict()


def load_workbook_cached(report_id: str, path: str | Path, source_stem: str | None = None) -> list[SheetData]:
    cached = _workbook_cache.get(report_id)
    if cached is not None:
        _workbook_cache.move_to_end(report_id)
        return cached
    sheets = bpipeline.load_workbook(path, source_stem=source_stem)
    _workbook_cache[report_id] = sheets
    if len(_workbook_cache) > _WORKBOOK_CACHE_MAXSIZE:
        _workbook_cache.popitem(last=False)
    return sheets


def seed_workbook_cache(report_id: str, sheets: list[SheetData]) -> None:
    """Upload already reads and parses the file once, before report_id
    even exists -- seeding the cache with that same already-loaded
    result (once the id is known) means the first mapping-confirmation
    GET call for this report is a cache hit too, instead of a second
    full re-read of a file the process just finished reading a moment
    ago."""
    _workbook_cache[report_id] = sheets
    _workbook_cache.move_to_end(report_id)
    if len(_workbook_cache) > _WORKBOOK_CACHE_MAXSIZE:
        _workbook_cache.popitem(last=False)


def evict_workbook_cache(report_id: str) -> None:
    """Called once a report finishes processing (successfully or not) --
    the parsed sheets are no longer needed after persist_pipeline_result
    has run, so there is no reason to hold them in memory for the rest
    of the server's life."""
    _workbook_cache.pop(report_id, None)


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
