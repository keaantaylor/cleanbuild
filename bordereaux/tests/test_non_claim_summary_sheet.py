"""TB-001 regression: a sheet binding only monetary columns (a per-sheet
dashboard/summary tab, no claim reference, no insured name + date) must
never be emitted as claims. Reproduces the headline defect: a 3x
overstatement because a workbook's Dashboard tab -- three per-sheet
subtotal rows plus a grand total -- was previously counted as four
claims worth twice the real book."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import openpyxl  # noqa: E402
import pandas as pd  # noqa: E402

from bordereaux import ingest, pipeline  # noqa: E402
from bordereaux.mapping import build_mapping  # noqa: E402

# Generated fixtures go to a temp dir: tests must never rewrite tracked files.
import tempfile  # noqa: E402

FIXTURE_DIR = Path(tempfile.gettempdir()) / "truebind_generated_fixtures"
FIXTURE_DIR.mkdir(parents=True, exist_ok=True)


def _build_dashboard_fixture() -> Path:
    path = FIXTURE_DIR / "dashboard_summary.xlsx"
    wb = openpyxl.Workbook()

    dash = wb.active
    dash.title = "Dashboard"
    dash.append(["Sheet", "Paid Amount", "Reserve Amount", "Incurred Amount"])
    dash.append(["Direct_GBP", 500000.00, 100000.00, 600000.00])
    dash.append(["Direct_EUR", 300000.00, 50000.00, 350000.00])
    dash.append(["TOTAL", 800000.00, 150000.00, 950000.00])

    claims = wb.create_sheet("Direct_GBP")
    claims.append(["Claim Ref", "Insured Name", "Paid Amount", "Reserve Amount", "Incurred Amount"])
    for i in range(10):
        claims.append([f"CLM-{i + 1:04d}", f"Insured {i}", 50000.00, 10000.00, 60000.00])

    wb.save(path)
    return path


def test_dashboard_sheet_excluded_from_claims_and_named_in_report() -> None:
    path = _build_dashboard_fixture()
    sheets = ingest.load_workbook_sheets(path)
    proposals = pipeline.propose_mapping_for_workbook(sheets)
    confirmed = {p.sheet.sheet_name: {s.source_column: s.field_code
                                       for s in p.mapping.suggestions if s.field_code}
                 for p in proposals}

    result = pipeline.run_workbook_pipeline(sheets, confirmed, proposals, source_name="dashboard_summary.xlsx")

    assert "Dashboard" in result.coverage.non_claim_summary_sheets, (
        f"Dashboard should be recognised as a non-claim summary sheet; got {result.coverage.non_claim_summary_sheets}"
    )
    assert len(result.canonical) == 10, f"expected exactly 10 real claim rows, got {len(result.canonical)}"
    assert result.canonical["TB_PAID_TD"].sum() == 500000.00, (
        f"paid total must reflect only the real claims sheet, got {result.canonical['TB_PAID_TD'].sum()}"
    )

    rec = result.coverage.reconciliation
    # All 3 Dashboard rows (2 per-sheet rollups + the grand TOTAL) are
    # fully populated, not majority-blank -- the existing subtotal-row
    # filter (TB-007) is for a mostly-blank line with just a total label,
    # which this isn't, so all 3 land in non_claim_summary_rows via
    # sheet-level classification instead.
    # The dashboard's own "TOTAL" line is a structural row (total label
    # followed only by numbers) and is excluded with that reason; the two
    # per-sheet rollup lines land in non_claim_summary_rows. Source rows
    # still reconcile exactly (2 + 1 + 10 claims).
    assert rec.non_claim_summary_rows == 2, f"expected 2, got {rec.non_claim_summary_rows}"
    assert rec.rejected_rows == 1, f"expected 1 (the TOTAL line), got {rec.rejected_rows}"
    assert rec.reconciles, f"reconciliation must still balance: {rec.as_lines()}"
    assert result.coverage.fully_covered, "excluding a recognised summary sheet must not look like incomplete coverage"
    assert result.health.score_reliable, "a correctly-excluded summary sheet must not degrade score reliability"
    print(f"OK: Dashboard excluded ({rec.non_claim_summary_rows} rows); "
          f"10 real claims, paid total {result.canonical['TB_PAID_TD'].sum()}; reconciliation balances")


if __name__ == "__main__":
    test_dashboard_sheet_excluded_from_claims_and_named_in_report()
    print("\nNon-claim-summary-sheet regression test PASSED.")
