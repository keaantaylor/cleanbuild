"""Phase 1: generate deliberately messy synthetic claims bordereaux.

Produces four fake sender files, each with different column names, column
order and date formats for the same ten skeleton fields, plus injected
data-quality problems (arithmetic mismatches, missing mandatory fields,
duplicate/near-duplicate claims). Also writes an answer key (JSON) listing
every injected problem, used by Phase 2+ tests to check detection.

Run: python3 generate_synthetic.py
"""

from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path

from faker import Faker

OUT_DIR = Path(__file__).parent
Faker.seed(42)
random.seed(42)
fake = Faker("en_IE")

CURRENCIES = ["EUR", "EUR", "EUR", "GBP", "USD"]
STATUSES = ["open", "closed", "reopened", "open", "closed"]


def rand_date(start: date, end: date) -> date:
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))


def make_claim(i: int, prefix: str) -> dict:
    loss_date = rand_date(date(2023, 1, 1), date(2025, 6, 30))
    notified_date = loss_date + timedelta(days=random.randint(0, 30))
    paid = round(random.uniform(0, 40000), 2)
    reserve = round(random.uniform(0, 20000), 2)
    incurred = round(paid + reserve, 2)
    status = random.choice(STATUSES)
    if status == "closed":
        reserve = 0.0
        incurred = paid
    return {
        "claim_ref": f"{prefix}-{i:05d}",
        "status": status,
        "loss_date": loss_date,
        "notified_date": notified_date,
        "insured": fake.company(),
        "policy_ref": f"POL-{prefix}-{random.randint(10000, 99999)}",
        "paid": paid,
        "reserve": reserve,
        "incurred": incurred,
        "currency": random.choice(CURRENCIES),
    }


def inject_arithmetic_errors(rows: list[dict], n: int, errors: list[dict]) -> None:
    targets = random.sample(rows, n)
    for row in targets:
        row["incurred"] = round(row["incurred"] + random.choice([-500, 750, 1200]), 2)
        errors.append({"claim_ref": row["claim_ref"], "type": "arithmetic_mismatch"})


def inject_missing_mandatory(rows: list[dict], n: int, errors: list[dict]) -> None:
    mandatory_fields = ["insured", "policy_ref", "status", "notified_date"]
    targets = random.sample(rows, n)
    for row in targets:
        field_name = random.choice(mandatory_fields)
        row[field_name] = None
        errors.append({
            "claim_ref": row["claim_ref"],
            "type": "missing_mandatory_field",
            "field": field_name,
        })


def inject_duplicates(rows: list[dict], n_pairs: int, errors: list[dict]) -> list[dict]:
    extra = []
    candidates = random.sample(rows, n_pairs)
    for idx, row in enumerate(candidates):
        dup = dict(row)
        if idx % 2 == 0:
            # exact duplicate claim reference, resubmitted verbatim
            extra.append(dup)
            errors.append({
                "claim_ref": row["claim_ref"],
                "type": "exact_duplicate",
            })
        else:
            # near-duplicate: same insured (misspelled) + adjacent loss date,
            # new claim reference
            dup["claim_ref"] = row["claim_ref"] + "-R"
            dup["insured"] = _misspell(row["insured"])
            dup["loss_date"] = row["loss_date"] + timedelta(days=1)
            extra.append(dup)
            errors.append({
                "claim_ref": [row["claim_ref"], dup["claim_ref"]],
                "type": "near_duplicate",
            })
    return extra


def _misspell(name: str) -> str:
    if len(name) < 4:
        return name + " "
    pos = random.randint(1, len(name) - 2)
    return name[:pos] + name[pos + 1] + name[pos] + name[pos + 2:]


def build_dataset(prefix: str, n_rows: int, n_arith_errors: int,
                   n_missing: int, n_dup_pairs: int) -> tuple[list[dict], list[dict]]:
    rows = [make_claim(i, prefix) for i in range(1, n_rows + 1)]
    errors: list[dict] = []
    inject_arithmetic_errors(rows, n_arith_errors, errors)
    inject_missing_mandatory(rows, n_missing, errors)
    dup_rows = inject_duplicates(rows, n_dup_pairs, errors)
    rows.extend(dup_rows)
    random.shuffle(rows)
    return rows, errors


def fmt_date(d: date | None, fmt: str) -> str | None:
    if d is None:
        return None
    return d.strftime(fmt)


