"""Regression test for the "drag-and-drop an Excel file and get an error"
defect: load_workbook_sheets()/load_raw() previously routed every non-CSV
file through openpyxl regardless of extension, which raises
InvalidFileException on a real legacy .xls (openpyxl only reads the
zip/XML .xlsx/.xlsm container). Fixtures here are genuine binary formats,
not just renamed .xlsx files -- legacy_sample.xls is CDFV2/BIFF (written
with xlwt), macro_enabled_sample.xlsm is the same zip/XML container as
.xlsx with the macro-enabled extension."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from bordereaux.ingest import load_raw, load_workbook_sheets  # noqa: E402

FIXTURES = REPO_ROOT / "tests" / "fixtures"
EXPECTED_HEADERS = {"Claim Ref", "Insured Name", "Claim Status", "Date of Loss",
                     "Paid Amount", "Reserve Amount", "Currency"}


def check_file(path: Path, label: str) -> None:
    sheets = load_workbook_sheets(path)
    assert len(sheets) == 1, f"{label}: expected 1 sheet, got {len(sheets)}"
    sheet = sheets[0]
    assert not sheet.skipped, f"{label}: sheet was skipped ({sheet.skip_reason})"
    assert len(sheet.raw) == 2, f"{label}: expected 2 data rows, got {len(sheet.raw)}"
    assert set(sheet.raw.columns) == EXPECTED_HEADERS, f"{label}: unexpected columns {list(sheet.raw.columns)}"

    raw = load_raw(path)
    assert len(raw) == 2, f"{label} (load_raw): expected 2 rows, got {len(raw)}"
    print(f"{label}: OK -- {len(sheet.raw)} rows, header at row {sheet.header_row_index}")


def main() -> None:
    check_file(FIXTURES / "legacy_sample.xls", "legacy .xls (BIFF/CDFV2)")
    check_file(FIXTURES / "macro_enabled_sample.xlsm", "macro-enabled .xlsm")
    print("\nLegacy-format regression test PASSED.")


if __name__ == "__main__":
    main()
