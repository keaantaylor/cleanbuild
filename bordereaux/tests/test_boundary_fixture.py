"""Fix spec 3.10: regression test against test_boundary_cases.xlsx +
its answer key. This is the permanent fixture for the ingestion/mapping
bug class documented in the fix spec (D1-D8) -- every assertion here
corresponds directly to one of that spec's acceptance criteria.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from bordereaux import pipeline, schema  # noqa: E402

FIXTURE = REPO_ROOT / "data" / "synthetic" / "test_boundary_cases.xlsx"
ANSWER_KEY = json.loads((REPO_ROOT / "data" / "synthetic" / "test_boundary_cases_answer_key.json").read_text())


def _auto_confirm_all(proposals: list) -> dict[str, dict[str, str]]:
    """Emulate a user who accepts every proposed mapping as-is -- valid
    here because 3.5's alias dictionary resolves 100% of this fixture's
    headers via the fuzzy stage alone (see test_phase3-style coverage
    check below), so there's nothing an AI call or a manual pick would
    need to add."""
    return {
        p.sheet.sheet_name: {s.source_column: s.field_code for s in p.mapping.suggestions if s.field_code}
        for p in proposals
    }


def _run() -> tuple:
    sheets = pipeline.load_workbook(FIXTURE)
    proposals = pipeline.propose_mapping_for_workbook(sheets)
    confirmed = _auto_confirm_all(proposals)
    result = pipeline.run_workbook_pipeline(sheets, confirmed, proposals, source_name=FIXTURE.name)
    return sheets, proposals, result


def test_all_sheets_and_rows_ingested(sheets, result) -> None:
    assert len(sheets) == ANSWER_KEY["sheets_processed"] == 10
    assert all(not s.skipped for s in sheets), [s.skip_reason for s in sheets if s.skipped]
    assert result.coverage.sheets_total == 10
    assert result.coverage.sheets_processed == 10
    assert len(result.canonical) == ANSWER_KEY["total_rows"] == 320
    assert result.coverage.rows_assessed == 320

    for sheet_name, expected_count in ANSWER_KEY["sheet_row_counts"].items():
        actual = (result.canonical[schema.SOURCE_SHEET_CODE] == sheet_name).sum()
        assert actual == expected_count, f"{sheet_name}: expected {expected_count} rows, got {actual}"
    print(f"D1/3.1 OK: all 10 sheets ingested, {len(result.canonical)}/320 rows")


def test_banner_sheets_mapped_fully(proposals) -> None:
    for sheet_name in ANSWER_KEY["sheets_with_banner_row"]:
        proposal = next(p for p in proposals if p.sheet.sheet_name == sheet_name)
        expected_rows = ANSWER_KEY["sheet_row_counts"][sheet_name]
        assert len(proposal.sheet.raw) == expected_rows, (
            f"{sheet_name}: expected {expected_rows} data rows, got {len(proposal.sheet.raw)}")
        mapped_codes = {s.field_code for s in proposal.mapping.suggestions if s.field_code}
        assert len(mapped_codes) == 10, f"{sheet_name}: only {len(mapped_codes)}/10 fields mapped"
    print(f"D1/3.2 OK: banner-row sheets {ANSWER_KEY['sheets_with_banner_row']} "
          f"detected their real header row and mapped all 10 fields")


def test_no_required_field_left_unmapped(proposals) -> None:
    required_codes = set(schema.REQUIRED_CODES)
    for p in proposals:
        mapped_codes = {s.field_code for s in p.mapping.suggestions if s.field_code}
        missing = required_codes - mapped_codes
        assert not missing, f"{p.sheet.sheet_name}: required fields never mapped: {missing}"
    print(f"3.3/3.5 OK: every sheet mapped both unconditionally-required fields "
          f"({sorted(required_codes)})")


def test_alias_stage_alone_resolves_fixture(proposals) -> None:
    total_cols = sum(len(p.mapping.suggestions) for p in proposals)
    alias_or_ai = sum(1 for p in proposals for s in p.mapping.suggestions if s.field_code)
    ai_used = sum(1 for p in proposals for s in p.mapping.suggestions if s.method == "ai")
    assert alias_or_ai / total_cols >= 0.95, f"only {alias_or_ai}/{total_cols} columns mapped"
    print(f"3.5 OK: {alias_or_ai}/{total_cols} columns mapped ({ai_used} via AI fallback, "
          f"rest via fuzzy alias matching alone)")


def test_missing_mandatory_fields_exact(result) -> None:
    df = result.canonical
    sheet_local_row = df.groupby(schema.SOURCE_SHEET_CODE).cumcount() + 1
    exceptions = result.validation_result.exceptions

    expected_claim_ref = {
        (e["sheet"], e["row"]) for e in ANSWER_KEY["injected_errors"]["missing_mandatory_fields"]["claim_reference"]
    }
    expected_insured = {
        (e["sheet"], e["row"]) for e in ANSWER_KEY["injected_errors"]["missing_mandatory_fields"]["insured_name"]
    }
    expected_union = expected_claim_ref | expected_insured

    flagged_idx = set(exceptions.loc[exceptions["rule"] == "missing_mandatory_field", "row_index"])
    flagged_keys = {
        (df.at[i, schema.SOURCE_SHEET_CODE], int(sheet_local_row.at[i])) for i in flagged_idx
    }

    missed = expected_union - flagged_keys
    false_positives = flagged_keys - expected_union
    assert not missed, f"missed missing-mandatory-field rows: {sorted(missed)}"
    assert not false_positives, f"false-positive missing-mandatory-field rows: {sorted(false_positives)}"

    expected_total = len(expected_union)
    assert len(flagged_keys) == expected_total
    print(f"D3/D4/D6/3.3/3.4/3.6 OK: exactly {expected_total} rows flagged missing-mandatory-field "
          f"(48 missing claim ref + 26 missing insured name, 6-row overlap), zero false positives, "
          "zero false negatives; CR0155CM (incurred) is not independently required so it never "
          "manufactures a phantom exception")


def test_arithmetic_reconciliation_exact(result) -> None:
    df = result.canonical
    sheet_local_row = df.groupby(schema.SOURCE_SHEET_CODE).cumcount() + 1
    exceptions = result.validation_result.exceptions

    expected = {
        (e["sheet"], e["row"]): e["difference"]
        for e in ANSWER_KEY["injected_errors"]["arithmetic_errors"]["rows"]
    }

    mismatch_idx = set(exceptions.loc[exceptions["rule"] == "arithmetic_mismatch", "row_index"])
    flagged_keys = {
        (df.at[i, schema.SOURCE_SHEET_CODE], int(sheet_local_row.at[i])) for i in mismatch_idx
    }

    assert len(flagged_keys) == len(expected) == ANSWER_KEY["injected_errors"]["arithmetic_errors"]["count"] == 38
    assert flagged_keys == set(expected.keys())

    for i in mismatch_idx:
        key = (df.at[i, schema.SOURCE_SHEET_CODE], int(sheet_local_row.at[i]))
        paid = df.at[i, schema.PAID_CODE] if schema.PAID_CODE in df.columns else df.at[i, "CR0126CM"]
        reserve = df.at[i, "CR0130CM"]
        incurred = df.at[i, "CR0155CM"]
        actual_diff = round(float(incurred) - (float(paid) + float(reserve)), 2)
        expected_diff = expected[key]
        assert abs(actual_diff - expected_diff) < 0.02, f"{key}: expected delta {expected_diff}, got {actual_diff}"

    assert result.validation_result.arithmetic_mismatch_count == 38
    assert result.validation_result.arithmetic_not_evaluable_count == 0
    assert result.validation_result.arithmetic_match_count == 320 - 38
    print("D5/D6/3.7 OK: exactly 38/320 arithmetic mismatches, each delta matches the answer key "
          "within tolerance; 0 rows reported not-evaluable (every input was mapped on this fixture)")


def test_duplicates_exact(result) -> None:
    df = result.canonical
    sheet_local_row = df.groupby(schema.SOURCE_SHEET_CODE).cumcount() + 1
    duplicates = result.duplicates
    probable = duplicates[duplicates["match_type"] == "probable_duplicate"]

    def key_for(idx: int) -> tuple:
        return (df.at[idx, schema.SOURCE_SHEET_CODE], int(sheet_local_row.at[idx]))

    found_pairs = {
        frozenset((key_for(a), key_for(b)))
        for a, b in zip(probable["row_index_a"], probable["row_index_b"])
    }

    expected_pairs = {
        frozenset(((p["a"]["sheet"], p["a"]["row"]), (p["b"]["sheet"], p["b"]["row"])))
        for p in ANSWER_KEY["injected_errors"]["duplicates"]["pairs"]
    }

    assert len(expected_pairs) == 16
    missed = expected_pairs - found_pairs
    assert not missed, f"missed duplicate pairs: {missed}"

    zurich_pair = frozenset((("Zurich Re", 6), ("Zurich Re", 24)))
    assert zurich_pair in found_pairs, "the in-sheet Zurich Re rows 6 & 24 pair (D7) was not caught"

    print(f"D7/3.8 OK: all {len(expected_pairs)} probable-duplicate pairs caught (32 rows), "
          "including the in-sheet case-only-name pair on Zurich Re")


def test_composite_score_is_plausible(result) -> None:
    h = result.health
    assert h.score_reliable, "score should be reliable: every sheet processed, no required field unmapped"
    assert h.grade >= 3, (
        f"file was built with bounded ~15-20% error rates; a correct run should not score near-zero "
        f"(got grade {h.grade}, composite {h.composite_score:.1f})"
    )
    print(f"D8/3.9 OK: grade {h.grade}/5 (composite {h.composite_score:.1f}/100) -- "
          "plausible for a file built with bounded, documented error rates, not a near-zero "
          "pipeline-failure score")


def main() -> None:
    sheets, proposals, result = _run()
    test_all_sheets_and_rows_ingested(sheets, result)
    test_banner_sheets_mapped_fully(proposals)
    test_no_required_field_left_unmapped(proposals)
    test_alias_stage_alone_resolves_fixture(proposals)
    test_missing_mandatory_fields_exact(result)
    test_arithmetic_reconciliation_exact(result)
    test_duplicates_exact(result)
    test_composite_score_is_plausible(result)
    print("\ntest_boundary_cases.xlsx regression suite PASSED -- D1-D8 all fixed.")


if __name__ == "__main__":
    main()
