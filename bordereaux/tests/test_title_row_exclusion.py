"""TB-007b regression: a section banner embedded mid-sheet ("Table B —
GBP claims", "UNDERWRITING YEAR 2023") must be excluded from the claim
set like any other structural row, not emitted as a claim with every
field but one blank. The existing subtotal filter only catches a row
naming a total/sum explicitly; a bare title has no such wording, only
the shape of a lone populated cell."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import openpyxl  # noqa: E402

from bordereaux import ingest  # noqa: E402

FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures"


def _build_title_row_fixture() -> Path:
    path = FIXTURE_DIR / "title_row.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Table_B"
    ws.append(["Claim Ref", "Insured Name", "Paid Amount", "Reserve Amount", "Incurred Amount"])
    ws.append(["CLM-0001", "Alice Ltd", 100.0, 50.0, 150.0])
    ws.append(["Table B — GBP claims"])  # lone banner cell, everything else blank
    ws.append(["CLM-0002", "Bob Co", 200.0, 25.0, 225.0])
    ws.append(["UNDERWRITING YEAR 2023"])
    ws.append(["CLM-0003", "Carl Inc", 300.0, 0.0, 300.0])
    wb.save(path)
    return path


def test_title_banner_rows_excluded_not_emitted_as_claims() -> None:
    path = _build_title_row_fixture()
    sheets = ingest.load_workbook_sheets(path)
    assert len(sheets) == 1
    sheet = sheets[0]
    assert not sheet.skipped

    assert len(sheet.raw) == 3, f"expected 3 real claim rows, got {len(sheet.raw)}"
    refs = set(sheet.raw["Claim Ref"])
    assert refs == {"CLM-0001", "CLM-0002", "CLM-0003"}

    title_exclusions = [er for er in sheet.excluded_rows if er.reason == "title"]
    assert len(title_exclusions) == 2, f"expected 2 title rows excluded, got {len(title_exclusions)}"
    print(f"OK: {len(sheet.raw)} real claims kept; {len(title_exclusions)} banner rows excluded and named")


if __name__ == "__main__":
    test_title_banner_rows_excluded_not_emitted_as_claims()
    print("\nTitle-row-exclusion regression test PASSED.")
