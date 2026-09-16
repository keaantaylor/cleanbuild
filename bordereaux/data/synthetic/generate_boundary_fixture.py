"""Build test_boundary_cases.xlsx + test_boundary_cases_answer_key.json:
a 10-sheet, 320-row multi-sender workbook that exercises every defect in
the "Bordereaux MVP -- Ingestion & Mapping Fix Spec":

  - 10 sheets, each a different fictional sender with its own header
    wording/order (D1: only-first-sheet bug; 3.5: alias coverage).
  - 2 sheets ("RSA Group", "Tokio Marine HCC") carry a merged banner row
    above the real header row (D1 header-row-offset case; 3.2).
  - "Zurich Re" uses "Reserve Amount" / "Incurred Amount" headers that the
    original alias dictionary does not cover, while "Amount Paid" (same
    sheet) does -- reproducing D2/D4 exactly.
  - Deterministic, exactly-counted error injection: 48 missing claim refs,
    26 missing insured names (6-row overlap -> union 68), 38 arithmetic
    mismatches (delta 5,000-50,000), 16 probable-duplicate pairs (32 rows,
    including the in-sheet Zurich Re rows 6 & 24 case-only-name pair).

Every injected fact is recorded into the answer key as it's created, so
the two files are correct by construction -- the pipeline's job is to
rediscover exactly these facts.

Run: python3 generate_boundary_fixture.py
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import openpyxl
from faker import Faker

OUT_DIR = Path(__file__).parent
Faker.seed(2024)
random.seed(2024)
fake = Faker("en_IE")

CURRENCIES = ["EUR", "EUR", "EUR", "GBP", "USD"]
STATUSES = ["open", "closed", "reopened", "open", "closed"]


@dataclass
class SheetSpec:
    name: str
    prefix: str
    row_count: int
    columns: dict[str, str]  # canonical field code -> header text
    column_order: list[str]  # header text, in the order they appear
    has_banner: bool = False
    missing_claim_ref: int = 0
    missing_insured_name: int = 0
    arithmetic_errors: int = 0


@dataclass
class Row:
    sheet: str
    position: int  # 1-indexed position among this sheet's data rows
    claim_ref: str
    status: str
    loss_date: date
    notified_date: date
    insured: str
    policy_ref: str
    paid: float
    reserve: float
    incurred: float
    currency: str
    dup_group: int | None = None


def _shift_loss_date(row: Row, new_loss_date: date) -> None:
    """Move a row's loss date (for a duplicate injection) while keeping
    notified_date >= loss_date, so the duplicate-pair injection never
    incidentally creates an unrelated date_order validation exception."""
    delta = new_loss_date - row.loss_date
    row.loss_date = new_loss_date
    row.notified_date = row.notified_date + delta


def rand_date(start: date, end: date) -> date:
    return start + timedelta(days=random.randint(0, (end - start).days))


def make_row(sheet: str, position: int, prefix: str) -> Row:
    loss_date = rand_date(date(2024, 10, 1), date(2025, 6, 30))
    notified_date = loss_date + timedelta(days=random.randint(0, 21))
    paid = round(random.uniform(500, 60000), 2)
    reserve = round(random.uniform(0, 40000), 2)
    status = random.choice(STATUSES)
    if status == "closed":
        reserve = 0.0
    incurred = round(paid + reserve, 2)
    return Row(
        sheet=sheet,
        position=position,
        claim_ref=f"{prefix}-{position:05d}",
        status=status,
        loss_date=loss_date,
        notified_date=notified_date,
        insured=fake.company(),
        policy_ref=f"POL-{prefix}-{random.randint(10000, 99999)}",
        paid=paid,
        reserve=reserve,
        incurred=incurred,
        currency=random.choice(CURRENCIES),
    )


# ---------------------------------------------------------------------
# Sheet specs: 10 senders, row counts sum to 320, headers vary widely.
# RESERVE_HDR / INCURRED_HDR on "Zurich Re" are deliberately the two
# header spellings the original alias dictionary does not recognise.
# ---------------------------------------------------------------------

SHEETS: list[SheetSpec] = [
    SheetSpec(
        name="Zurich Re", prefix="ZUR", row_count=35,
        columns={
            "CR0104M": "Claim Reference", "CR0105CM": "Claim Status",
            "CR0119CM": "Loss Date", "CR0136CM": "Notified Date",
            "CR0035M": "Insured Name", "CR0029M": "Policy Reference",
            "CR0126CM": "Amount Paid", "CR0130CM": "Reserve Amount",
            "CR0155CM": "Incurred Amount", "CR0110CM": "Currency",
        },
        column_order=["Claim Reference", "Claim Status", "Loss Date", "Notified Date",
                      "Insured Name", "Policy Reference", "Amount Paid", "Reserve Amount",
                      "Incurred Amount", "Currency"],
        missing_claim_ref=5, missing_insured_name=3, arithmetic_errors=6,
    ),
    SheetSpec(
        name="Beazley", prefix="BEZ", row_count=28,
        columns={
            "CR0104M": "Claim No", "CR0105CM": "Status", "CR0119CM": "Date of Loss",
            "CR0136CM": "Date Notified", "CR0035M": "Insured", "CR0029M": "Policy No",
            "CR0126CM": "Paid", "CR0130CM": "O/S Reserve", "CR0155CM": "Total Incurred",
            "CR0110CM": "Ccy",
        },
        column_order=["Claim No", "Status", "Date of Loss", "Date Notified", "Insured",
                      "Policy No", "Paid", "O/S Reserve", "Total Incurred", "Ccy"],
        missing_claim_ref=4, missing_insured_name=2, arithmetic_errors=3,
    ),
    SheetSpec(
        name="Hiscox", prefix="HSC", row_count=32,
        columns={
            "CR0104M": "ClaimRef", "CR0105CM": "ClaimStatus", "CR0119CM": "LossDate",
            "CR0136CM": "NotifiedDate", "CR0035M": "Insured", "CR0029M": "PolicyRef",
            "CR0126CM": "IndemnityPaid", "CR0130CM": "IndemnityReserve",
            "CR0155CM": "TotalIncurred", "CR0110CM": "SettlementCurrency",
        },
        column_order=["ClaimRef", "ClaimStatus", "LossDate", "NotifiedDate", "Insured",
                      "PolicyRef", "IndemnityPaid", "IndemnityReserve", "TotalIncurred",
                      "SettlementCurrency"],
        missing_claim_ref=5, missing_insured_name=3, arithmetic_errors=4,
    ),
    SheetSpec(
        name="Chubb", prefix="CHB", row_count=25,
        columns={
            "CR0104M": "Reference", "CR0105CM": "State", "CR0119CM": "Incident Date",
            "CR0136CM": "Advised Date", "CR0035M": "Client Name", "CR0029M": "Contract No",
            "CR0126CM": "Paid To Date", "CR0130CM": "Case Reserve",
            "CR0155CM": "Incurred To Date", "CR0110CM": "Currency Code",
        },
        column_order=["Reference", "State", "Incident Date", "Advised Date", "Client Name",
                      "Contract No", "Paid To Date", "Case Reserve", "Incurred To Date",
                      "Currency Code"],
        missing_claim_ref=4, missing_insured_name=2, arithmetic_errors=3,
    ),
    SheetSpec(
        name="AIG", prefix="AIG", row_count=40,
        columns={
            "CR0104M": "Claim Number", "CR0105CM": "Claim State", "CR0119CM": "Date of Loss",
            "CR0136CM": "First Notified", "CR0035M": "Policyholder", "CR0029M": "Policy Number",
            "CR0126CM": "Amount Paid", "CR0130CM": "Reserve O/S", "CR0155CM": "Gross Incurred",
            "CR0110CM": "Ccy Code",
        },
        column_order=["Claim Number", "Claim State", "Date of Loss", "First Notified",
                      "Policyholder", "Policy Number", "Amount Paid", "Reserve O/S",
                      "Gross Incurred", "Ccy Code"],
        missing_claim_ref=6, missing_insured_name=4, arithmetic_errors=5,
    ),
    SheetSpec(
        name="RSA Group", prefix="RSA", row_count=30,
        columns={
            "CR0104M": "Claim Ref", "CR0105CM": "Status", "CR0119CM": "Loss Date",
            "CR0136CM": "Notification Date", "CR0035M": "Insured", "CR0029M": "Policy Ref",
            "CR0126CM": "Paid Amount", "CR0130CM": "Reserve Amount",
            "CR0155CM": "Incurred Amount", "CR0110CM": "Currency",
        },
        column_order=["Claim Ref", "Status", "Loss Date", "Notification Date", "Insured",
                      "Policy Ref", "Paid Amount", "Reserve Amount", "Incurred Amount",
                      "Currency"],
        has_banner=True,
        missing_claim_ref=5, missing_insured_name=3, arithmetic_errors=3,
    ),
    SheetSpec(
        name="Allianz", prefix="ALZ", row_count=22,
        columns={
            "CR0104M": "Claim Reference No", "CR0105CM": "Current Status",
            "CR0119CM": "Date Of Loss", "CR0136CM": "Date First Notified",
            "CR0035M": "Name of Insured", "CR0029M": "Policy Reference No",
            "CR0126CM": "Indemnity Paid", "CR0130CM": "Indemnity O/S",
            "CR0155CM": "Total Incurred Amount", "CR0110CM": "Settlement Ccy",
        },
        column_order=["Claim Reference No", "Current Status", "Date Of Loss",
                      "Date First Notified", "Name of Insured", "Policy Reference No",
                      "Indemnity Paid", "Indemnity O/S", "Total Incurred Amount",
                      "Settlement Ccy"],
        missing_claim_ref=3, missing_insured_name=2, arithmetic_errors=2,
    ),
    SheetSpec(
        name="Tokio Marine HCC", prefix="TMH", row_count=45,
        columns={
            "CR0104M": "Claim Ref", "CR0105CM": "Claim Status", "CR0119CM": "Loss Date",
            "CR0136CM": "Notified Date", "CR0035M": "Insured Name", "CR0029M": "Policy No",
            "CR0126CM": "Paid", "CR0130CM": "Reserve", "CR0155CM": "Incurred",
            "CR0110CM": "Currency",
        },
        column_order=["Claim Ref", "Claim Status", "Loss Date", "Notified Date",
                      "Insured Name", "Policy No", "Paid", "Reserve", "Incurred", "Currency"],
        has_banner=True,
        missing_claim_ref=7, missing_insured_name=4, arithmetic_errors=6,
    ),
    SheetSpec(
        name="AXA XL", prefix="AXL", row_count=33,
        columns={
            "CR0104M": "Claim ID", "CR0105CM": "Status Code", "CR0119CM": "Date Loss Occurred",
            "CR0136CM": "Date Claim Notified", "CR0035M": "Insured Party",
            "CR0029M": "Policy Identifier", "CR0126CM": "Amount Paid To Date",
            "CR0130CM": "Outstanding Reserve", "CR0155CM": "Incurred Total",
            "CR0110CM": "Currency",
        },
        column_order=["Claim ID", "Status Code", "Date Loss Occurred", "Date Claim Notified",
                      "Insured Party", "Policy Identifier", "Amount Paid To Date",
                      "Outstanding Reserve", "Incurred Total", "Currency"],
        missing_claim_ref=5, missing_insured_name=2, arithmetic_errors=3,
    ),
    SheetSpec(
        name="Markel", prefix="MRK", row_count=30,
        columns={
            "CR0104M": "CLAIM_REF", "CR0105CM": "CLAIM_STATUS", "CR0119CM": "LOSS_DATE",
            "CR0136CM": "NOTIFIED_DATE", "CR0035M": "INSURED_NAME", "CR0029M": "POLICY_REF",
            "CR0126CM": "PAID_AMT", "CR0130CM": "RESERVE_AMT", "CR0155CM": "INCURRED_AMT",
            "CR0110CM": "CURRENCY",
        },
        column_order=["CLAIM_REF", "CLAIM_STATUS", "LOSS_DATE", "NOTIFIED_DATE",
                      "INSURED_NAME", "POLICY_REF", "PAID_AMT", "RESERVE_AMT", "INCURRED_AMT",
                      "CURRENCY"],
        missing_claim_ref=4, missing_insured_name=1, arithmetic_errors=3,
    ),
]

assert sum(s.row_count for s in SHEETS) == 320
assert sum(s.missing_claim_ref for s in SHEETS) == 48
assert sum(s.missing_insured_name for s in SHEETS) == 26
assert sum(s.arithmetic_errors for s in SHEETS) == 38

NAME_VARIANTS = [
    lambda n: n.upper(),
    lambda n: n.lower(),
    lambda n: n.replace("Ltd", "Limited") if "Ltd" in n else (n.replace("Limited", "Ltd") if "Limited" in n else n + " "),
    lambda n: n.replace("&", "and") if "&" in n else n.replace(" and ", " & ") if " and " in n else n + "  ",
    lambda n: n.strip() + "  ",
]


def main() -> None:
    all_rows: list[Row] = []
    answer = {
        "fixture": "test_boundary_cases.xlsx",
        "total_rows": 320,
        "sheets_processed": 10,
        "sheet_row_counts": {s.name: s.row_count for s in SHEETS},
        "sheets_with_banner_row": [s.name for s in SHEETS if s.has_banner],
        "column_mapping_by_sheet": {s.name: s.columns for s in SHEETS},
        "injected_errors": {
            "missing_mandatory_fields": {"claim_reference": [], "insured_name": [], "overlap": []},
            "arithmetic_errors": {"count": 38, "rows": []},
            "duplicates": {"count": 16, "pairs": []},
        },
        "validation_notes": (
            "Every row listed under missing_mandatory_fields, arithmetic_errors and "
            "duplicates is a deliberate, exact injection -- a correct pipeline run "
            "flags precisely these rows and no others for the corresponding reason "
            "(zero false positives, zero false negatives)."
        ),
    }

    # ---- base rows, per sheet ----
    sheet_rows: dict[str, list[Row]] = {}
    for spec in SHEETS:
        rows = [make_row(spec.name, i + 1, spec.prefix) for i in range(spec.row_count)]
        sheet_rows[spec.name] = rows
        all_rows.extend(rows)

    # ---- missing claim_ref / insured_name, with a deliberate 6-row overlap ----
    overlap_remaining = 6
    for spec in SHEETS:
        rows = sheet_rows[spec.name]
        positions = list(range(len(rows)))
        random.shuffle(positions)
        claim_ref_targets = positions[: spec.missing_claim_ref]
        remaining = positions[spec.missing_claim_ref:]

        n_overlap_here = 0
        if overlap_remaining > 0 and claim_ref_targets and spec.missing_insured_name > 0:
            n_overlap_here = min(overlap_remaining, spec.missing_insured_name, len(claim_ref_targets))
            overlap_remaining -= n_overlap_here

        insured_targets = claim_ref_targets[:n_overlap_here] + remaining[: spec.missing_insured_name - n_overlap_here]

        for pos in claim_ref_targets:
            rows[pos].claim_ref = None
            answer["injected_errors"]["missing_mandatory_fields"]["claim_reference"].append(
                {"sheet": spec.name, "row": rows[pos].position})
        for pos in insured_targets:
            rows[pos].insured = None
            answer["injected_errors"]["missing_mandatory_fields"]["insured_name"].append(
                {"sheet": spec.name, "row": rows[pos].position})
        for pos in set(claim_ref_targets) & set(insured_targets):
            answer["injected_errors"]["missing_mandatory_fields"]["overlap"].append(
                {"sheet": spec.name, "row": rows[pos].position})

    used_for_injection: dict[str, set[int]] = {s.name: set() for s in SHEETS}
    for spec in SHEETS:
        rows = sheet_rows[spec.name]
        for pos, r in enumerate(rows):
            if r.claim_ref is None or r.insured is None:
                used_for_injection[spec.name].add(pos)

    # ---- arithmetic mismatches: delta 5,000-50,000, avoid rows already missing fields ----
    for spec in SHEETS:
        rows = sheet_rows[spec.name]
        available = [p for p in range(len(rows)) if p not in used_for_injection[spec.name]]
        random.shuffle(available)
        targets = available[: spec.arithmetic_errors]
        for pos in targets:
            r = rows[pos]
            delta = round(random.uniform(5000, 50000), 2) * random.choice([1, -1])
            r.incurred = round(r.incurred + delta, 2)
            used_for_injection[spec.name].add(pos)
            answer["injected_errors"]["arithmetic_errors"]["rows"].append({
                "sheet": spec.name, "row": r.position, "claim_reference": r.claim_ref,
                "difference": round(delta, 2),
            })

    # ---- duplicates: 1 fixed in-sheet pair (Zurich Re 6 & 24) + 15 more ----
    dup_pairs: list[tuple[Row, Row]] = []

    zur = sheet_rows["Zurich Re"]
    src, tgt = zur[5], zur[23]  # positions 6 and 24, 1-indexed
    tgt.insured = src.insured.upper()
    _shift_loss_date(tgt, src.loss_date)
    used_for_injection["Zurich Re"].update({5, 23})
    dup_pairs.append((src, tgt))

    all_sheet_names = [s.name for s in SHEETS]
    attempts = 0
    while len(dup_pairs) < 16 and attempts < 5000:
        attempts += 1
        sheet_a = random.choice(all_sheet_names)
        sheet_b = random.choice(all_sheet_names) if random.random() < 0.5 else sheet_a
        rows_a, rows_b = sheet_rows[sheet_a], sheet_rows[sheet_b]
        pa = random.randrange(len(rows_a))
        pb = random.randrange(len(rows_b))
        if sheet_a == sheet_b and pa == pb:
            continue
        if pa in used_for_injection[sheet_a] or pb in used_for_injection[sheet_b]:
            continue
        src_row, tgt_row = rows_a[pa], rows_b[pb]
        if src_row.insured is None or tgt_row.insured is None:
            continue
        variant = random.choice(NAME_VARIANTS)
        tgt_row.insured = variant(src_row.insured)
        _shift_loss_date(tgt_row, src_row.loss_date + timedelta(days=random.choice([-1, 0, 1])))
        used_for_injection[sheet_a].add(pa)
        used_for_injection[sheet_b].add(pb)
        dup_pairs.append((src_row, tgt_row))

    assert len(dup_pairs) == 16, f"only generated {len(dup_pairs)} duplicate pairs"
    for src_row, tgt_row in dup_pairs:
        answer["injected_errors"]["duplicates"]["pairs"].append({
            "a": {"sheet": src_row.sheet, "row": src_row.position, "claim_reference": src_row.claim_ref,
                  "insured_name": src_row.insured, "loss_date": str(src_row.loss_date)},
            "b": {"sheet": tgt_row.sheet, "row": tgt_row.position, "claim_reference": tgt_row.claim_ref,
                  "insured_name": tgt_row.insured, "loss_date": str(tgt_row.loss_date)},
        })

    # ---- write the workbook ----
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for spec in SHEETS:
        ws = wb.create_sheet(spec.name)
        row_cursor = 1
        if spec.has_banner:
            ws.append([f"{spec.name.upper()} -- CLAIMS BORDEREAU -- Q2 2025"])
            ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(spec.column_order))
            row_cursor += 1
        ws.append(spec.column_order)
        row_cursor += 1
        code_by_header = {v: k for k, v in spec.columns.items()}
        for r in sheet_rows[spec.name]:
            by_code = {
                "CR0104M": r.claim_ref, "CR0105CM": r.status, "CR0119CM": r.loss_date,
                "CR0136CM": r.notified_date, "CR0035M": r.insured, "CR0029M": r.policy_ref,
                "CR0126CM": r.paid, "CR0130CM": r.reserve, "CR0155CM": r.incurred,
                "CR0110CM": r.currency,
            }
            ws.append([by_code[code_by_header[h]] for h in spec.column_order])

    wb.save(OUT_DIR / "test_boundary_cases.xlsx")

    with open(OUT_DIR / "test_boundary_cases_answer_key.json", "w") as f:
        json.dump(answer, f, indent=2, default=str)

    n_missing_claimref = len(answer["injected_errors"]["missing_mandatory_fields"]["claim_reference"])
    n_missing_insured = len(answer["injected_errors"]["missing_mandatory_fields"]["insured_name"])
    n_overlap = len(answer["injected_errors"]["missing_mandatory_fields"]["overlap"])
    n_arith = len(answer["injected_errors"]["arithmetic_errors"]["rows"])
    n_dup = len(answer["injected_errors"]["duplicates"]["pairs"])
    print(f"sheets: {len(SHEETS)}, total rows: {sum(s.row_count for s in SHEETS)}")
    print(f"missing claim_ref: {n_missing_claimref}, missing insured_name: {n_missing_insured}, "
          f"overlap: {n_overlap}, union: {n_missing_claimref + n_missing_insured - n_overlap}")
    print(f"arithmetic errors: {n_arith}")
    print(f"duplicate pairs: {n_dup} ({n_dup * 2} rows)")


if __name__ == "__main__":
    main()
