"""Truebind 2.1 acceptance test: the payment-leakage detector finds
exactly the engineered CERTAIN/PROBABLE/POSSIBLE case in
leakage_fixture.csv, and flags none of the three negative cases (amount
outside tolerance, different payee, outside the wide date window)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from bordereaux import ingest, leakage  # noqa: E402

FIXTURE = REPO_ROOT / "data" / "synthetic" / "leakage_fixture.csv"
ANSWER_KEY = json.loads((REPO_ROOT / "data" / "synthetic" / "leakage_fixture_answer_key.json").read_text())

MAPPING = {
    "Claim Ref": "CR0104M", "Status": "CR0105CM", "Loss Date": "CR0119CM",
    "Notification Date": "CR0136CM", "Insured": "CR0035M", "Policy Ref": "CR0029M",
    "Paid": "CR0126CM", "Reserve": "CR0130CM", "Incurred": "CR0155CM", "Currency": "CR0110CM",
}


def main() -> None:
    raw = ingest.load_raw(FIXTURE)
    canonical = ingest.apply_mapping(raw, MAPPING)
    assert len(canonical) == ANSWER_KEY["total_rows"] == 32

    flags = leakage.find_leakage(canonical)
    tier_counts = flags["confidence"].value_counts().to_dict() if not flags.empty else {}
    expected_counts = ANSWER_KEY["expected_flag_count"]

    for tier, expected in expected_counts.items():
        actual = tier_counts.get(tier, 0)
        assert actual == expected, f"{tier}: expected {expected} flags, got {actual} ({tier_counts})"

    total_flags = sum(tier_counts.values())
    assert total_flags == sum(expected_counts.values()), (
        f"expected exactly {sum(expected_counts.values())} total flags, got {total_flags}: "
        f"{flags[['confidence', 'claim_ref_a', 'claim_ref_b']].to_dict('records')}"
    )

    certain_case = ANSWER_KEY["cases"]["certain"]
    certain_rows = flags[flags["confidence"] == "CERTAIN"]
    assert (certain_rows["claim_ref_a"] == certain_case["claim_ref"]).all()

    probable_case = ANSWER_KEY["cases"]["probable"]
    probable_rows = flags[flags["confidence"] == "PROBABLE"]
    probable_refs = set(probable_rows["claim_ref_a"]) | set(probable_rows["claim_ref_b"])
    assert probable_refs == {probable_case["claim_ref_a"], probable_case["claim_ref_b"]}

    possible_case = ANSWER_KEY["cases"]["possible"]
    possible_rows = flags[flags["confidence"] == "POSSIBLE"]
    possible_refs = set(possible_rows["claim_ref_a"]) | set(possible_rows["claim_ref_b"])
    assert possible_refs == {possible_case["claim_ref_a"], possible_case["claim_ref_b"]}

    flagged_refs = set(flags["claim_ref_a"]) | set(flags["claim_ref_b"])
    for neg in ANSWER_KEY["negative_cases"]:
        assert neg["claim_ref_a"] not in flagged_refs or neg["claim_ref_b"] not in flagged_refs, (
            f"false positive: {neg['claim_ref_a']}/{neg['claim_ref_b']} should not be flagged "
            f"({neg['reason']})"
        )

    exposure = leakage.total_exposure(flags)
    certain_amount = flags.loc[flags["confidence"] == "CERTAIN", "amount_exposure"].sum()
    probable_amount = flags.loc[flags["confidence"] == "PROBABLE", "amount_exposure"].sum()
    expected_exposure = certain_amount + probable_amount
    assert abs(exposure - expected_exposure) < 0.01
    possible_amount = flags.loc[flags["confidence"] == "POSSIBLE", "amount_exposure"].sum()
    assert possible_amount > 0  # sanity: the POSSIBLE case did flag with a real amount
    assert exposure < certain_amount + probable_amount + possible_amount  # POSSIBLE excluded from exposure

    print(f"tier counts: {tier_counts}")
    print(f"estimated exposure (CERTAIN+PROBABLE only): {exposure:.2f}")
    print("Leakage detector acceptance test PASSED -- zero false positives, exact tier match.")


if __name__ == "__main__":
    main()
