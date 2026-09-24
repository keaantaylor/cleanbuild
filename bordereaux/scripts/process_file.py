"""Phase 2: ingest + validate + segregate one bordereau, with a
hard-coded column mapping (we know the layout because we generated the
Phase 1 synthetic data ourselves). No AI/fuzzy mapping yet -- that's
Phase 3.

Usage: python3 scripts/process_file.py <sender>
  sender in {a, b, c, d}
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from bordereaux import export, ingest, validation  # noqa: E402
from bordereaux.pandera_schema import CANONICAL_SCHEMA  # noqa: E402

DATA_DIR = REPO_ROOT / "data" / "synthetic"
OUT_DIR = REPO_ROOT / "data" / "output"

HARD_CODED_MAPPINGS = {
    "a": (
        DATA_DIR / "sender_a_sedgwick.csv",
        {
            "Claim Ref": "CR0104M",
            "Status": "CR0105CM",
            "Loss Date": "CR0119CM",
            "Notification Date": "CR0136CM",
            "Insured": "CR0035M",
            "Policy Ref": "CR0029M",
            "Paid": "TB_PAID_TD",
            "Reserve": "CR0130CM",
            "Incurred": "CR0155CM",
            "Currency": "CR0110CM",
        },
    ),
    "b": (
        DATA_DIR / "sender_b_crawford.xlsx",
        {
            "Claim No.": "CR0104M",
            "Claim Status": "CR0105CM",
            "Date of Loss": "CR0119CM",
            "Date Notified": "CR0136CM",
            "Insured Name": "CR0035M",
            "Policy Number": "CR0029M",
            "Amount Paid": "TB_PAID_TD",
            "O/S Reserve": "CR0130CM",
            "Total Incurred": "CR0155CM",
            "Ccy": "CR0110CM",
        },
    ),
    "c": (
        DATA_DIR / "sender_c_blackrock.xlsx",
        {
            "ClaimReference": "CR0104M",
            "ClaimStatus": "CR0105CM",
            "LossDate": "CR0119CM",
            "FirstNotifiedDate": "CR0136CM",
            "InsuredName": "CR0035M",
            "RiskReference": "CR0029M",
            "IndemnityPaid": "TB_PAID_TD",
            "IndemnityReserve": "CR0130CM",
            "TotalIncurred": "CR0155CM",
            "SettlementCurrency": "CR0110CM",
        },
    ),
    "d": (
        DATA_DIR / "sender_d_mx_underwriting.xlsx",
        {
            "Unique Identifier": "CR0104M",
            "Current Stage": "CR0105CM",
            "Occurrence Date": "CR0119CM",
            "Advice Date": "CR0136CM",
            "Named Insured Party": "CR0035M",
            "Cover Note Number": "CR0029M",
            "Settled Amount": "TB_PAID_TD",
            "Outstanding Provision": "CR0130CM",
            "Gross Position": "CR0155CM",
            "Denomination": "CR0110CM",
        },
    ),
}


def process(sender: str) -> tuple:
    path, mapping = HARD_CODED_MAPPINGS[sender]
    raw = ingest.load_raw(path)
    canonical = ingest.apply_mapping(raw, mapping)
    CANONICAL_SCHEMA.validate(canonical)
    exceptions = validation.validate(canonical).exceptions

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{path.stem}_segregated.xlsx"
    export.write_segregated_export(canonical, out_path)
    return canonical, exceptions, out_path


def main() -> None:
    sender = sys.argv[1] if len(sys.argv) > 1 else "a"
    canonical, exceptions, out_path = process(sender)

    print(f"Processed {len(canonical)} rows for sender '{sender}'.")
    print(f"Segregated export written to {out_path}")
    print(f"\n{len(exceptions)} exceptions found:")
    if not exceptions.empty:
        print(exceptions["rule"].value_counts().to_string())
        print()
        print(exceptions.to_string(index=False))


if __name__ == "__main__":
    main()
