"""Phase 5 acceptance check: the health report's numbers are internally
consistent and both output artifacts (Excel detail + PDF one-pager) are
produced. (The actual "a stranger understands it in under two minutes"
bar was checked by eye against the rendered PDF.)"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from bordereaux import schema, pipeline  # noqa: E402
import process_file  # noqa: E402


def check_sender(sender: str) -> None:
    path, mapping = process_file.HARD_CODED_MAPPINGS[sender]
    result = pipeline.process_path(path, mapping)
    h = result.health

    assert 1 <= h.grade <= 5
    assert h.grade_label
    assert h.total_claims == len(result.canonical)
    assert len(h.field_completeness) == len(schema.FIELDS)
    assert all(fs.never_mapped or 0.0 <= fs.pct <= 100.0 for fs in h.field_completeness)
    assert h.arithmetic_mismatches == int((result.exceptions["rule"] == "arithmetic_mismatch").sum())
    assert h.exact_duplicates == int((result.duplicates["match_type"] == "exact_duplicate").sum())

    out_dir = REPO_ROOT / "data" / "output"
    paths = pipeline.write_outputs(result, out_dir, path.stem)
    assert paths["health"].exists() and paths["health"].stat().st_size > 0
    assert paths["health_pdf"].exists() and paths["health_pdf"].stat().st_size > 1000

    import pandas as pd
    xl = pd.ExcelFile(paths["health"])
    for expected_sheet in ["Summary", "Field completeness", "Exceptions", "Possible duplicates", "Full data"]:
        assert expected_sheet in xl.sheet_names, f"missing sheet {expected_sheet}"

    print(f"sender {sender}: grade {h.grade}/5 ({h.grade_label}), "
          f"outputs at {paths['health']} and {paths['health_pdf']}")


def main() -> None:
    for sender in ["a", "b", "c", "d"]:
        check_sender(sender)
    print("\nPhase 5 acceptance check PASSED for all senders.")


if __name__ == "__main__":
    main()
