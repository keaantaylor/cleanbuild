"""Phase 2 acceptance test: running process_file.py on a Phase 1 file
must produce a segregated export and catch every deliberately-injected
arithmetic/missing-mandatory-field error from the answer key."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import process_file  # noqa: E402

ANSWER_KEY = json.loads((REPO_ROOT / "data" / "synthetic" / "answer_key.json").read_text())

FILE_BY_SENDER = {
    "a": "sender_a_sedgwick.csv",
    "b": "sender_b_crawford.xlsx",
    "c": "sender_c_blackrock.xlsx",
    "d": "sender_d_mx_underwriting.xlsx",
}


# Fix spec 3.6 narrowed unconditional requiredness to just claim reference
# and insured name (status/dates/policy ref are validated when present,
# not flagged when absent). Phase 1's injections target insured/policy_ref/
# status/notified_date; only the "insured" ones are still expected to
# raise a missing_mandatory_field exception under the current taxonomy.
STILL_REQUIRED_TARGET_FIELDS = {"insured"}


def check_sender(sender: str) -> None:
    canonical, exceptions, out_path = process_file.process(sender)
    answer = ANSWER_KEY[FILE_BY_SENDER[sender]]

    expected_arith = {e["claim_ref"] for e in answer if e["type"] == "arithmetic_mismatch"}
    expected_missing = {
        e["claim_ref"] for e in answer
        if e["type"] == "missing_mandatory_field" and e.get("field") in STILL_REQUIRED_TARGET_FIELDS
    }

    found_arith = set(exceptions.loc[exceptions["rule"] == "arithmetic_mismatch", "claim_ref"])
    found_missing = set(exceptions.loc[exceptions["rule"] == "missing_mandatory_field", "claim_ref"])

    missed_arith = expected_arith - found_arith
    missed_missing = expected_missing - found_missing

    assert not missed_arith, f"sender {sender}: missed arithmetic errors {missed_arith}"
    assert not missed_missing, f"sender {sender}: missed missing-field errors {missed_missing}"
    assert out_path.exists(), f"sender {sender}: segregated export not written"

    print(f"sender {sender}: OK — {len(canonical)} rows, "
          f"{len(expected_arith)}/{len(expected_arith)} arithmetic errors caught, "
          f"{len(expected_missing)}/{len(expected_missing)} missing-field errors caught")


def main() -> None:
    for sender in ["a", "b", "c", "d"]:
        check_sender(sender)
    print("\nPhase 2 acceptance test PASSED for all senders.")


if __name__ == "__main__":
    main()
