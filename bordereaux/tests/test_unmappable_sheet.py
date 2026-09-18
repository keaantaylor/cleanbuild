"""Regression test: a sheet whose headers can't be confidently mapped
(a foreign-language layout, an unrecognized terminology) must never be
silently dropped. It must still appear in sheets_total/coverage and be
processed through the normal mapping flow with every field UNMAPPED --
distinct from a genuinely non-data sheet (a notes/cover tab), which is
still correctly skipped. Also covers per-sheet crash isolation: an
exception reading one sheet must never abort the rest of the workbook."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import openpyxl  # noqa: E402

import bordereaux.ingest as ingest  # noqa: E402
from bordereaux import pipeline  # noqa: E402

FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures"


def _build_french_fixture() -> Path:
    path = FIXTURE_DIR / "french_and_english.xlsx"
    wb = openpyxl.Workbook()
    en = wb.active
    en.title = "English"
    en.append(["Claim Ref", "Insured Name", "Paid Amount", "Reserve Amount"])
    en.append(["C1", "Alice Ltd", 100.0, 50.0])
    en.append(["C2", "Bob Co", 200.0, 25.0])

    fr = wb.create_sheet("French")
    fr.append(["Référence de réclamation", "Nom de l'assuré", "Montant payé", "Montant de réserve"])
    fr.append(["C3", "Carl SARL", 300.0, 75.0])
    fr.append(["C4", "Dana SA", 400.0, 0.0])

    wb.save(path)
    return path


def _build_notes_fixture() -> Path:
    path = FIXTURE_DIR / "data_and_notes.xlsx"
    wb = openpyxl.Workbook()
    data = wb.active
    data.title = "Data"
    data.append(["Claim Ref", "Insured Name", "Paid Amount", "Reserve Amount"])
    data.append(["C1", "Alice Ltd", 100.0, 50.0])

    notes = wb.create_sheet("Notes")
    notes.append(["Please see the Data tab for full figures. Contact accounts@example.com."])

    wb.save(path)
    return path


def test_foreign_language_sheet_never_silently_dropped() -> None:
    path = _build_french_fixture()
    sheets = pipeline.load_workbook(path)

    assert len(sheets) == 2, f"both sheets must appear, got {len(sheets)}"
    by_name = {s.sheet_name: s for s in sheets}
    assert not by_name["French"].skipped, (
        f"a sheet with unmappable (foreign-language) headers must not be skipped, "
        f"got skip_reason={by_name['French'].skip_reason!r}"
    )
    assert len(by_name["French"].raw) == 2, "both French data rows must be ingested"

    proposals = pipeline.propose_mapping_for_workbook(sheets)
    by_sheet_name = {p.sheet.sheet_name: p for p in proposals}
    french_mapped = sum(1 for s in by_sheet_name["French"].mapping.suggestions if s.field_code)
    assert french_mapped == 0, f"no French header should alias-match an English field, got {french_mapped}"
    english_mapped = sum(1 for s in by_sheet_name["English"].mapping.suggestions if s.field_code)
    assert english_mapped == 4, f"the English sheet's mapping must be unaffected, got {english_mapped}"

    confirmed = {"English": {s.source_column: s.field_code for s in by_sheet_name["English"].mapping.suggestions if s.field_code},
                 "French": {}}  # simulates a user who hasn't manually mapped it yet
    result = pipeline.run_workbook_pipeline(sheets, confirmed, proposals, source_name=path.name)

    assert result.coverage.sheets_total == 2
    assert result.coverage.sheets_processed == 2, "the French sheet must count as processed, not skipped"
    assert result.coverage.skipped_sheets == [], "nothing should be in skipped_sheets"
    assert len(result.canonical) == 4, "all 4 rows (2 English + 2 French) must reach the canonical output"
    print("OK: foreign-language sheet processed with 0 fields mapped, never silently dropped")


def test_genuine_notes_sheet_still_skipped() -> None:
    path = _build_notes_fixture()
    sheets = pipeline.load_workbook(path)
    by_name = {s.sheet_name: s for s in sheets}

    assert not by_name["Data"].skipped
    assert by_name["Notes"].skipped, "a genuine non-tabular notes sheet must still be recognized and skipped"
    print("OK: genuine notes/cover sheet is still correctly skipped, not treated as unmapped data")


def test_per_sheet_crash_is_isolated(monkeypatch) -> None:
    original = ingest._build_sheet_data

    def _boom(name, rows):
        if name == "Corrupt":
            raise ValueError("simulated corruption")
        return original(name, rows)

    monkeypatch.setattr(ingest, "_build_sheet_data", _boom)

    path = FIXTURE_DIR / "crash_isolation.xlsx"
    wb = openpyxl.Workbook()
    good = wb.active
    good.title = "Good"
    good.append(["Claim Ref", "Insured Name", "Paid Amount", "Reserve Amount"])
    good.append(["C1", "Alice Ltd", 100.0, 50.0])
    bad = wb.create_sheet("Corrupt")
    bad.append(["Claim Ref", "Insured Name", "Paid Amount", "Reserve Amount"])
    bad.append(["C2", "Bob Co", 200.0, 25.0])
    wb.save(path)

    sheets = ingest.load_workbook_sheets(path)
    by_name = {s.sheet_name: s for s in sheets}

    assert len(sheets) == 2, "the crashing sheet must not take the whole workbook down"
    assert not by_name["Good"].skipped
    assert by_name["Corrupt"].skipped
    assert "simulated corruption" in (by_name["Corrupt"].skip_reason or ""), (
        "the actual exception must be named, not swallowed generically"
    )
    print("OK: a crash reading one sheet is isolated, named, and never aborts the rest of the workbook")


if __name__ == "__main__":
    test_foreign_language_sheet_never_silently_dropped()
    test_genuine_notes_sheet_still_skipped()

    class _FakeMonkeypatch:
        def setattr(self, obj, name, value):
            setattr(obj, name, value)

    test_per_sheet_crash_is_isolated(_FakeMonkeypatch())
    print("\nUnmappable-sheet regression tests PASSED.")