def write_sender_a(rows: list[dict]) -> None:
    """Sedgwick Ireland style: DD/MM/YYYY dates, simple lowercase-ish headers."""
    import pandas as pd

    records = []
    for r in rows:
        records.append({
            "Claim Ref": r["claim_ref"],
            "Status": r["status"],
            "Loss Date": fmt_date(r["loss_date"], "%d/%m/%Y"),
            "Notification Date": fmt_date(r["notified_date"], "%d/%m/%Y"),
            "Insured": r["insured"],
            "Policy Ref": r["policy_ref"],
            "Paid": r["paid"],
            "Reserve": r["reserve"],
            "Incurred": r["incurred"],
            "Currency": r["currency"],
        })
    df = pd.DataFrame(records)
    df.to_csv(OUT_DIR / "sender_a_sedgwick.csv", index=False)


def write_sender_b(rows: list[dict]) -> None:
    """Crawford Ireland style: ISO dates, reordered columns, xlsx."""
    import pandas as pd

    records = []
    for r in rows:
        records.append({
            "Claim No.": r["claim_ref"],
            "Insured Name": r["insured"],
            "Policy Number": r["policy_ref"],
            "Claim Status": r["status"],
            "Date of Loss": fmt_date(r["loss_date"], "%Y-%m-%d"),
            "Date Notified": fmt_date(r["notified_date"], "%Y-%m-%d"),
            "Amount Paid": r["paid"],
            "O/S Reserve": r["reserve"],
            "Total Incurred": r["incurred"],
            "Ccy": r["currency"],
        })
    df = pd.DataFrame(records)
    df.to_excel(OUT_DIR / "sender_b_crawford.xlsx", index=False)


def write_sender_c(rows: list[dict]) -> None:
    """Blackrock MGA (SRG Dublin) style: US-style dates, camelCase headers."""
    import pandas as pd

    records = []
    for r in rows:
        records.append({
            "ClaimReference": r["claim_ref"],
            "ClaimStatus": r["status"],
            "LossDate": fmt_date(r["loss_date"], "%m/%d/%Y"),
            "FirstNotifiedDate": fmt_date(r["notified_date"], "%m/%d/%Y"),
            "InsuredName": r["insured"],
            "RiskReference": r["policy_ref"],
            "IndemnityPaid": r["paid"],
            "IndemnityReserve": r["reserve"],
            "TotalIncurred": r["incurred"],
            "SettlementCurrency": r["currency"],
        })
    df = pd.DataFrame(records)
    df.to_excel(OUT_DIR / "sender_c_blackrock.xlsx", index=False)


def write_sender_d(rows: list[dict]) -> None:
    """MX Underwriting style: deliberately novel headers, unseen by the
    alias dictionary, used to exercise the AI-assisted mapping fallback."""
    import pandas as pd

    records = []
    for r in rows:
        records.append({
            "Unique Identifier": r["claim_ref"],
            "Current Stage": r["status"],
            "Occurrence Date": fmt_date(r["loss_date"], "%d-%b-%Y"),
            "Advice Date": fmt_date(r["notified_date"], "%d-%b-%Y"),
            "Named Insured Party": r["insured"],
            "Cover Note Number": r["policy_ref"],
            "Settled Amount": r["paid"],
            "Outstanding Provision": r["reserve"],
            "Gross Position": r["incurred"],
            "Denomination": r["currency"],
        })
    df = pd.DataFrame(records)
    df.to_excel(OUT_DIR / "sender_d_mx_underwriting.xlsx", index=False)


def main() -> None:
    all_errors: dict[str, list[dict]] = {}

    rows_a, err_a = build_dataset("SDG", 50, n_arith_errors=2, n_missing=2, n_dup_pairs=3)
    write_sender_a(rows_a)
    all_errors["sender_a_sedgwick.csv"] = err_a

    rows_b, err_b = build_dataset("CRW", 200, n_arith_errors=3, n_missing=4, n_dup_pairs=4)
    write_sender_b(rows_b)
    all_errors["sender_b_crawford.xlsx"] = err_b

    rows_c, err_c = build_dataset("BLK", 1000, n_arith_errors=8, n_missing=12, n_dup_pairs=6)
    write_sender_c(rows_c)
    all_errors["sender_c_blackrock.xlsx"] = err_c

    rows_d, err_d = build_dataset("MXU", 80, n_arith_errors=2, n_missing=3, n_dup_pairs=3)
    write_sender_d(rows_d)
    all_errors["sender_d_mx_underwriting.xlsx"] = err_d

    with open(OUT_DIR / "answer_key.json", "w") as f:
        json.dump(all_errors, f, indent=2, default=str)

    for fname, errs in all_errors.items():
        n_rows = {"sender_a_sedgwick.csv": len(rows_a), "sender_b_crawford.xlsx": len(rows_b),
                  "sender_c_blackrock.xlsx": len(rows_c), "sender_d_mx_underwriting.xlsx": len(rows_d)}[fname]
        print(f"{fname}: {n_rows} rows, {len(errs)} injected issues")


if __name__ == "__main__":
    main()
