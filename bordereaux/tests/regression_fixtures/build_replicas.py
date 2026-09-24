"""Replicas of the user's regression workbooks, built from the defect
descriptions (the original files were not available in the repo).

Known ground truth per file is returned by build_all() so tests can assert
exact numbers instead of eyeballing output."""
from __future__ import annotations

import random
from pathlib import Path

import openpyxl

OUT = Path(__file__).resolve().parent
_A = ["Harbour", "Granite", "Willow", "Summit", "Beacon", "Falcon", "Meadow", "Cobalt", "Juniper", "Anchor",
      "Crescent", "Orchard", "Pinnacle", "Riverside", "Sterling", "Thistle", "Vantage", "Westgate", "Yarrow", "Zenith"]
_B = ["Logistics", "Bakery", "Dental", "Motors", "Textiles", "Farms", "Clinics", "Marine", "Hotels", "Joinery",
      "Pharma", "Foods", "Studios", "Builders", "Freight", "Optics", "Kennels", "Brewing", "Printing", "Surveys"]
_C = ["Ltd", "plc", "LLP", "Group", "Holdings", "& Sons", "Partners", "Co", "Trading", "Services"]


def name(i: int, salt: int = 0) -> str:
    """Distinct, realistic insured names (a unique A/B/C combination per i),
    so near-duplicate matching is not triggered by synthetic look-alikes."""
    j = i + 97 * salt
    return f"{_A[j % 20]} {_B[(j // 20) % 20]} {_C[(j // 400) % 10]}"


def _save(name: str, sheets: dict[str, list[list]]) -> Path:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for title, rows in sheets.items():
        ws = wb.create_sheet(title)
        for r in rows:
            ws.append(r)
    path = OUT / name
    wb.save(path)
    return path


def test1_basic() -> Path:
    """12 clean rows: Paid Indemnity + Paid Expenses + Outstanding Reserve == Total Incurred."""
    rng = random.Random(1)
    rows = [["Claim Reference", "Insured Name", "Date of Loss", "Claim Status", "Currency",
             "Paid Indemnity", "Paid Expenses", "Outstanding Reserve", "Total Incurred"]]
    for i in range(12):
        pi, pe, osr = rng.randint(1000, 90000), rng.randint(100, 9000), rng.randint(0, 50000)
        rows.append([f"T1-{i:03d}", name(i), f"2024-0{1 + i % 9}-1{i % 9}", "Open", "GBP",
                     pi, pe, osr, pi + pe + osr])
    return _save("Truebind_Test1_Basic_replica.xlsx", {"Claims": rows})


def _void_rows(prefix: str, n: int, void_at: int) -> list[list]:
    rng = random.Random(prefix)
    rows = [["Claim Ref", "Insured", "Loss Date", "Status", "Currency", "Paid Indemnity", "Paid Expenses",
             "Outstanding Reserve", "Total Incurred"]]
    for i in range(n):
        pi, pe, osr = rng.randint(1000, 50000), rng.randint(0, 5000), rng.randint(0, 30000)
        status = "Void" if i == void_at else rng.choice(["Open", "Closed", "Reopened"])
        rows.append([f"{prefix}-{i:04d}", name(i, len(prefix) + ord(prefix[-1])), f"2024-{1 + i % 12:02d}-{1 + i % 27:02d}", status, "GBP", pi, pe, osr, pi + pe + osr])
    return rows


def realworld_a() -> Path:
    return _save("Truebind_RealWorld_A_Meridian_Monthly_replica.xlsx", {"Meridian Mar-24": _void_rows("MER", 40, 7)})


def realworld_b() -> Path:
    return _save("Truebind_RealWorld_B_Coastline_Consolidated_replica.xlsx",
                 {"Coastline Q1": _void_rows("CST", 30, 3), "Coastline Q2": _void_rows("CSU", 30, 20)})


SENDER_COLS = {"Sender Alpha": ("Adjuster Reference", "Broker Reference"),
               "Sender Beta": ("Handler Ref", "Cedant Ref"),
               "Sender Gamma": ("Coverholder Ref", "Binder Ref")}
DUP_REFS: list[str] = []
DEV_REFS: list[str] = []


def stress_450() -> Path:
    """3 sheets x 150 rows (450). Per sheet: 2 exact resubmissions (same ref,
    same period, identical values) and 2 development pairs (same ref, later
    period, different amounts). Totals: 6 duplicate groups, 6 development pairs."""
    rng = random.Random(450)
    sheets = {}
    DUP_REFS.clear()
    DEV_REFS.clear()
    for s_i, (title, (xa, xb)) in enumerate(SENDER_COLS.items()):
        header = ["Claim Reference", "Insured Name", "Date of Loss", "Claim Status", "Currency", "Period End",
                  "Paid Indemnity", "Paid Expenses", "Outstanding Reserve", "Total Incurred", xa, xb]
        base = []
        for i in range(146):
            pi, pe, osr = rng.randint(1000, 200000), rng.randint(0, 9000), rng.randint(0, 150000)
            base.append([f"S{s_i}-{i:04d}", name(i, s_i + 1),
                         f"2023-{1 + i % 12:02d}-{1 + i % 27:02d}", "Open", "GBP", "2024-03-31",
                         pi, pe, osr, pi + pe + osr, f"{xa[:3].upper()}-{i}", f"{xb[:3].upper()}-{i}"])
        rows = list(base)
        for k in (0, 1):  # exact resubmissions
            rows.append(list(base[10 + k]))
            DUP_REFS.append(base[10 + k][0])
        for k in (0, 1):  # development: next period, amounts moved on
            r = list(base[50 + k])
            r[5] = "2024-04-30"
            r[6] += 61300
            r[8] = max(0, r[8] - 254)
            r[9] = r[6] + r[7] + r[8]
            rows.append(r)
            DEV_REFS.append(r[0])
        sheets[title] = [header] + rows
    return _save("Truebind_StressTest_450rows_replica.xlsx", sheets)


def build_all() -> dict[str, Path]:
    return {"test1": test1_basic(), "rw_a": realworld_a(), "rw_b": realworld_b(), "stress": stress_450()}


if __name__ == "__main__":
    for k, p in build_all().items():
        print(k, p)
