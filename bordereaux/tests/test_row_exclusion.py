"""Regression test for the "repeated header row mid-sheet" defect: a sheet
with two data blocks separated by a second copy of the header row must
ingest every real claim row from both blocks, exclude the repeated header
row itself (never as a claim, never as a "missing mandatory field"
violation), and report that exclusion by name/count -- the same way
blank and subtotal rows are now excluded and reported too."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import openpyxl  # noqa: E402

from bordereaux import pipeline  # noqa: E402

import tempfile  # noqa: E402

_GEN_DIR = Path(tempfile.gettempdir()) / "truebind_generated_fixtures"  # never rewrite tracked files
_GEN_DIR.mkdir(parents=True, exist_ok=True)
FIXTURE_PATH = _GEN_DIR / "repeated_header_block.xlsx"


def _build_fixture() -> None:
    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Two submissions"
    header = ["Claim Reference", "Insured Name", "Claim Status", "Paid Amount", "Reserve Amount"]
    rows = [
        header,
        ["C-001", "Alice Ltd", "open", 100.0, 50.0],
        ["C-002", "Bob Co", "closed", 200.0, 0.0],
        [None, None, None, None, None],  # blank row between the two "monthly" blocks
        header,  # second submission's own header row, pasted mid-sheet
        ["C-003", "Carl Inc", "open", 300.0, 25.0],
        ["C-004", "Dana LLP", "reopened", 0.0, 400.0],
        [None, "Total", None, 600.0, None],  # trailing subtotal line
    ]
    for row in rows:
        ws.append(row)
    wb.save(FIXTURE_PATH)


def main() -> None:
    _build_fixture()
    sheets = pipeline.load_workbook(FIXTURE_PATH)
    assert len(sheets) == 1, f"expected 1 sheet, got {len(sheets)}"
    sheet = sheets[0]
    assert not sheet.skipped, f"sheet was unexpectedly skipped: {sheet.skip_reason}"

    real_refs = set(sheet.raw["Claim Reference"])
    assert real_refs == {"C-001", "C-002", "C-003", "C-004"}, \
        f"expected all 4 real claim rows from both blocks, got {real_refs}"
    assert len(sheet.raw) == 4, f"expected exactly 4 data rows, got {len(sheet.raw)}"

    reasons = {er.reason: er for er in sheet.excluded_rows}
    assert set(reasons) == {"blank", "repeated_header", "subtotal"}, \
        f"expected blank+repeated_header+subtotal exclusions, got {set(reasons)}"
    assert reasons["repeated_header"].values["Claim Reference"] == "Claim Reference", \
        "repeated header row's own values should be captured for drill-down"
    print(f"OK: 4 real rows ingested, 3 rows excluded ({sorted(reasons)}), "
          "none silently dropped, none miscounted as claims")

    proposals = pipeline.propose_mapping_for_workbook(sheets)
    confirmed = {
        p.sheet.sheet_name: {s.source_column: s.field_code for s in p.mapping.suggestions if s.field_code}
        for p in proposals
    }
    result = pipeline.run_workbook_pipeline(sheets, confirmed, proposals, source_name=FIXTURE_PATH.name)

    assert len(result.canonical) == 4, f"canonical should have exactly the 4 real claims, got {len(result.canonical)}"

    exceptions = result.validation_result.exceptions
    missing_mandatory = exceptions[exceptions["rule"] == "missing_mandatory_field"]
    assert missing_mandatory.empty, (
        "the repeated header row (or blank/subtotal rows) must be excluded BEFORE the "
        f"missing-mandatory-field check runs, not flagged by it -- got {missing_mandatory.to_dict('records')}"
    )
    print("OK: repeated header/blank/subtotal rows never reach the missing-mandatory-field check")

    coverage = result.coverage
    assert coverage.excluded_row_counts == {"blank": 1, "repeated_header": 1, "subtotal": 1}, \
        f"coverage should report exactly one of each exclusion reason, got {coverage.excluded_row_counts}"
    print(f"OK: coverage reports the exclusions by name/count: {coverage.excluded_row_counts}")

    print("\nRow-exclusion regression test PASSED.")


if __name__ == "__main__":
    main()
