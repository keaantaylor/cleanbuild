"""Truebind 2.1: a small, deterministic fixture for the payment-leakage
detector, engineered with exactly one case at each confidence tier plus
clean/near-miss rows that must NOT be flagged (zero false positives).

Single sheet, simple headers (same convention as Phase 1's sender_a), so
it exercises leakage.py through the normal ingest path, not a hand-built
DataFrame -- catching any ingest-layer issues (date parsing, amount
coercion) the detector itself would otherwise mask.

Run: python3 generate_leakage_fixture.py
"""

from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from faker import Faker

OUT_DIR = Path(__file__).parent
Faker.seed(77)
random.seed(77)
fake = Faker("en_IE")


def make_clean_row(i: int) -> dict:
    loss_date = date(2025, 1, 1) + timedelta(days=random.randint(0, 300))
    paid = round(random.uniform(1000, 40000), 2)
    reserve = round(random.uniform(0, 10000), 2)
    return {
        "Claim Ref": f"LKG-{i:05d}",
        "Status": "open",
        "Loss Date": loss_date.strftime("%d/%m/%Y"),
        "Notification Date": (loss_date + timedelta(days=3)).strftime("%d/%m/%Y"),
        "Insured": fake.company(),
        "Policy Ref": f"POL-LKG-{random.randint(10000, 99999)}",
        "Paid": paid,
        "Reserve": reserve,
        "Incurred": round(paid + reserve, 2),
        "Currency": "EUR",
    }


def main() -> None:
    rows = [make_clean_row(i) for i in range(1, 21)]  # 20 clean baseline rows
    answer = {"fixture": "leakage_fixture.csv", "cases": {}}

    # --- CERTAIN: same claim paid twice (exact claim reference match) ---
    certain_a = make_clean_row(101)
    certain_a["Insured"] = "Meridian Logistics Ltd"
    certain_b = dict(certain_a)  # identical resubmission, same everything
    rows.extend([certain_a, certain_b])
    answer["cases"]["certain"] = {
        "claim_ref": certain_a["Claim Ref"],
        "expected_tier": "CERTAIN",
    }

    # --- PROBABLE: different claim ref, same payee, amount within 2%,
    #     loss dates 10 days apart (inside the 30-day tight window) ---
    probable_a = make_clean_row(102)
    probable_a["Insured"] = "Fairwind Shipping Group"
    probable_a["Paid"] = 15000.00
    probable_a_loss = date(2025, 4, 1)
    probable_a["Loss Date"] = probable_a_loss.strftime("%d/%m/%Y")

    probable_b = make_clean_row(103)
    probable_b["Insured"] = "FAIRWIND SHIPPING GROUP"  # case-only variant
    probable_b["Paid"] = 15150.00  # +1% -- within the 2% tolerance
    probable_b_loss = probable_a_loss + timedelta(days=10)
    probable_b["Loss Date"] = probable_b_loss.strftime("%d/%m/%Y")
    rows.extend([probable_a, probable_b])
    answer["cases"]["probable"] = {
        "claim_ref_a": probable_a["Claim Ref"], "claim_ref_b": probable_b["Claim Ref"],
        "expected_tier": "PROBABLE",
    }

    # --- POSSIBLE: different claim ref, same payee, amount within 2%,
    #     loss dates 60 days apart (outside tight, inside wide 90-day window) ---
    possible_a = make_clean_row(104)
    possible_a["Insured"] = "Blackrock Underwriting Partners"
    possible_a["Paid"] = 22000.00
    possible_a_loss = date(2025, 6, 1)
    possible_a["Loss Date"] = possible_a_loss.strftime("%d/%m/%Y")

    possible_b = make_clean_row(105)
    possible_b["Insured"] = "Blackrock Underwriting Partners"
    possible_b["Paid"] = 22200.00  # within 2%
    possible_b_loss = possible_a_loss + timedelta(days=60)
    possible_b["Loss Date"] = possible_b_loss.strftime("%d/%m/%Y")
    rows.extend([possible_a, possible_b])
    answer["cases"]["possible"] = {
        "claim_ref_a": possible_a["Claim Ref"], "claim_ref_b": possible_b["Claim Ref"],
        "expected_tier": "POSSIBLE",
    }

    # --- Negative case 1: same payee, same date, amount OUTSIDE tolerance
    #     (10% apart) -- must NOT be flagged ---
    neg1_a = make_clean_row(106)
    neg1_a["Insured"] = "Sterling Marine Assurance"
    neg1_a["Paid"] = 10000.00
    neg1_a_loss = date(2025, 3, 1)
    neg1_a["Loss Date"] = neg1_a_loss.strftime("%d/%m/%Y")

    neg1_b = make_clean_row(107)
    neg1_b["Insured"] = "Sterling Marine Assurance"
    neg1_b["Paid"] = 11200.00  # 12% higher -- outside 2% tolerance
    neg1_b["Loss Date"] = neg1_a_loss.strftime("%d/%m/%Y")
    rows.extend([neg1_a, neg1_b])

    # --- Negative case 2: same amount, same date, DIFFERENT payee --
    #     must NOT be flagged ---
    neg2_a = make_clean_row(108)
    neg2_a["Insured"] = "Coastal Freight Holdings"
    neg2_a["Paid"] = 8000.00
    neg2_a_loss = date(2025, 2, 1)
    neg2_a["Loss Date"] = neg2_a_loss.strftime("%d/%m/%Y")

    neg2_b = make_clean_row(109)
    neg2_b["Insured"] = "Havenbrook Retail Group"  # unrelated payee
    neg2_b["Paid"] = 8000.00
    neg2_b["Loss Date"] = neg2_a_loss.strftime("%d/%m/%Y")
    rows.extend([neg2_a, neg2_b])

    # --- Negative case 3: same payee, amount within tolerance, but loss
    #     dates 120 days apart -- outside even the wide window ---
    neg3_a = make_clean_row(110)
    neg3_a["Insured"] = "Northgate Aviation Services"
    neg3_a["Paid"] = 5000.00
    neg3_a_loss = date(2025, 1, 15)
    neg3_a["Loss Date"] = neg3_a_loss.strftime("%d/%m/%Y")

    neg3_b = make_clean_row(111)
    neg3_b["Insured"] = "Northgate Aviation Services"
    neg3_b["Paid"] = 5050.00
    neg3_b["Loss Date"] = (neg3_a_loss + timedelta(days=120)).strftime("%d/%m/%Y")
    rows.extend([neg3_a, neg3_b])

    random.shuffle(rows)
    df = pd.DataFrame(rows)
    df.to_csv(OUT_DIR / "leakage_fixture.csv", index=False)

    answer["total_rows"] = len(rows)
    answer["expected_flag_count"] = {"CERTAIN": 1, "PROBABLE": 1, "POSSIBLE": 1}
    answer["negative_cases"] = [
        {"claim_ref_a": neg1_a["Claim Ref"], "claim_ref_b": neg1_b["Claim Ref"], "reason": "amount outside tolerance"},
        {"claim_ref_a": neg2_a["Claim Ref"], "claim_ref_b": neg2_b["Claim Ref"], "reason": "different payee"},
        {"claim_ref_a": neg3_a["Claim Ref"], "claim_ref_b": neg3_b["Claim Ref"], "reason": "outside wide date window"},
    ]

    with open(OUT_DIR / "leakage_fixture_answer_key.json", "w") as f:
        json.dump(answer, f, indent=2, default=str)

    print(f"{len(rows)} rows written; expected tiers: "
          f"{answer['expected_flag_count']}; {len(answer['negative_cases'])} negative cases")


if __name__ == "__main__":
    main()
