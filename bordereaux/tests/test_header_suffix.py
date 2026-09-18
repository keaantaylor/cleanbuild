"""Regression test for the "parenthetical suffix breaks alias matching"
defect: a header like "Paid to Date (GBP)" scored just under
FUZZY_THRESHOLD against its own alias ("paid to date") because the
"(GBP)" suffix dragged the token_sort_ratio down, so real monetary
columns went unmapped and every arithmetic check on that sheet came back
"not evaluable" -- reported as a data problem when it was an ingestion
defect. Covers a full sheet (every monetary column suffixed, not one
header in isolation) plus the currency-hint population when the sheet
has no separate Currency column."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import openpyxl  # noqa: E402

from bordereaux import pipeline  # noqa: E402

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "suffixed_headers.xlsx"


def _build_fixture() -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["Claim Ref", "Insured Name", "Paid to Date (GBP)", "Reserve Amount (GBP)", "Incurred Amount (GBP)"])
    ws.append(["C1", "Alice Ltd", 100.0, 50.0, 150.0])
    ws.append(["C2", "Bob Co", 200.0, 0.0, 200.0])
    ws.append(["C3", "Carl Inc", 300.0, 25.0, 325.0])
    wb.save(FIXTURE)


def main() -> None:
    _build_fixture()
    sheets = pipeline.load_workbook(FIXTURE)
    proposals = pipeline.propose_mapping_for_workbook(sheets)
    proposal = proposals[0]

    mapped = {s.source_column: s.field_code for s in proposal.mapping.suggestions if s.field_code}
    assert len(mapped) == 5, f"every suffixed header should still alias-match, got {mapped}"
    print(f"OK: all 5 suffixed headers mapped: {mapped}")

    confirmed = {"Sheet1": mapped}
    result = pipeline.run_workbook_pipeline(sheets, confirmed, proposals, source_name=FIXTURE.name)

    canonical = result.canonical
    assert canonical["CR0126CM"].notna().all(), "Paid amounts must all parse despite the (GBP) suffix"
    assert canonical["CR0130CM"].notna().all(), "Reserve amounts must all parse despite the (GBP) suffix"
    assert canonical["CR0155CM"].notna().all(), "Incurred amounts must all parse despite the (GBP) suffix"
    assert (canonical["CR0110CM"] == "GBP").all(), (
        f"currency should be populated from the header hint since no Currency column exists, "
        f"got {canonical['CR0110CM'].tolist()}"
    )
    print("OK: all monetary columns parsed correctly, currency populated from the header hint")

    assert result.health.arithmetic_not_evaluable == 0, (
        f"no row should be not-evaluable -- every input mapped and parsed cleanly, "
        f"got {result.health.arithmetic_not_evaluable}"
    )
    assert result.health.arithmetic_mismatches == 0, "paid+reserve==incurred on every row of this fixture"
    print("OK: arithmetic reconciliation runs cleanly -- previously this whole sheet came back not-evaluable")

    print("\nHeader-suffix regression test PASSED.")


if __name__ == "__main__":
    main()
