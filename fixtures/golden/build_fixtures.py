"""Build the golden fixtures for the check modules (deterministic).

    python fixtures/golden/build_fixtures.py

Each module gets:
- dirty.xlsx + answer_key.json: every planted defect, written by hand next to
  the row that carries it (the answer key is the specification, never the
  module's output);
- clean.xlsx: the same shape with no defect -- must yield zero findings;
- unmapped.xlsx: the dirty file with the rule inputs under headers nobody
  can map -- must yield NOT_ASSESSED, never "passed".
The generated files are committed; re-running this script must not change
them (fixed workbook timestamps).
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any

import openpyxl

HERE = Path(__file__).resolve().parent
FIXED = dt.datetime(2026, 1, 1, 0, 0, 0)
HEADER = ["Claim Reference", "Insured Name", "Date of Loss", "Claim Status", "Currency", "Paid to Date",
          "Outstanding Reserve", "Total Incurred"]  # fmt: skip


def _save(path: Path, sheets: dict[str, list[list[Any]]]) -> None:
    wb = openpyxl.Workbook()
    first = True
    for name, rows in sheets.items():
        ws = wb.active if first else wb.create_sheet(name)
        assert ws is not None
        ws.title = name
        first = False
        for r in rows:
            ws.append(r)
    wb.properties.created = FIXED
    raw = io.BytesIO()
    wb.save(raw)  # openpyxl stamps "modified" with the current time: rewrite it, and every entry's time
    raw.seek(0)
    out = io.BytesIO()
    with zipfile.ZipFile(raw) as src, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            body = src.read(item.filename)
            if item.filename == "docProps/core.xml":
                body = re.sub(rb"<dcterms:modified([^>]*)>[^<]*<", rb"<dcterms:modified\1>2026-01-01T00:00:00Z<", body)
            dst.writestr(
                zipfile.ZipInfo(item.filename, date_time=(2026, 1, 1, 0, 0, 0)),
                body,
                compress_type=zipfile.ZIP_DEFLATED,
            )
    path.write_bytes(out.getvalue())


Planted = list[tuple[list[Any], list[dict[str, Any]]]]


def _split(rows: Planted) -> tuple[list[list[Any]], list[tuple[int, dict[str, Any]]]]:
    data = [HEADER]
    expected: list[tuple[int, dict[str, Any]]] = []
    for values, expects in rows:
        data.append(values)
        expected.extend((len(data), e) for e in expects)  # 1-based sheet row (header is row 1)
    return data, expected


def d(y: int, m: int, day: int) -> dt.datetime:
    return dt.datetime(y, m, day)


# ------------------------------------------------------------------ binder
BINDER = {
    "name": "Golden Binder 2024-25",
    "umr": "B0999GOLDEN2024",
    "coverholder": "Golden Coverholder Ltd",
    "inception_date": "2024-03-01",
    "expiry_date": "2025-02-28",
    "currencies": ["EUR", "GBP"],
    "limit_currency": "GBP",
    "claims_authority": "50000.00",
    "aggregate_limit": "250000.00",
}
# ECB rates used by the golden test (units per EUR), constant over the period.
FX = {"GBP": "0.8500", "USD": "1.0800"}

PERIOD, CCY, AUTH = "BND_LOSS_OUTSIDE_PERIOD", "BND_CURRENCY_NOT_PERMITTED", "BND_OVER_AUTHORITY"
FAIL, REVIEW = "FAIL", "REVIEW"

BINDER_DIRTY_MAIN: list[tuple[list[Any], list[dict[str, Any]]]] = [
    (["TB-001", "Alder Marine", d(2024, 4, 10), "Open", "GBP", 10000, 5000, 15000], []),
    (
        ["TB-002", "Birch Haulage", d(2024, 2, 20), "Open", "GBP", 2000, 1000, 3000],
        [{"rule": PERIOD, "status": FAIL}],
    ),  # before inception
    (
        ["TB-003", "Cedar Foods", d(2025, 3, 5), "Open", "GBP", 1000, 500, 1500],
        [{"rule": PERIOD, "status": FAIL}],
    ),  # after expiry
    (
        ["TB-004", "Dunmore Retail", d(2024, 6, 1), "Open", "USD", 4000, 1000, 5000],
        [{"rule": CCY, "status": FAIL}],
    ),  # USD not permitted; 5,000 USD is within authority
    (
        ["TB-005", "Elm Logistics", d(2024, 7, 15), "Open", "GBP", 60000, 20000, 80000],
        [{"rule": AUTH, "status": FAIL, "amount": "30000.00", "currency": "GBP"}],
    ),
    (
        ["TB-006", "Fern Textiles", d(2024, 8, 1), "Open", "EUR", 50000, 20000, 70000],
        [{"rule": AUTH, "status": FAIL, "amount": "9500.00", "currency": "GBP"}],
    ),  # 70,000 x 0.85 = 59,500
    (["TB-007", "Gorse Farms", d(2024, 9, 9), "Closed", "EUR", 40000, 0, 40000], []),  # 34,000 GBP
    (["TB-008", "Hazel Print", d(2024, 10, 10), "Open", "GBP", 45000, 5000, 50000], []),  # exactly at authority
    (["TB-009", "Ivy Studios", d(2024, 3, 1), "Open", "GBP", 5000, 0, 5000], []),  # inception day, inclusive
    (["TB-010", "Juniper Tech", d(2025, 2, 28), "Open", "GBP", 5000, 0, 5000], []),  # expiry day, inclusive
    (
        ["TB-011", "Kestrel Autos", d(2024, 5, 5), "Open", "JPY", 100000, 0, 100000],
        [{"rule": CCY, "status": FAIL}],
    ),  # no JPY rate: authority not assessed for this row
    (["TB-012", "Larch Energy", d(2024, 11, 11), "Open", "GBP", 30000, 10000, 40000], []),
    (["TB-013", "Maple Dental", d(2024, 12, 12), "Open", "GBP", 20000, 0, 20000], []),
]
# Every date in this column reads both ways (all days <= 12): the engine reads
# day/month and discloses it; one reading in, one out -> REVIEW.
BINDER_DIRTY_AMBIGUOUS: list[tuple[list[Any], list[dict[str, Any]]]] = [
    (
        ["TB-101", "Nettle Bakery", "02/03/2024", "Open", "GBP", 1000, 0, 1000],
        [{"rule": PERIOD, "status": REVIEW}],
    ),  # 2 Mar 2024 in / 3 Feb 2024 out
    (["TB-102", "Oak Joinery", "05/06/2024", "Open", "GBP", 1000, 0, 1000], []),  # both readings in
    (
        ["TB-103", "Pine Cycles", "10/01/2025", "Open", "GBP", 1000, 0, 1000],
        [{"rule": PERIOD, "status": REVIEW}],
    ),  # 10 Jan 2025 in / 1 Oct 2025 out
    (
        ["TB-104", "Quince Cafe", "01/02/2024", "Open", "GBP", 1000, 0, 1000],
        [{"rule": PERIOD, "status": FAIL}],
    ),  # both readings before inception
    (["TB-105", "Rowan Pharmacy", "12/12/2024", "Open", "GBP", 1000, 0, 1000], []),  # reads one way only
]
# Aggregate: latest paid per claim in GBP = 178,000 GBP + EUR (50,000 + 40,000) x 0.85 = 76,500
# + USD 4,000 x 0.85 / 1.08 = 3,148.15 + 5 x 1,000 (ambiguous sheet) = 262,648.15; JPY cannot be
# converted, so the total is a lower bound -- still 12,648.15 over the 250,000 limit.
BINDER_REPORT_LEVEL = [{"rule": "BND_AGGREGATE_EXCEEDED", "status": FAIL, "amount": "12648.15", "currency": "GBP"}]


def _clean(rows: list[tuple[list[Any], list[dict[str, Any]]]]) -> list[list[Any]]:
    out = [HEADER]
    for values, _ in rows:
        v = list(values)
        if isinstance(v[2], dt.datetime) and not dt.datetime(2024, 3, 1) <= v[2] <= dt.datetime(2025, 2, 28):
            v[2] = dt.datetime(2024, 6, 15)
        if v[4] not in ("GBP", "EUR"):
            v[4] = "GBP"
        v[5], v[6], v[7] = min(v[5], 8000), min(v[6], 2000), min(v[5], 8000) + min(v[6], 2000)
        out.append(v)
    return out


def build_binder() -> None:
    folder = HERE / "binder"
    folder.mkdir(exist_ok=True)
    main, exp_main = _split(BINDER_DIRTY_MAIN)
    amb, exp_amb = _split(BINDER_DIRTY_AMBIGUOUS)
    _save(folder / "dirty.xlsx", {"Claims": main, "Ambiguous dates": amb})
    key = {
        "module": "binder",
        "binder": BINDER,
        "fx_per_eur": FX,
        "findings": [
            *({"sheet": "Claims", "row": r, **e} for r, e in exp_main),
            *({"sheet": "Ambiguous dates", "row": r, **e} for r, e in exp_amb),
            *({"sheet": None, "row": None, **e} for e in BINDER_REPORT_LEVEL),
        ],
        "not_assessed_rules_dirty": [],
    }
    (folder / "answer_key.json").write_text(json.dumps(key, indent=2) + "\n", encoding="utf-8")
    clean_main = _clean(BINDER_DIRTY_MAIN)
    _save(folder / "clean.xlsx", {"Claims": clean_main})
    unmapped = [["Claim Reference", "Insured Name", "Col Q", "Claim Status", "Col R", "Paid to Date",
                 "Outstanding Reserve", "Total Incurred"], *main[1:]]  # fmt: skip
    _save(folder / "unmapped.xlsx", {"Claims": unmapped})


# ------------------------------------------------------------------ leakage
LEAK_HEADER = ["Claim Reference", "Insured Name", "Date of Loss", "Claim Status", "Currency", "Reporting Period",
               "Paid This Month", "Paid to Date", "Outstanding Reserve", "Total Incurred"]  # fmt: skip
DUP, NEG, CLOSED, AFTER, DEC = ("LKG_DUPLICATE_PAYMENT", "LKG_NEGATIVE_RESERVE", "LKG_CLOSED_WITH_RESERVE",
                                "LKG_PAID_AFTER_CLOSURE", "LKG_PAID_DECREASED")  # fmt: skip

LEAK_DIRTY: Planted = [
    (["LK-001", "Ash Motors", d(2024, 1, 10), "Open", "GBP", "2024-01", 1000, 1000, 4000, 5000], []),
    (["LK-001", "Ash Motors", d(2024, 1, 10), "Open", "GBP", "2024-02", 500, 1500, 3500, 5000], []),
    (["LK-002", "Beech Care", d(2024, 1, 5), "Open", "GBP", "2024-01", 2000, 2000, 1000, 3000], []),
    (
        ["LK-002", "Beech Care", d(2024, 1, 5), "Open", "GBP", "2024-01", 2000, 2000, 1000, 3000],
        [{"rule": DUP, "status": FAIL, "amount": "2000.00", "currency": "GBP"}],
    ),  # same payment twice
    (
        ["LK-003", "Cork Dental", d(2024, 2, 1), "Open", "GBP", "2024-02", 0, 3000, -500, 2500],
        [{"rule": NEG, "status": FAIL, "amount": "500.00", "currency": "GBP"}],
    ),
    (
        ["LK-004", "Dock Freight", d(2024, 1, 20), "Closed", "GBP", "2024-01", 0, 8000, 1200, 9200],
        [{"rule": CLOSED, "status": FAIL, "amount": "1200.00", "currency": "GBP"}],
    ),
    (["LK-005", "Elder Foods", d(2023, 11, 11), "Closed", "EUR", "2024-01", 0, 6000, 0, 6000], []),
    (
        ["LK-005", "Elder Foods", d(2023, 11, 11), "Closed", "EUR", "2024-02", 750, 6750, 0, 6750],
        [{"rule": AFTER, "status": REVIEW, "amount": "750.00", "currency": "EUR"}],
    ),
    (["LK-006", "Fir Timber", d(2023, 12, 1), "Open", "GBP", "2024-01", 0, 4000, 1000, 5000], []),
    (
        ["LK-006", "Fir Timber", d(2023, 12, 1), "Open", "GBP", "2024-02", 0, 3400, 1000, 4400],
        [{"rule": DEC, "status": REVIEW, "amount": "600.00", "currency": "GBP"}],
    ),
    (["LK-007", "Glen Bakery", d(2024, 2, 14), "Open", "USD", "2024-02", 100, 100, 900, 1000], []),
    (
        ["LK-008", "Holm Print", d(2024, 2, 15), "Open", None, "2024-02", 0, 0, -250, -250],
        [{"rule": NEG, "status": FAIL, "amount": "250.00", "currency": None}],
    ),  # no currency: said so
    (["LK-009", "Ivy Hotels", d(2024, 1, 2), "Closed", "GBP", "Q1 2024", 0, 500, 0, 500], []),
    (["LK-010", "Jet Couriers", d(2024, 3, 3), "Open", "GBP", "2024-03", 300, 300, 700, 1000], []),
]
LEAK_CLEAN_FIX = {  # row index in LEAK_DIRTY -> replacement values (None drops the row)
    3: None,
    4: ["LK-003", "Cork Dental", d(2024, 2, 1), "Open", "GBP", "2024-02", 0, 3000, 500, 3500],
    5: ["LK-004", "Dock Freight", d(2024, 1, 20), "Closed", "GBP", "2024-01", 0, 8000, 0, 8000],
    6: ["LK-005", "Elder Foods", d(2023, 11, 11), "Open", "EUR", "2024-01", 0, 6000, 750, 6750],
    9: ["LK-006", "Fir Timber", d(2023, 12, 1), "Open", "GBP", "2024-02", 400, 4400, 600, 5000],
    11: ["LK-008", "Holm Print", d(2024, 2, 15), "Open", "GBP", "2024-02", 0, 0, 250, 250],
}


def build_leakage() -> None:
    folder = HERE / "leakage"
    folder.mkdir(exist_ok=True)
    data: list[list[Any]] = [LEAK_HEADER]
    expected: list[dict[str, Any]] = []
    for values, expects in LEAK_DIRTY:
        data.append(values)
        expected.extend({"sheet": "Claims", "row": len(data), **e} for e in expects)
    _save(folder / "dirty.xlsx", {"Claims": data})
    key = {"module": "leakage", "findings": expected}
    (folder / "answer_key.json").write_text(json.dumps(key, indent=2) + "\n", encoding="utf-8")
    clean: list[list[Any]] = [LEAK_HEADER]
    for i, (values, _) in enumerate(LEAK_DIRTY):
        fixed = LEAK_CLEAN_FIX.get(i, values)
        if fixed is not None:
            clean.append(fixed)
    _save(folder / "clean.xlsx", {"Claims": clean})
    unmapped = [["Claim Reference", "Insured Name", "Date of Loss", "Col S", "Currency", "Col T", "Paid This Month",
                 "Paid to Date", "Col U", "Total Incurred"], *data[1:]]  # fmt: skip
    _save(folder / "unmapped.xlsx", {"Claims": unmapped})


# ------------------------------------------------------------------ sanctions
# A synthetic list in the UK OFSI consolidated-list CSV layout. Every name is
# invented for this fixture.
OFSI_HEADER = ["Name 6", "Name 1", "Name 2", "Name 3", "Name 4", "Name 5", "Title", "DOB", "Nationality",
               "Group Type", "Alias Type", "Regime", "Group ID"]  # fmt: skip
OFSI_ROWS = [
    ["QUORVANE SHIPPING LTD", "", "", "", "", "", "", "", "", "Entity", "Primary name", "Fixture", "90001"],
    ["Velkaris", "Anatol", "Brenn", "", "", "", "", "01/01/1970", "", "Individual", "Primary name", "Fixture",
     "90002"],
    ["Velkaris", "Tolya", "", "", "", "", "", "01/01/1970", "", "Individual", "AKA", "Fixture", "90002"],
    ["ORSKAYA METALS AG", "", "", "", "", "", "", "", "", "Entity", "Primary name", "Fixture", "90003"],
    ["Draxmoor Holdings", "", "", "", "", "", "", "", "", "Entity", "Primary name", "Fixture", "90004"],
    ["Müller Zentrix GmbH", "", "", "", "", "", "", "", "", "Entity", "Primary name", "Fixture", "90005"],
]  # fmt: skip
EXACT, CLOSE = "SAN_EXACT_MATCH", "SAN_CLOSE_MATCH"
SAN_DIRTY: Planted = [
    (
        ["SN-001", "Quorvane Shipping Limited", d(2024, 5, 1), "Open", "GBP", 100, 0, 100],
        [{"rule": EXACT, "status": REVIEW}],
    ),  # legal form differs only
    (
        ["SN-002", "Velkaris, Anatol Brenn", d(2024, 5, 2), "Open", "GBP", 100, 0, 100],
        [{"rule": EXACT, "status": REVIEW}],
    ),  # word order differs only
    (
        ["SN-003", "Orskaya Metal AG", d(2024, 5, 3), "Open", "GBP", 100, 0, 100],
        [{"rule": CLOSE, "status": REVIEW}],
    ),  # one letter short (96%)
    (["SN-004", "Anatol Bakery", d(2024, 5, 4), "Open", "GBP", 100, 0, 100], []),  # shares a word only
    (["SN-005", "Metals Recycling Ltd", d(2024, 5, 5), "Open", "GBP", 100, 0, 100], []),  # shares a word only
    (["SN-006", "Harbour View Cafe", d(2024, 5, 6), "Open", "GBP", 100, 0, 100], []),
    (
        ["SN-007", "Tolya Velkaris", d(2024, 5, 7), "Open", "GBP", 100, 0, 100],
        [{"rule": EXACT, "status": REVIEW}],
    ),  # an alias
    (
        ["SN-008", "Muller Zentrix", d(2024, 5, 8), "Open", "GBP", 100, 0, 100],
        [{"rule": EXACT, "status": REVIEW}],
    ),  # accent and legal form differ only
    (["SN-009", "Draxmoor Holdings Group", d(2024, 5, 9), "Open", "GBP", 100, 0, 100], []),  # 85%, below 90
    (["SN-010", None, d(2024, 5, 10), "Open", "GBP", 100, 0, 100], []),  # blank: not assessed
    (["SN-011", "Shipping Solutions Ltd", d(2024, 5, 11), "Open", "GBP", 100, 0, 100], []),
]
SAN_CLEAN_NAMES = {0: "Quayside Stores", 1: "Brennan Hardware", 2: "Oakfield Metalwork", 6: "Tollgate Motors",
                   7: "Zenith Gardens", 9: "Northfield Dental"}  # fmt: skip


def build_sanctions() -> None:
    folder = HERE / "sanctions"
    folder.mkdir(exist_ok=True)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["Last Updated", "01/01/2026"])
    w.writerow(OFSI_HEADER)
    w.writerows(OFSI_ROWS)
    (folder / "list_ofsi_format.csv").write_text(buf.getvalue(), encoding="utf-8")
    data, expected = _split(SAN_DIRTY)
    _save(folder / "dirty.xlsx", {"Claims": data})
    key = {"module": "sanctions", "findings": [{"sheet": "Claims", "row": r, **e} for r, e in expected],
           "list_entries": len(OFSI_ROWS), "not_assessed_rows_dirty": 1}  # fmt: skip
    (folder / "answer_key.json").write_text(json.dumps(key, indent=2) + "\n", encoding="utf-8")
    clean = [HEADER]
    for i, (values, _) in enumerate(SAN_DIRTY):
        v = list(values)
        v[1] = SAN_CLEAN_NAMES.get(i, v[1])
        clean.append(v)
    _save(folder / "clean.xlsx", {"Claims": clean})
    unmapped = [["Claim Reference", "Col N", *HEADER[2:]], *data[1:]]
    _save(folder / "unmapped.xlsx", {"Claims": unmapped})


if __name__ == "__main__":
    build_binder()
    build_leakage()
    build_sanctions()
