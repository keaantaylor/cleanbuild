"""Phase 4 acceptance test: every deliberately-injected duplicate/near-
duplicate from the Phase 1 answer key must be caught, with no more than
one false positive per file."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from bordereaux import dedupe, ingest  # noqa: E402
import process_file  # noqa: E402

ANSWER_KEY = json.loads((REPO_ROOT / "data" / "synthetic" / "answer_key.json").read_text())

FILE_BY_SENDER = {
    "a": "sender_a_sedgwick.csv",
    "b": "sender_b_crawford.xlsx",
    "c": "sender_c_blackrock.xlsx",
    "d": "sender_d_mx_underwriting.xlsx",
}


def check_sender(sender: str) -> None:
    path, mapping = process_file.HARD_CODED_MAPPINGS[sender]
    raw = ingest.load_raw(path)
    canonical = ingest.apply_mapping(raw, mapping)
    dups = dedupe.find_duplicates(canonical)

    answer = ANSWER_KEY[FILE_BY_SENDER[sender]]
    expected_exact = {e["claim_ref"] for e in answer if e["type"] == "exact_duplicate"}
    expected_near = [tuple(sorted(e["claim_ref"])) for e in answer if e["type"] == "near_duplicate"]

    exact_found = dups[dups["match_type"] == "exact_duplicate"]
    found_exact_refs = set(exact_found["claim_ref_a"]) | set(exact_found["claim_ref_b"])
    missed_exact = expected_exact - found_exact_refs
    assert not missed_exact, f"sender {sender}: missed exact duplicates {missed_exact}"

    probable = dups[dups["match_type"] == "probable_duplicate"]
    found_pairs = {tuple(sorted((a, b))) for a, b in zip(probable["claim_ref_a"], probable["claim_ref_b"])}
    missed_near = [p for p in expected_near if p not in found_pairs]
    assert not missed_near, f"sender {sender}: missed near-duplicate pairs {missed_near}"

    false_positives = found_pairs - set(expected_near)
    assert len(false_positives) <= 1, (
        f"sender {sender}: {len(false_positives)} false-positive probable duplicates "
        f"(max 1 allowed): {false_positives}"
    )

    print(f"sender {sender}: OK — {len(expected_exact)}/{len(expected_exact)} exact dupes caught, "
          f"{len(expected_near)}/{len(expected_near)} near-dupe pairs caught, "
          f"{len(false_positives)} false positives")


def main() -> None:
    for sender in ["a", "b", "c", "d"]:
        check_sender(sender)
    print("\nPhase 4 acceptance test PASSED for all senders.")


if __name__ == "__main__":
    main()
