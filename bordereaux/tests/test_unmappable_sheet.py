"""Regression test for fix spec Section 1: a sheet whose headers can't be
confidently mapped (e.g. all-French column names) must never be silently
excluded. It must still appear in the workbook coverage and mapping audit
trail, ingested with 0 (or few) fields mapped, rather than vanishing from
the sheet count with no error and no explanation.

Also covers 1.3: a sheet that raises while being read/scored must be
caught and reported by name, never allowed to abort the rest of the
workbook.
"""

from __future__ import annotations

import sys
from pathlib import Path

import openpyxl

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from bordereaux import ingest, pipeline, schema  # noqa: E402


def _build_workbook(tmp_path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sender A (English)"
    ws.append(["Claim Reference", "Insured Name", "Date of Loss", "Paid Amount",
               "Reserve Amount", "Incurred Amount"])
    ws.append(["CLM-001", "Acme Ltd", "2024-01-05", 1000, 500, 1500])
    ws.append(["CLM-002", "Beta Corp", "2024-02-10", 2000, 0, 2000])

    fr = wb.create_sheet("Sender B (French)")
    fr.append(["Référence du sinistre", "Nom de l'assuré", "Date du sinistre", "Montant payé",
               "Réserve", "Montant total"])
    fr.append(["SIN-001", "Société Dupont", "2024-01-05", 1200, 300, 1500])
    fr.append(["SIN-002", "Société Martin", "2024-02-10", 800, 200, 1000])

    other = wb.create_sheet("Sender C (English)")
    other.append(["Claim Reference", "Insured Name", "Date of Loss", "Paid Amount",
                   "Reserve Amount", "Incurred Amount"])
    other.append(["CLM-101", "Gamma LLC", "2024-03-01", 500, 500, 1000])

    path = tmp_path / "multi_lang.xlsx"
    wb.save(path)
    return path


def main() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = _build_workbook(Path(tmp))
        sheets = pipeline.load_workbook(path)

        assert len(sheets) == 3, f"expected 3 sheets, got {len(sheets)}"
        assert {s.sheet_name for s in sheets} == {
            "Sender A (English)", "Sender B (French)", "Sender C (English)",
        }

        fr_sheet = next(s for s in sheets if s.sheet_name == "Sender B (French)")
        # The core fix: the French sheet is NOT skipped. Its headers exist
        # and its rows are real, they just didn't match a known alias.
        assert not fr_sheet.skipped, f"French sheet was skipped: {fr_sheet.skip_reason}"
        assert fr_sheet.low_confidence_header, "French sheet should be flagged low-confidence"
        assert len(fr_sheet.raw) == 2, f"expected 2 data rows ingested, got {len(fr_sheet.raw)}"
        print("1.1/1.2 OK: non-English sheet was NOT dropped -- ingested with "
              f"{len(fr_sheet.raw)} rows, flagged low_confidence_header=True")

        proposals = pipeline.propose_mapping_for_workbook(sheets)
        assert len(proposals) == 3, f"expected a mapping proposal for all 3 sheets, got {len(proposals)}"
        fr_proposal = next(p for p in proposals if p.sheet.sheet_name == "Sender B (French)")
        mapped_codes = {s.field_code for s in fr_proposal.mapping.suggestions if s.field_code}
        # A cognate like "Réserve" fuzzy-matching "reserve" is a fine,
        # correct partial match -- the point of this fixture is that the
        # two REQUIRED fields (claim reference, insured name) don't have
        # an English-alias-matchable cognate and stay unmapped, so the
        # sheet is still visibly incomplete and needs manual review.
        assert schema.CLAIM_REF_CODE not in mapped_codes and schema.INSURED_NAME_CODE not in mapped_codes, (
            f"expected the required fields to stay unmapped on the French sheet, got {mapped_codes}"
        )
        assert len(mapped_codes) < len(schema.FIELDS), (
            f"French sheet mapped {len(mapped_codes)}/{len(schema.FIELDS)} fields -- "
            "fixture should still leave most fields unmapped"
        )
        print(f"1.2 OK: French sheet has its own mapping proposal in the audit trail, "
              f"only {len(mapped_codes)} of {len(schema.FIELDS)} fields mapped (required fields "
              "claim reference/insured name stay unmapped) -- exactly the 'needs manual review' "
              "outcome the report/coverage layer surfaces, never a silently-shrunk sheet count")

        confirmed = {
            p.sheet.sheet_name: {s.source_column: s.field_code for s in p.mapping.suggestions if s.field_code}
            for p in proposals
        }
        result = pipeline.run_workbook_pipeline(sheets, confirmed, proposals, source_name=path.name)

        assert result.coverage.sheets_total == 3
        assert result.coverage.sheets_processed == 3, (
            "the French sheet must count as processed (ingested, just poorly mapped), "
            f"not skipped -- got sheets_processed={result.coverage.sheets_processed}"
        )
        assert result.coverage.skipped_sheets == []
        french_rows = (result.canonical[schema.SOURCE_SHEET_CODE] == "Sender B (French)").sum()
        assert french_rows == 2, f"French sheet's 2 rows must still be in the canonical output, got {french_rows}"
        print(f"1.2/1.4 OK: coverage reports {result.coverage.sheets_processed}/{result.coverage.sheets_total} "
              f"sheets processed (the French sheet counts as processed, not skipped), and its "
              f"{french_rows} rows are present in the combined canonical output")

        fr_state = result.coverage.sheet_field_state["Sender B (French)"]
        assert fr_state[schema.CLAIM_REF_CODE] == "unmapped"
        assert fr_state[schema.INSURED_NAME_CODE] == "unmapped"
        # Deliberately NOT flagged as missing_mandatory_field: an
        # unmapped-on-this-sheet field is a mapping-completeness problem,
        # not "the user left this blank" -- conflating the two would
        # double-report the same root cause under the wrong label. The
        # per-sheet mapping state above is the visible, correct signal.
        exceptions = result.validation_result.exceptions
        mandatory_flagged_rows = set(exceptions.loc[exceptions["rule"] == "missing_mandatory_field", "row_index"])
        french_rows_idx = set(result.canonical.index[result.canonical[schema.SOURCE_SHEET_CODE] == "Sender B (French)"])
        assert not (mandatory_flagged_rows & french_rows_idx), (
            "an unmapped-on-this-sheet required field must not ALSO manufacture a "
            "missing_mandatory_field exception -- that's the mapping-completeness problem, "
            "reported once via sheet_field_state/coverage, not twice under a different label"
        )
        print("1.2 OK: sheet_field_state visibly names CR0104M/CR0035M as 'unmapped' on the "
              "French sheet (the per-sheet mapping-completeness signal), without also "
              "double-reporting it as a per-row missing-mandatory-field exception")

    print("\ntest_unmappable_sheet.py PASSED.")


def test_per_sheet_crash_is_isolated() -> None:
    """Fix spec 1.3: an exception while reading/scoring ONE sheet must be
    caught, logged with the sheet name and the real exception, and
    surfaced as a named failure for that sheet -- never allowed to
    propagate and abort the rest of the workbook."""
    import tempfile
    from unittest.mock import patch

    with tempfile.TemporaryDirectory() as tmp:
        path = _build_workbook(Path(tmp))

        real_build = ingest._build_sheet_data

        def _boom(name, rows):
            if name == "Sender B (French)":
                raise ValueError("simulated corrupt sheet data")
            return real_build(name, rows)

        with patch.object(ingest, "_build_sheet_data", side_effect=_boom):
            sheets = pipeline.load_workbook(path)

        assert len(sheets) == 3, f"a crash on one sheet must not drop the others from the result, got {len(sheets)}"
        crashed = next(s for s in sheets if s.sheet_name == "Sender B (French)")
        assert crashed.skipped, "the crashed sheet must be marked skipped, not silently half-processed"
        assert "simulated corrupt sheet data" in (crashed.skip_reason or ""), (
            f"skip_reason should name the actual exception, got: {crashed.skip_reason!r}"
        )
        others = [s for s in sheets if s.sheet_name != "Sender B (French)"]
        assert all(not s.skipped for s in others), "other sheets must process normally despite the crash"
        assert all(len(s.raw) > 0 for s in others)
        print("1.3 OK: an exception reading one sheet is caught, named ('simulated corrupt "
              "sheet data'), and reported as that sheet's own skip_reason -- the other 2 "
              "sheets in the same workbook still processed normally, not aborted")

    print("\ntest_unmappable_sheet.py (crash isolation) PASSED.")


if __name__ == "__main__":
    main()
    test_per_sheet_crash_is_isolated()
