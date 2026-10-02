"""Phase 4 deliverables: annotated workbook, corrected copy, query letter and
month-on-month check."""

from __future__ import annotations

import io

import openpyxl
from conftest import Api, run_jobs

HEADER = ["Claim Reference", "Insured Name", "Policy Number", "Date of Loss", "Claim Status", "Currency",
          "Paid to Date", "Reserve", "Total Incurred"]


def _book(rows: list[list], title: str | None = "Q3 claims bordereau") -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Claims"
    if title:
        ws.append([title])
    ws.append(HEADER)
    for r in rows:
        ws.append(r)
        for c in ws[ws.max_row]:
            if isinstance(c.value, str) and c.value.startswith("="):
                c.data_type = "s"  # text that merely looks like a formula, as a customer's file can hold
    ws.column_dimensions["B"].width = 33  # layout to keep
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _clean(i: int, **over) -> list:
    row = {"ref": f"CLM-{i:04d}", "name": f"Insured {i}", "pol": f"{100000 + i}", "dol": "2024-01-15",
           "status": "Open", "ccy": "GBP", "paid": 1000, "res": 500, "inc": 1500}
    row.update(over)
    return [row["ref"], row["name"], row["pol"], row["dol"], row["status"], row["ccy"], row["paid"], row["res"],
            row["inc"]]


def _rows() -> list[list]:
    rows = [_clean(i) for i in range(12)]          # sheet rows 3..14
    rows.append(_clean(20, inc=999))               # row 15: arithmetic error in I15
    rows.append(_clean(21, ccy="Euro"))            # row 16: currency written non-standardly (E -> F16)
    rows.append(_clean(22, name="=HYPERLINK(\"http://x\")"))  # row 17: formula-looking text stays text
    rows.append(_clean(23, ref=" CLM-0023 ", dol="03/04/2024"))  # row 18: extra spaces; ambiguous date text
    rows.append(_clean(24, status="Settled", res=0))  # row 19: synonym
    rows.append(_clean(25, pol="12345", dol="15/01/2024"))  # row 20: lost a leading zero; unambiguous date text
    rows.append(["Total", None, None, None, None, None, 18000, 9000, 27000])  # row 21: subtotal row
    return rows


def _run(api: Api, content: bytes, name: str = "book.xlsx") -> str:
    rid, _ = api.full_run(name, content)
    return rid


def _xlsx(api: Api, url: str) -> openpyxl.Workbook:
    r = api.get(url)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats")
    return openpyxl.load_workbook(io.BytesIO(r.content))


def _fill(cell) -> str:
    return (cell.fill.start_color.rgb or "")[-6:] if cell.fill and cell.fill.fill_type == "solid" else ""


def test_annotated_workbook(api: Api):
    original = _book(_rows())
    rid = _run(api, original)
    wb = _xlsx(api, f"/api/v1/reports/{rid}/export/annotated.xlsx")
    assert wb.sheetnames[0] == "Review Summary" and "Issues" in wb.sheetnames and "Claims" in wb.sheetnames
    ws = wb["Claims"]
    src = openpyxl.load_workbook(io.BytesIO(original))["Claims"]
    # Source values are never altered and the layout is kept.
    for row in src.iter_rows():
        for c in row:
            assert ws[c.coordinate].value == c.value, c.coordinate
    assert ws.column_dimensions["B"].width == 33
    assert ws["B17"].data_type == "s" and ws["B17"].value.startswith("=HYPERLINK")
    # Colours: header and subtotal grey, clean cells green, the wrong total red with dark red text and a note.
    assert _fill(ws["A2"]) == "E7E6E6" and _fill(ws["A21"]) == "E7E6E6"
    assert _fill(ws["A3"]) == "E2F0D9" and _fill(ws["I3"]) == "E2F0D9"
    assert _fill(ws["I15"]) == "FFC7CE" and (ws["I15"].font.color.rgb or "").endswith("9C0006")
    assert ws["I15"].comment is not None and "Fix:" in ws["I15"].comment.text
    assert _fill(ws["F16"]) == "FFF2CC" and ws["F16"].comment is not None
    # Review notes column on every claim row.
    notes_col = max(c.column for c in ws[2] if c.value == "Review notes")
    assert ws.cell(row=3, column=notes_col).value == "OK"
    assert "Error" in ws.cell(row=15, column=notes_col).value
    # Issues sheet: grouped, with a link to the cell.
    issues = wb["Issues"]
    links = [c.hyperlink.location for row in issues.iter_rows(min_row=2) for c in row if c.hyperlink]
    assert "'Claims'!I15" in links
    assert any(issues.row_dimensions[r].outline_level == 1 for r in range(2, issues.max_row + 1))
    summary = wb["Review Summary"]
    formulas = [c.value for row in summary.iter_rows() for c in row if isinstance(c.value, str) and c.value.startswith("=")]
    assert any("COUNTIFS(Issues!$B:$B,\"Error\")" in f for f in formulas)
    assert any(c.value == "Legend" for row in summary.iter_rows() for c in row)


def test_corrected_copy_applies_only_safe_fixes(api: Api):
    rid = _run(api, _book(_rows()))
    wb = _xlsx(api, f"/api/v1/reports/{rid}/export/corrected.xlsx")
    log = wb["Change Log"]
    changes = {(r[0].value, r[1].value): (r[2].value, r[3].value, r[4].value) for r in log.iter_rows(min_row=2)
               if r[1].value}
    ws = wb["Claims"]
    assert ws["F16"].value == "EUR" and ("Claims", "F16") in changes
    assert ws["A18"].value == "CLM-0023" and "trimmed" in changes[("Claims", "A18")][2]
    assert ws["E19"].value == "Closed" and "synonym" in changes[("Claims", "E19")][2]
    assert ws["C20"].value == "012345" and "zero-padded" in changes[("Claims", "C20")][2]
    assert ws["D20"].is_date and "real date" in changes[("Claims", "D20")][2]  # 15/01: only one reading
    assert ws["D18"].value == "03/04/2024" and ("Claims", "D18") not in changes  # 3 April or 4 March: left alone
    # Never touched: the arithmetic error, the subtotal row, the formula-looking text.
    assert ws["I15"].value == 999
    assert ws["G21"].value == 18000
    assert ws["B17"].data_type == "s" and ws["B17"].value.startswith("=HYPERLINK")
    assert not any("I15" == k[1] for k in changes)


def test_query_letter_lists_sender_issues_with_cells(api: Api):
    rid = _run(api, _book(_rows()))
    r = api.get(f"/api/v1/reports/{rid}/query-letter")
    assert r.status_code == 200
    letter = r.json()
    assert "Claims!I15" in letter["body"]
    labels = [g["label"] for g in letter["groups"]]
    assert "Total incurred does not reconcile" in labels
    assert "Currency written non-standardly" not in labels  # we fix that ourselves


def test_month_on_month(api: Api):
    before = _run(api, _book([_clean(1), _clean(2), _clean(3, status="Closed", res=0, inc=1000),
                              _clean(4, paid=1000), _clean(5, res=500)], title=None), "june.xlsx")
    after = _run(api, _book([_clean(1), _clean(4, paid=800, inc=1300), _clean(5, res=2000, inc=3000)], title=None),
                 "july.xlsx")
    r = api.get(f"/api/v1/reports/{after}/compare", params={"previous_report_id": before})
    assert r.status_code == 200, r.text
    c = r.json()
    assert [v["claim_ref"] for v in c["vanished"]] == ["CLM-0002"]  # CLM-0003 was closed, so not flagged
    assert [p["claim_ref"] for p in c["paid_down"]] == ["CLM-0004"]
    assert [j["claim_ref"] for j in c["reserve_jump"]] == ["CLM-0005"]
    r = api.get(f"/api/v1/reports/{after}/compare", params={"previous_report_id": before, "reserve_jump_pct": 400})
    assert r.json()["counts"]["reserve_jump"] == 0


def test_deliverables_wait_for_processing(api: Api):
    rid = api.ingest("a.xlsx", _book(_rows()))
    assert api.get(f"/api/v1/reports/{rid}/export/annotated.xlsx").status_code == 409
    run_jobs()


def test_sheet_grid_pages_and_colours(api: Api):
    rid = _run(api, _book(_rows()))
    sheet = next(s for s in api.get(f"/api/v1/reports/{rid}/sheets").json() if s["sheet_name"] == "Claims")
    g = api.get(f"/api/v1/reports/{rid}/sheets/{sheet['id']}/grid", params={"offset": 0, "limit": 100}).json()
    rows = {r["row"]: r for r in g["rows"]}
    assert g["header_row"] == 2 and rows[2]["kind"] == "header" and rows[1]["kind"] == "structural"
    assert rows[3]["kind"] == "claim" and rows[3]["cells"][0]["tone"] == "ok"
    bad = rows[15]["cells"][8]  # I15: wrong total
    assert bad["v"] == "999" and bad["tone"] == "err" and bad["notes"][0]["fix"]
    assert rows[16]["cells"][5]["tone"] == "warn"  # F16: "Euro"
    assert rows[21]["kind"] == "structural"  # subtotal
    assert rows[17]["cells"][1]["v"].startswith("=HYPERLINK")  # shown as text, as received
    page2 = api.get(f"/api/v1/reports/{rid}/sheets/{sheet['id']}/grid", params={"offset": 10, "limit": 5}).json()
    assert [r["row"] for r in page2["rows"]] == [11, 12, 13, 14, 15]
