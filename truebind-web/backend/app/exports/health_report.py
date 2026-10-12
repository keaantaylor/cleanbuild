"""The TrueBind Health Report: one .xlsx built in memory with XlsxWriter.

Sheets, in order (see README.md for how to add one):
Summary · Coverage · Exceptions · Duplicates · Reconciliation · Missing Data ·
Audit Trail · About This Report.

Rules every sheet keeps:
- What was not checked is shown next to what was (the Summary's coverage
  banner sits above every score and count).
- Every colour has its word in the cell (Error / Warning / Couldn't check).
- Text is always written as text: ``strings_to_formulas`` is off, so a value
  such as ``=HYPERLINK(...)`` in a customer's file can never run. The only
  formulas are the ones this module writes with ``write_formula``.
- Formats come from the ``Formats`` cache: one object per distinct style.
"""

from __future__ import annotations

import datetime as dt
import io
from collections import Counter, defaultdict

import xlsxwriter
from bordereaux.rules import RULES, SEVERITY_ORDER
from bordereaux.schema import FIELDS_BY_CODE, REQUIRED_CODES
from xlsxwriter.utility import xl_col_to_name, xl_rowcol_to_cell

from .data import HealthReportData, Issue
from .theme import MAPPING_BUCKET, MAPPING_MEANING, MAPPING_WORD, THEME, TONE, Formats, column_widths, safe_footer_text

TITLE = "TrueBind Health Report"
SHEETS = ("Summary", "Coverage", "Exceptions", "Duplicates", "Reconciliation", "Missing Data", "Audit Trail",
          "About This Report")
STATUS_CHOICES = ["Open", "Queried with sender", "Resolved", "Accepted"]
RESULT_RANK = {"Error": 0, "Warning": 1, "Couldn't check": 2}
MAX_LINKS = 5_000  # internal hyperlinks per list; beyond that the reference is plain text
CHECK_WORD = {
    "MANDATORY_FIELD": "Required data", "ARITHMETIC": "Arithmetic", "DUPLICATE": "Duplicates", "DATE": "Dates",
    "CURRENCY": "Currency", "STATUS": "Claim status", "POLICY": "Policy", "AMOUNT": "Amounts",
    "REFERENCE": "References", "RECONCILIATION": "Reconciliation", "MAPPING_COMPLETENESS": "Mapping",
    "OTHER": "Data type",
}


def _utc(v: dt.datetime | None) -> dt.datetime | None:
    """Excel has no time zones: write UTC wall-clock time, labelled (UTC)."""
    if v is None:
        return None
    if v.tzinfo is not None:
        v = v.astimezone(dt.UTC).replace(tzinfo=None)
    return v


def _text_date(v) -> object:
    if isinstance(v, dt.datetime):
        return _utc(v).strftime("%d-%b-%Y %H:%M")
    if isinstance(v, dt.date):
        return v.strftime("%d-%b-%Y")
    return v


def _plural(n: int, word: str, many: str | None = None) -> str:
    return f"{n:,} {word if n == 1 else (many or word + 's')}"


class _Ctx:
    """Shared state while one workbook is built."""

    def __init__(self, wb, data: HealthReportData) -> None:
        self.wb, self.data, self.f = wb, data, Formats(wb)
        self.issues = sorted(data.issues, key=lambda i: (
            RESULT_RANK.get(i.result, 9), SEVERITY_ORDER.get(i.severity, 9), self.sheet_index(i.sheet),
            i.row or 0, i.rule))
        self.ref = {i.id: f"E-{n:05d}" for n, i in enumerate(self.issues, start=1)}
        self.exc_row = {i.id: n + 1 for n, i in enumerate(self.issues, start=1)}  # 1-based Excel row

    def sheet_index(self, name: str | None) -> int:
        return next((s.index for s in self.data.sheets if s.name == name), 9_999)

    def link_to_issue(self, ws, row: int, col: int, issue: Issue, fmt=None, count: list | None = None) -> None:
        text = self.ref[issue.id]
        if count is not None:
            count[0] += 1
            if count[0] > MAX_LINKS:
                ws.write_string(row, col, text, fmt)
                return
        ws.write_url(row, col, f"internal:'Exceptions'!A{self.exc_row[issue.id]}", fmt or self.f.link(),
                     string=text, tip="Open this finding on the Exceptions sheet")

    def print_setup(self, ws, repeat_row: int | None = None, gridlines: bool = True) -> None:
        ws.set_landscape()
        ws.set_paper(9)  # A4
        ws.fit_to_pages(1, 0)
        ws.set_margins(left=0.4, right=0.4, top=0.5, bottom=0.6)
        if repeat_row is not None:
            ws.repeat_rows(repeat_row)
        ws.set_footer(f"&L&8{safe_footer_text(TITLE)} · {safe_footer_text(self.data.meta.file_name, 80)}"
                      "&R&8Page &P of &N")
        if not gridlines:
            ws.hide_gridlines(2)


def build_health_report(data: HealthReportData) -> bytes:
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False,
                                   "strings_to_numbers": False, "default_date_format": "dd-mmm-yyyy"})
    m = data.meta
    wb.set_properties({
        "title": f"{TITLE}: {m.file_name}", "subject": "Bordereau validation report", "author": "TrueBind",
        "company": "TrueBind", "manager": m.exported_by, "category": "Bordereau health report",
        "keywords": "TrueBind, bordereau, validation", "comments": f"Run ID {m.report_id}",
        "created": _utc(m.exported_at)})
    ctx = _Ctx(wb, data)
    sheets = {name: wb.add_worksheet(name) for name in SHEETS}
    _summary(ctx, sheets["Summary"])
    _coverage(ctx, sheets["Coverage"])
    _exceptions(ctx, sheets["Exceptions"])
    _duplicates(ctx, sheets["Duplicates"])
    _reconciliation(ctx, sheets["Reconciliation"])
    _missing(ctx, sheets["Missing Data"])
    _audit(ctx, sheets["Audit Trail"])
    _about(ctx, sheets["About This Report"])
    sheets["Summary"].activate()
    sheets["Summary"].set_first_sheet()
    wb.close()
    return buf.getvalue()


# ------------------------------------------------------------------ figures shared by sheets

def coverage_figures(data: HealthReportData) -> dict:
    s = data.summary
    hv = data.health_view
    buckets = Counter(MAPPING_BUCKET.get(c.state, "none") for c in data.columns)
    remembered = sum(1 for c in data.columns if c.state in ("MAPPED_BY_MEMORY", "MANUAL"))
    rec = s.get("reconciliation") or {}
    rows_total = int(rec.get("source_data_rows") or sum(x.source_rows for x in data.sheets))
    rows_read = sum(x.claim_rows for x in data.sheets) + sum(x.excluded_rows for x in data.sheets
                                                            if x.status == "CONFIRMED")
    sheets_total = int(s.get("sheets_total") or len(data.sheets))
    sheets_read = int(s.get("sheets_processed") or sum(1 for x in data.sheets if x.status == "CONFIRMED"))
    couldnt = hv.get("couldnt_check") or []
    complete = (sheets_read >= sheets_total and buckets["none"] == 0 and not couldnt and rows_read >= rows_total)
    return {"sheets_read": sheets_read, "sheets_total": sheets_total, "rows_read": min(rows_read, rows_total),
            "rows_total": rows_total, "alias": buckets["alias"], "ai": buckets["ai"], "none": buckets["none"],
            "remembered": remembered, "couldnt": couldnt, "complete": complete,
            "pct": (100.0 * min(rows_read, rows_total) / rows_total) if rows_total else 0.0}


def _money_by_currency(data: HealthReportData, issues: list[Issue]) -> dict[str, float]:
    seen: set[str] = set()
    out: dict[str, float] = defaultdict(float)
    for i in issues:
        if i.claim_row_id in seen or i.claim.incurred is None:
            continue
        seen.add(i.claim_row_id)
        out[(i.claim.currency or "").strip().upper() or "(none)"] += abs(i.claim.incurred)
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def _money_text(amounts: dict[str, float]) -> str:
    if not amounts:
        return "None calculable"
    sym = {"GBP": "£", "EUR": "€", "USD": "$"}
    parts = []
    for c, v in list(amounts.items())[:3]:
        parts.append(f"{sym[c]}{v:,.0f}" if c in sym else f"{c} {v:,.0f}")
    if len(amounts) > 3:
        parts.append(f"+{len(amounts) - 3} more")
    return "\n".join(parts)


# ------------------------------------------------------------------ 1. Summary

def _summary(ctx: _Ctx, ws) -> None:
    f, d, m = ctx.f, ctx.data, ctx.data.meta
    s, hv = d.summary, d.health_view
    ctx.print_setup(ws, gridlines=False)
    ws.set_column(0, 0, 2)
    ws.set_column(1, 12, 12.5)
    ws.set_column(13, 13, 2)
    band = f.get(bg_color=THEME["ink"], font_color=THEME["ink_text"], font_size=20, bold=True, valign="vcenter",
                 indent=1)
    sub = f.get(bg_color=THEME["ink"], font_color=THEME["mint"], font_size=11, valign="vcenter", indent=1)
    ws.set_row(0, 8)
    ws.set_row(1, 36)
    ws.merge_range(1, 1, 1, 12, TITLE, band)
    ws.set_row(2, 20)
    ws.merge_range(2, 1, 2, 12, m.file_name, sub)

    label = f.get(font_color=THEME["muted"], font_size=9)
    value = f.get(bold=True)
    vdate = f.datetime(bold=True)
    left = [("Source file", m.file_name), ("Sender", m.sender or "Not given"),
            ("Programme", m.programme or "Not given"),
            ("Reporting period", ", ".join(m.reporting_periods[:4]) + (" …" if len(m.reporting_periods) > 4 else "")
             if m.reporting_periods else "Not detected")]
    right = [("Processed (UTC)", _utc(m.processed_at)), ("Run ID", m.report_id),
             ("Uploaded by", m.uploaded_by or "Not recorded"),
             ("Exported (UTC)", f"{_utc(m.exported_at):%d-%b-%Y %H:%M} by {m.exported_by}")]
    for n, ((ll, lv), (rl, rv)) in enumerate(zip(left, right)):
        r = 4 + n
        ws.merge_range(r, 1, r, 2, ll, label)
        ws.merge_range(r, 3, r, 6, lv, value)
        ws.merge_range(r, 8, r, 9, rl, label)
        if isinstance(rv, dt.datetime):
            ws.merge_range(r, 10, r, 12, "", vdate)
            ws.write_datetime(r, 10, rv, vdate)
        else:
            ws.merge_range(r, 10, r, 12, rv if rv is not None else "Not recorded", value)

    # Coverage banner: above every number, impossible to miss.
    cov = coverage_figures(d)
    tone = "pass" if cov["complete"] else "warning"
    fill, ink = THEME[tone]
    head = f.get(bg_color=fill, font_color=ink, bold=True, font_size=12, valign="vcenter", indent=1,
                 top=2, top_color=ink)
    big = f.get(bg_color=fill, font_color=THEME["ink"], bold=True, font_size=15, valign="vcenter", indent=1)
    cap = f.get(bg_color=fill, font_color=ink, font_size=9, valign="top", indent=1, text_wrap=True)
    stmt = f.get(bg_color=fill, font_color=ink, font_size=10, valign="vcenter", indent=1, text_wrap=True,
                 bottom=2, bottom_color=ink)
    r = 9
    ws.set_row(r, 22)
    ws.merge_range(r, 1, r, 12, "COVERAGE: " + ("everything in the file was read and every check ran" if cov["complete"]
                                                 else "Couldn't check everything. See the Coverage sheet"), head)
    ws.set_row(r + 1, 24)
    ws.set_row(r + 2, 26)
    tiles = [
        (f"{cov['sheets_read']} of {cov['sheets_total']}", "Sheets read"),
        (f"{cov['rows_read']:,} of {cov['rows_total']:,}", "Rows read (claim rows and structural rows)"),
        (f"{cov['alias']:,} · {cov['ai']:,} · {cov['none']:,}",
         "Columns mapped by alias · mapped by AI · couldn't map"
         + (f" (alias includes {cov['remembered']} remembered or set by hand)" if cov["remembered"] else "")),
        (str(len(cov["couldnt"])), "Checks that couldn't run (Couldn't check)"),
    ]
    for n, (v, c) in enumerate(tiles):
        c0 = 1 + n * 3
        ws.merge_range(r + 1, c0, r + 1, c0 + 2, v, big)
        ws.merge_range(r + 2, c0, r + 2, c0 + 2, c, cap)
    unread = cov["sheets_total"] - cov["sheets_read"]
    if cov["complete"]:
        text = s.get("coverage_statement") or "All sheets, rows and columns were read; every check ran."
    else:
        bits = []
        if unread:
            bits.append(_plural(unread, "sheet") + " not read")
        if cov["none"]:
            bits.append(_plural(cov["none"], "column") + " couldn't be mapped, so no check used them")
        if cov["couldnt"]:
            bits.append(_plural(len(cov["couldnt"]), "check") + " couldn't run on some or all rows")
        if cov["rows_read"] < cov["rows_total"]:
            bits.append(f"{cov['rows_total'] - cov['rows_read']:,} rows not read")
        text = "Couldn't check: " + "; ".join(bits) + ". The counts below cover only what was read: see Coverage."
    ws.set_row(r + 3, 30)
    ws.merge_range(r + 3, 1, r + 3, 12, text, stmt)

    # KPI tiles.
    counts = hv.get("counts") or {}
    errors_list = [i for i in d.issues if i.result == "Error"]
    total_rows = int(s.get("total_claims") or sum(x.claim_rows for x in d.sheets))
    dup_rows = len({i.claim_row_id for i in d.issues if i.check_type == "DUPLICATE"}
                   | {i.match_claim_row_id for i in d.issues if i.check_type == "DUPLICATE" and i.match_claim_row_id})
    dups = hv.get("duplicates") or {}
    score_v = f"{d.score:.0f} / 100" if d.score is not None else "Not scored"
    score_cap = (f"Grade {d.grade} of 5. " if d.grade else "") + (
        f"On {cov['pct']:.0f}% of rows and {cov['sheets_read']} of {cov['sheets_total']} sheets")
    if s.get("score_reliable") is False:
        score_cap += ". Not reliable: too little was checked"
    kpis = [
        (score_v, "Overall health score", score_cap, "neutral"),
        (f"{total_rows:,}", "Total claim rows", f"Across {cov['sheets_read']} sheets read", "neutral"),
        (f"{int(counts.get('errors', len(errors_list))):,}", "Errors",
         f"On {int(counts.get('error_rows', 0)):,} rows. Must be fixed", "error"),
        (f"{int(counts.get('warnings', 0)):,}", "Warnings", "Unusual values to review", "warning"),
        (f"{dup_rows:,}", "Rows in duplicate pairs",
         f"{int(dups.get('exact_pairs') or 0):,} exact · "
         + (f"{int(dups['probable_pairs']):,} probable" if dups.get("probable_pairs") is not None
            else "probable: couldn't check"), "neutral"),
        (f"{int(s.get('arithmetic_mismatches') or 0):,}", "Arithmetic mismatches",
         f"{int(s.get('arithmetic_matches') or 0):,} reconcile · "
         f"{int(s.get('arithmetic_not_evaluable') or 0):,} couldn't check", "neutral"),
        (f"{int(s.get('missing_mandatory_rows') or 0):,}", "Rows missing mandatory data",
         "Distinct rows; one row can miss several fields", "neutral"),
        (_money_text(_money_by_currency(d, errors_list)), "Value affected",
         "Total incurred on rows with an error, per currency", "neutral"),
    ]
    r = 15
    ws.merge_range(r, 1, r, 12, "Results", f.section())
    for n, (v, lab, c, tone) in enumerate(kpis):
        row = r + 2 + (n // 4) * 4
        c0 = 1 + (n % 4) * 3
        fill, ink = THEME[tone] if tone != "neutral" else (THEME["band"], THEME["ink"])
        vf = f.get(bg_color=fill, font_color=ink, bold=True, font_size=11 if "\n" in v else 18,
                   valign="vcenter", indent=1,
                   text_wrap=True, left=5, left_color=ink if tone != "neutral" else THEME["accent"])
        lf = f.get(bg_color=fill, font_color=ink, bold=True, font_size=10, indent=1,
                   left=5, left_color=ink if tone != "neutral" else THEME["accent"])
        cf = f.get(bg_color=fill, font_color=THEME["muted"] if tone == "neutral" else ink, font_size=8.5, indent=1,
                   text_wrap=True, left=5, left_color=ink if tone != "neutral" else THEME["accent"])
        ws.set_row(row, 38 if "\n" not in v else 52)
        ws.set_row(row + 2, 24)
        ws.merge_range(row, c0, row, c0 + 2, v, vf)
        ws.merge_range(row + 1, c0, row + 1, c0 + 2, lab, lf)
        ws.merge_range(row + 2, c0, row + 2, c0 + 2, c, cf)

    # Top 10.
    r = 26
    ws.set_h_pagebreaks([r - 1])
    ws.merge_range(r, 1, r, 12, "Top 10 issues to fix first", f.section())
    ws.merge_range(r + 1, 1, r + 1, 12, "Errors before warnings, most serious first, then by the amount on the "
                                         "row. Click a reference to open it on the Exceptions sheet.", f.note())
    head = ["Ref", "Result", "Check", None, "Sheet", "Row", "Claim ref", "Incurred", "What we found"]
    hr = r + 2
    hfmt = f.header()
    ws.write_row(hr, 1, ["Ref", "Result", "Check"], hfmt)
    ws.write_blank(hr, 4, None, hfmt)
    ws.merge_range(hr, 3, hr, 4, "Check", hfmt)
    ws.write_row(hr, 5, head[4:8], hfmt)
    ws.merge_range(hr, 9, hr, 12, "What we found", hfmt)
    top = sorted(ctx.issues, key=lambda i: (RESULT_RANK.get(i.result, 9), SEVERITY_ORDER.get(i.severity, 9),
                                            -abs(i.claim.incurred or 0.0)))[:10]
    wrap = f.wrap()
    for n, i in enumerate(top):
        row = hr + 1 + n
        ws.set_row(row, 26)
        ctx.link_to_issue(ws, row, 1, i)
        ws.write_string(row, 2, i.result, f.status(TONE.get(i.result, "na")))
        ws.merge_range(row, 3, row, 4, i.label, wrap)
        ws.write(row, 5, i.sheet or "", wrap)
        ws.write(row, 6, i.row, f.get(num_format="0", align="center"))
        ws.write(row, 7, i.claim.claim_ref or "", f.text())
        if i.claim.incurred is not None:
            ws.write_number(row, 8, i.claim.incurred, f.money(i.claim.currency))
        else:
            ws.write_blank(row, 8, None)
        ws.merge_range(row, 9, row, 12, i.sentence, wrap)
    if not top:
        ws.merge_range(hr + 1, 1, hr + 1, 12, "No findings. Nothing to fix in what was read.", f.note())

    # Charts and the tables they read (visible, so a reader can check them).
    r = hr + 12
    ws.merge_range(r, 1, r, 6, "Issues by sheet", f.section())
    ws.merge_range(r, 7, r, 12, "Issues by check type", f.section())
    by_sheet: dict[str, Counter] = defaultdict(Counter)
    by_check: dict[str, Counter] = defaultdict(Counter)
    for i in d.issues:
        by_sheet[i.sheet or "(no sheet)"][i.result] += 1
        by_check[CHECK_WORD.get(i.check_type, i.check_type.title())][i.result] += 1
    sheet_names = sorted(by_sheet, key=ctx.sheet_index)
    check_names = sorted(by_check, key=lambda k: -sum(by_check[k].values()))
    tr = r + 19
    words = ("Error", "Warning", "Couldn't check")
    for col0, title, names, counts_by in ((1, "Sheet", sheet_names, by_sheet), (7, "Check", check_names, by_check)):
        ws.merge_range(tr, col0, tr, col0 + 1, title, hfmt)
        ws.write_row(tr, col0 + 2, ["Errors", "Warnings", "Couldn't check"], hfmt)
        for n, name in enumerate(names):
            ws.merge_range(tr + 1 + n, col0, tr + 1 + n, col0 + 1, name, f.text())
            ws.write_row(tr + 1 + n, col0 + 2, [counts_by[name][k] for k in words], f.int())
    colours = {"Error": "#B91C1C", "Warning": "#F59E0B", "Couldn't check": "#94A3B8"}
    for kind, names, col0, anchor in (("bar", sheet_names, 1, "B"), ("column", check_names, 7, "H")):
        if not names:
            ws.write_string(r + 2, col0, "No findings to chart.", f.note())
            continue
        chart = ctx.wb.add_chart({"type": kind, "subtype": "stacked"})
        for k, (word, colour) in enumerate(colours.items()):
            chart.add_series({
                "name": ["Summary", tr, col0 + 2 + k],
                "categories": ["Summary", tr + 1, col0, tr + len(names), col0],
                "values": ["Summary", tr + 1, col0 + 2 + k, tr + len(names), col0 + 2 + k],
                "fill": {"color": colour}, "border": {"color": "#FFFFFF", "width": 0.5}, "gap": 60,
            })
        chart.set_legend({"position": "bottom", "font": {"name": THEME["font"], "size": 9}})
        chart.set_chartarea({"border": {"none": True}})
        chart.set_plotarea({"border": {"none": True}})
        axis_font = {"name": THEME["font"], "size": 9, "color": THEME["muted"]}
        chart.set_x_axis({"num_font": axis_font, "major_gridlines": {"visible": kind == "bar",
                                                                      "line": {"color": "#E2E8F0"}}})
        chart.set_y_axis({"num_font": axis_font, "reverse": kind == "bar",
                          "major_gridlines": {"visible": kind == "column", "line": {"color": "#E2E8F0"}}})
        chart.set_title({"none": True})
        chart.set_size({"width": 6 * 88, "height": 340})
        ws.insert_chart(f"{anchor}{r + 2}", chart, {"x_offset": 2, "y_offset": 4, "object_position": 1})
    end = tr + 2 + max(len(sheet_names), len(check_names))
    ws.merge_range(end, 1, end, 12, "How to read this file, what each check means and what the colours mean: see "
                                     "the About This Report sheet.", f.note())
    ws.print_area(0, 0, end, 13)


# ------------------------------------------------------------------ 2. Coverage

def _sheet_word(s, audit: dict) -> tuple[str, str]:
    a = audit.get(s.name) or {}
    if a.get("status") == "unmapped":
        return "Couldn't map", "na"
    if a.get("status") == "non_claim_summary":
        return "Summary sheet, not claims", "info"
    if s.status == "CONFIRMED":
        return "Read", "pass"
    if s.status == "SKIPPED":
        return "Not read (skipped)", "na"
    return "Not read", "na"


def _coverage(ctx: _Ctx, ws) -> None:
    f, d = ctx.f, ctx.data
    ctx.print_setup(ws)
    ws.write_string(0, 0, "Coverage: what was read and what wasn't", f.get(bold=True, font_size=16))
    ws.write_string(1, 0, "Every sheet and every source column, with what it was mapped to. Grey rows were not "
                          "checked; the note says what that means.", f.note())
    audit = {a["sheet_name"]: a for a in d.summary.get("sheet_audit") or []}
    r = 3
    ws.write_string(r, 0, "Sheets", f.section())
    head = ["Sheet", "Read?", "Claim rows", "Structural rows excluded", "Rows in sheet"]
    ws.write_row(r + 1, 0, head, f.header())
    ws.merge_range(r + 1, 5, r + 1, 8, "Notes", f.header())
    for n, s in enumerate(d.sheets):
        row = r + 2 + n
        word, tone = _sheet_word(s, audit)
        ws.write_string(row, 0, s.name, f.status("na", bold=False) if tone == "na" else f.text())
        ws.write_string(row, 1, word, f.status(tone))
        ws.write_number(row, 2, s.claim_rows, f.int())
        ws.write_number(row, 3, s.excluded_rows, f.int())
        ws.write_number(row, 4, s.source_rows, f.int())
        note = s.skip_reason or (audit.get(s.name) or {}).get("reason") or ""
        if tone == "na" and not note:
            note = "Not read, so none of its rows were checked."
        ws.merge_range(row, 5, row, 8, note, f.wrap(indent=1))
    r = r + 3 + len(d.sheets)

    ws.write_string(r, 0, "Columns", f.section())
    head = ["Sheet", "Column", "Source heading", "Mapped to field", "Mapping state", "Confidence", "Confirmed by",
            "Confirmed (UTC)", "What this means"]
    hr = r + 1
    ws.write_row(hr, 0, head, f.header())
    ws.freeze_panes(hr + 1, 0)
    ws.repeat_rows(hr)
    for n, c in enumerate(d.columns):
        row = hr + 1 + n
        grey = c.state == "UNMAPPED"
        base = f.status("na", bold=False) if grey else f.text()
        ws.write_string(row, 0, c.sheet, base)
        ws.write_string(row, 1, c.letter, base)
        ws.write_string(row, 2, c.source_column, base)
        ws.write_string(row, 3, c.field_name or "Not mapped", base)
        tone = "na" if grey else "info" if c.state == "MAPPED_BY_AI" else "pass"
        ws.write_string(row, 4, MAPPING_WORD.get(c.state, c.state), f.status(tone))
        if c.confidence is not None:
            conf = c.confidence / 100 if c.confidence > 1 else c.confidence
            ws.write_number(row, 5, conf, f.get(num_format="0%", align="right"))
        else:
            ws.write_blank(row, 5, None, base)
        ws.write_string(row, 6, c.confirmed_by or "", base)
        if c.confirmed_at:
            ws.write_datetime(row, 7, _utc(c.confirmed_at), f.datetime())
        else:
            ws.write_blank(row, 7, None, base)
        meaning = ("Couldn't check: no check used this column. Its values are kept with each row (see the "
                   "unmapped values in the claims export)." if grey else
                   f"Matched by the AI model ({c.ai_model})." if c.state == "MAPPED_BY_AI" and c.ai_model else
                   MAPPING_MEANING.get(c.state, ""))
        ws.write_string(row, 8, meaning, f.wrap(**({"bg_color": THEME["na"][0]} if grey else {})))
    last = hr + max(1, len(d.columns))
    if not d.columns:
        ws.write_string(hr + 1, 0, "No sheet was read, so no column was mapped.", f.note())
    ws.autofilter(hr, 0, last, len(head) - 1)
    rows = [[c.sheet, c.letter, c.source_column, c.field_name, MAPPING_WORD.get(c.state), None, c.confirmed_by,
             "dd-mmm-yyyy hh:mm", "x" * 50] for c in d.columns]
    for i, w in enumerate(column_widths(rows, head, cap=48)):
        ws.set_column(i, i, w)
    ws.set_column(5, 5, 11)
    ws.set_column(8, 8, 60)
    r = last + 2

    gaps = sorted(d.field_gaps, key=lambda g: (ctx.sheet_index(g.sheet), not g.required, g.field_name))
    ws.write_string(r, 0, "Fields with no column on a sheet that was read", f.section())
    ws.write_row(r + 1, 0, ["Sheet", "Field", "Required?", "Effect"], f.header())
    for n, g in enumerate(gaps):
        row = r + 2 + n
        ws.write_string(row, 0, g.sheet, f.status("na", bold=False))
        ws.write_string(row, 1, g.field_name, f.status("na", bold=False))
        ws.write_string(row, 2, "Required" if g.required else "Optional", f.status("na", bold=g.required))
        ws.write_string(row, 3, ("Couldn't check: every row on this sheet is treated as missing this required field."
                                 if g.required else "Couldn't check: checks that use this field did not run on "
                                 "this sheet."), f.wrap(bg_color=THEME["na"][0]))
    if not gaps:
        ws.write_string(r + 2, 0, "None. Every field had a column on every sheet that was read.", f.note())
    r = r + 3 + max(1, len(gaps))

    couldnt = d.health_view.get("couldnt_check") or []
    ws.write_string(r, 0, "Checks that couldn't run", f.section())
    ws.write_row(r + 1, 0, ["Check", "Couldn't check because", "Rows affected", "How to fix"], f.header())
    for n, c in enumerate(couldnt):
        row = r + 2 + n
        ws.write_string(row, 0, c.get("label") or "", f.status("na"))
        ws.write_string(row, 1, c.get("reason") or "", f.wrap())
        if c.get("rows") is not None:
            ws.write_number(row, 2, int(c["rows"]), f.int())
        else:
            ws.write_string(row, 2, "All rows", f.text())
        ws.write_string(row, 3, "Map the missing column on the mapping screen, then re-run."
                        if c.get("fix") == "mapping" else "Ask the sender to provide or correct the values.", f.wrap())
    if not couldnt:
        ws.write_string(r + 2, 0, "None. Every check ran on every row that was read.", f.note())


# ------------------------------------------------------------------ 3. Exceptions

EXC_HEAD = ["Ref", "Severity", "Priority", "Check", "Sheet", "Source row", "Cell", "Claim reference", "Column",
            "Field", "Value found", "Expected / rule", "Explanation", "Suggested fix", "Who fixes", "Status",
            "Owner", "Notes"]


def _exceptions(ctx: _Ctx, ws) -> None:
    f = ctx.f
    ctx.print_setup(ws, repeat_row=0)
    rows = []
    for i in ctx.issues:
        expected = i.expected if i.expected is not None else i.label
        # None, not "": an empty cell costs nothing to write; an empty string is a cell.
        rows.append([ctx.ref[i.id], i.result, i.priority, i.label, i.sheet, i.row, i.cell, i.claim.claim_ref,
                     i.column, i.field_name, _text_date(i.value_found), _text_date(expected), i.sentence, i.fix,
                     i.owner, i.status, i.assignee or None, i.note or None])
    n = len(rows)
    if not n:
        rows = [["", "", "", "No findings", "", None, "", "", "", "", "", "", "Nothing was flagged in what was read. "
                 "See Coverage for anything that couldn't be checked.", "", "", "", "", ""]]
    widths = column_widths(rows, EXC_HEAD, cap=55)
    wrap = f.wrap()
    col_fmt = {"Source row": f.int(), "Explanation": wrap, "Suggested fix": wrap, "Notes": wrap,
               "Value found": f.get(num_format="#,##0.00", align="left"),
               "Expected / rule": f.get(num_format="#,##0.00", align="left", text_wrap=True)}
    edit = f.get(bg_color="#FFFFFF", border=1, border_color=THEME["line"])
    col_fmt.update({"Status": edit, "Owner": edit})
    fmts = [col_fmt.get(h, f.text()) for h in EXC_HEAD]
    # Rows are written with typed calls and empty cells are skipped (they take
    # the column's format from set_column below); the table is laid over them.
    for r, row in enumerate(rows, start=1):
        for c, v in enumerate(row):
            if v is None:
                continue
            if isinstance(v, str):
                ws.write_string(r, c, v, fmts[c])
            else:
                ws.write_number(r, c, v, fmts[c])
    ws.add_table(0, 0, len(rows), len(EXC_HEAD) - 1, {
        "name": "Exceptions", "style": "Table Style Light 1", "autofilter": True,
        "columns": [{"header": h, "header_format": f.header()} for h in EXC_HEAD]})
    ws.freeze_panes(1, 2)
    ws.set_row(0, 30)
    for i, w in enumerate(widths):
        ws.set_column(i, i, w, fmts[i])
    for name, w in (("Explanation", 60), ("Suggested fix", 48), ("Notes", 30), ("Expected / rule", 24),
                    ("Status", 20), ("Owner", 16)):
        c = EXC_HEAD.index(name)
        ws.set_column(c, c, w, col_fmt.get(name))
    last = max(1, len(rows))
    sev = EXC_HEAD.index("Severity")
    for word, tone in TONE.items():
        ws.conditional_format(1, sev, last, sev, {"type": "text", "criteria": "begins with", "value": word,
                                                  "format": f.status_dxf(tone)})
    st = EXC_HEAD.index("Status")
    ws.data_validation(1, st, max(last, 1000) if n else 1, st, {
        "validate": "list", "source": STATUS_CHOICES, "error_type": "warning",
        "input_title": "Status", "input_message": "Open, Queried with sender, Resolved or Accepted.",
        "error_title": "Status", "error_message": "Choose Open, Queried with sender, Resolved or Accepted."})
    for word, tone in (("Resolved", "pass"), ("Accepted", "info"), ("Queried with sender", "warning")):
        ws.conditional_format(1, st, last, st, {"type": "cell", "criteria": "==", "value": f'"{word}"',
                                                "format": f.status_dxf(tone)})


# ------------------------------------------------------------------ 4. Duplicates

def _duplicate_groups(ctx: _Ctx) -> list[list[tuple[str, Issue | None]]]:
    """Union of duplicate pairs into groups of claim rows; each member carries
    the finding that flagged it (the partner row has none of its own)."""
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    flagged: dict[str, Issue] = {}
    for i in ctx.data.issues:
        if i.check_type != "DUPLICATE":
            continue
        flagged.setdefault(i.claim_row_id, i)
        find(i.claim_row_id)
        if i.match_claim_row_id:
            parent[find(i.match_claim_row_id)] = find(i.claim_row_id)
    groups: dict[str, list[str]] = defaultdict(list)
    for x in list(parent):
        groups[find(x)].append(x)

    def pos(cid: str):
        c = ctx.data.claims.get(cid)
        return (ctx.sheet_index(c.sheet if c else None), (c.row if c else 0) or 0)

    out = [[(cid, flagged.get(cid)) for cid in sorted(members, key=pos)] for members in groups.values()]
    out.sort(key=lambda g: pos(g[0][0]))
    return out


def _duplicates(ctx: _Ctx, ws) -> None:
    f, d = ctx.f, ctx.data
    head = ["Group", "Match", "Confidence", "Sheet", "Source row", "Claim reference", "Insured", "Policy",
            "Date of loss", "Currency", "Total incurred", "Matched on", "Suggestion", "Finding"]
    ctx.print_setup(ws, repeat_row=0)
    ws.write_row(0, 0, head, f.header())
    ws.set_row(0, 30)
    ws.freeze_panes(1, 1)
    groups = _duplicate_groups(ctx)
    row, links = 1, [0]
    rows_for_width = []
    for g, members in enumerate(groups, start=1):
        shade = {"bg_color": THEME["band"]} if g % 2 == 0 else {}
        kinds = {i.rule for _, i in members if i}
        exact = "exact_duplicate" in kinds
        conf = max((i.match_confidence or 0 for _, i in members if i), default=0)
        for k, (cid, issue) in enumerate(members):
            c = d.claims.get(cid)
            if c is None:
                continue
            match = "Exact" if exact else "Probable" if "probable_duplicate" in kinds else "Repeat (no period)"
            suggestion = ("Keep" if k == 0 else "Remove: exact copy of the kept row" if exact
                          else "Review with the sender before removing")
            vals = [f"D-{g:04d}", match]
            ws.write_string(row, 0, vals[0], f.text(bold=True, **shade))
            ws.write_string(row, 1, match, f.status("error" if exact else "warning") if k == 0
                            else f.text(**shade))
            if conf and not exact:
                ws.write_number(row, 2, conf / 100, f.get(num_format="0%", align="right", **shade))
            else:
                ws.write_blank(row, 2, None, f.text(**shade))
            ws.write_string(row, 3, c.sheet or "", f.text(**shade))
            ws.write(row, 4, c.row, f.int(**shade))
            ws.write_string(row, 5, c.claim_ref or "", f.text(**shade))
            ws.write_string(row, 6, c.insured or "", f.text(**shade))
            ws.write_string(row, 7, c.policy_ref or "", f.text(**shade))
            if c.date_of_loss:
                ws.write_datetime(row, 8, dt.datetime.combine(c.date_of_loss, dt.time()), f.date(**shade))
            else:
                ws.write_blank(row, 8, None, f.text(**shade))
            ws.write_string(row, 9, c.currency or "", f.text(**shade))
            if c.incurred is not None:
                ws.write_number(row, 10, c.incurred, f.money(c.currency, **shade))
            else:
                ws.write_blank(row, 10, None, f.text(**shade))
            ws.write_string(row, 11, (issue.message if issue else "Partner row of the pair above"), f.wrap(**shade))
            ws.write_string(row, 12, suggestion, f.text(bold=k == 0, **shade))
            if issue:
                ctx.link_to_issue(ws, row, 13, issue, f.link(**shade), links)
            else:
                ws.write_blank(row, 13, None, f.text(**shade))
            rows_for_width.append([vals[0], match, None, c.sheet, c.row, c.claim_ref, c.insured, c.policy_ref,
                                   "dd-mmm-yyyy", c.currency, c.incurred, None, suggestion, "E-00000"])
            row += 1
    if not groups:
        ws.write_string(1, 0, "No duplicates were found." + (
            "" if (d.health_view.get("duplicates") or {}).get("probable_pairs") is not None else
            " Couldn't check probable duplicates: see Coverage."), f.note())
    ws.autofilter(0, 0, max(row - 1, 1), len(head) - 1)
    for i, w in enumerate(column_widths(rows_for_width, head, cap=40)):
        ws.set_column(i, i, w)
    ws.set_column(11, 11, 56)


# ------------------------------------------------------------------ 5. Reconciliation

def _reconciliation(ctx: _Ctx, ws) -> None:
    f, s = ctx.f, ctx.data.summary
    ctx.print_setup(ws, repeat_row=4)
    ws.write_string(0, 0, "Reconciliation: arithmetic checks", f.get(bold=True, font_size=16))
    ws.merge_range(1, 0, 1, 10, f"{int(s.get('arithmetic_matches') or 0):,} rows reconcile · "
                                f"{int(s.get('arithmetic_mismatches') or 0):,} don't · "
                                f"{int(s.get('arithmetic_not_evaluable') or 0):,} couldn't check (see Exceptions). "
                                "Difference = Reported − Expected, calculated live in this sheet.", f.note())
    head = ["Ref", "Sheet", "Source row", "Claim reference", "Check", "Currency", "Paid to date", "Reserve",
            "Fees paid to date", "Fees reserve", "Calculation", "Expected", "Reported", "Difference"]
    hr = 4
    ws.write_row(hr, 0, head, f.header())
    ws.set_row(hr, 30)
    ws.freeze_panes(hr + 1, 1)
    items = [i for i in ctx.issues if i.check_type == "ARITHMETIC" and i.result != "Couldn't check"]
    links = [0]
    for n, i in enumerate(items):
        row = hr + 1 + n
        c = i.claim
        ccy = (c.currency or "").strip().upper() or "(none)"
        money = f.money(c.currency)
        ctx.link_to_issue(ws, row, 0, i, count=links)
        ws.write_string(row, 1, i.sheet or "", f.text())
        ws.write(row, 2, i.row, f.int())
        ws.write_string(row, 3, c.claim_ref or "", f.text())
        ws.write_string(row, 4, i.label, f.wrap())
        ws.write_string(row, 5, ccy, f.text())
        for col, v in ((6, c.paid), (7, c.reserve), (8, c.fees_paid), (9, c.fees_reserve)):
            if v is not None:
                ws.write_number(row, col, v, money)
        ws.write_string(row, 10, i.message, f.wrap())
        exp = i.expected if isinstance(i.expected, float) else None
        act = i.actual if isinstance(i.actual, float) else None
        if exp is not None:
            ws.write_number(row, 11, exp, money)
        if act is not None:
            ws.write_number(row, 12, act, money)
        e, a = xl_rowcol_to_cell(row, 11), xl_rowcol_to_cell(row, 12)
        ws.write_formula(row, 13, f"=IF(AND(ISNUMBER({a}),ISNUMBER({e})),{a}-{e},\"\")", money,
                         (act - exp) if exp is not None and act is not None else "")
    last = hr + max(1, len(items))
    if not items:
        ws.write_string(hr + 1, 0, "No arithmetic mismatches in what was read.", f.note())
    ws.conditional_format(hr + 1, 13, last, 13, {"type": "cell", "criteria": "!=", "value": 0,
                                                 "format": f.status_dxf("error")})
    ws.autofilter(hr, 0, last, len(head) - 1)
    # Totals per currency, as live formulas (never added across currencies).
    r = last + 2
    ws.write_string(r, 0, "Totals by currency", f.section())
    ws.write_row(r + 1, 4, ["Rows", "Currency", "Paid to date", "Reserve", "Fees paid to date", "Fees reserve", None,
                            "Expected", "Reported", "Difference"], f.header())
    ccys = sorted({(i.claim.currency or "").strip().upper() or "(none)" for i in items}) or ["(none)"]
    first, end = hr + 2, last + 1  # 1-based rows of the data block
    crit = f"$F${first}:$F${end}"
    for k, ccy in enumerate(ccys):
        row = r + 2 + k
        money = f.money(ccy if ccy != "(none)" else None, bold=True, top=1)
        ws.write_formula(row, 4, f'=COUNTIFS({crit},"{ccy}")', f.int(bold=True, top=1),
                         sum(1 for i in items if ((i.claim.currency or "").strip().upper() or "(none)") == ccy))
        ws.write_string(row, 5, ccy, f.text(bold=True, top=1))
        for col in (6, 7, 8, 9, 11, 12, 13):
            letter = xl_col_to_name(col)
            ws.write_formula(row, col, f'=SUMIFS({letter}{first}:{letter}{end},{crit},"{ccy}")', money)
        ws.write_blank(row, 10, None, f.text(top=1))
    widths = [9, 18, 10, 18, 26, 9, 15, 15, 15, 15, 48, 15, 15, 15]
    for i, w in enumerate(widths):
        ws.set_column(i, i, w)


# ------------------------------------------------------------------ 6. Missing Data

def _missing(ctx: _Ctx, ws) -> None:
    f, d = ctx.f, ctx.data
    ctx.print_setup(ws)
    ws.write_string(0, 0, "Missing mandatory data", f.get(bold=True, font_size=16))
    ws.merge_range(1, 0, 1, 8, f"{int(d.summary.get('missing_mandatory_rows') or 0):,} distinct rows are missing "
                               "at least one required field. The grid counts findings per field and sheet; grey "
                               "means the field had no column on that sheet, so it couldn't be checked.",
                   f.note(wrap=True))
    ws.set_row(1, 28)
    items = [i for i in ctx.issues if i.check_type == "MANDATORY_FIELD"]
    read = [s for s in d.sheets if s.status == "CONFIRMED"]
    gaps = {(g.sheet, g.field_code) for g in d.field_gaps}
    codes = list(dict.fromkeys(list(REQUIRED_CODES) + [i.field_code for i in items if i.field_code]))
    counts = Counter((i.sheet, i.field_code) for i in items)
    hr = 3
    ws.write_row(hr, 0, ["Field"] + [s.name for s in read] + ["Total"], f.header())
    ws.set_row(hr, 32)
    na = f.status("na", bold=False, align="center")
    for n, code in enumerate(codes):
        row = hr + 1 + n
        spec = FIELDS_BY_CODE.get(code)
        ws.write_string(row, 0, spec.name if spec else code, f.text(bold=True))
        for k, s in enumerate(read):
            if (s.name, code) in gaps and not counts.get((s.name, code)):
                ws.write_string(row, 1 + k, "Couldn't map", na)
            else:
                ws.write_number(row, 1 + k, counts.get((s.name, code), 0), f.int())
        if read:
            a, b = xl_rowcol_to_cell(row, 1), xl_rowcol_to_cell(row, len(read))
            ws.write_formula(row, len(read) + 1, f"=SUM({a}:{b})", f.int(bold=True),
                             sum(counts.get((s.name, code), 0) for s in read))
    tot = hr + 1 + len(codes)
    ws.write_string(tot, 0, "Total", f.text(bold=True, top=1))
    for k in range(len(read) + 1):
        a, b = xl_rowcol_to_cell(hr + 1, 1 + k), xl_rowcol_to_cell(tot - 1, 1 + k)
        ws.write_formula(tot, 1 + k, f"=SUM({a}:{b})", f.int(bold=True, top=1),
                         sum(counts.get((read[k].name, c), 0) for c in codes) if k < len(read) else len(items))
    rr = tot + 1
    ws.write_string(rr, 0, "Claim rows read", f.note())
    for k, s in enumerate(read):
        ws.write_number(rr, 1 + k, s.claim_rows, f.int(font_color=THEME["muted"]))
    if read and codes:
        ws.conditional_format(hr + 1, 1, tot - 1, len(read), {
            "type": "2_color_scale", "min_color": "#FFFFFF", "max_color": "#F87171"})
    ws.set_column(0, 0, 26)
    ws.set_column(1, len(read) + 1, 12)

    r = rr + 2
    ws.write_string(r, 0, "Row by row", f.section())
    head = ["Ref", "Sheet", "Source row", "Claim reference", "Missing field", "Who fixes", "Explanation"]
    lr = r + 1
    ws.write_row(lr, 0, head, f.header())
    ws.repeat_rows(lr)
    links = [0]
    for n, i in enumerate(items):
        row = lr + 1 + n
        ctx.link_to_issue(ws, row, 0, i, count=links)
        ws.write_row(row, 1, [i.sheet or "", i.row, i.claim.claim_ref or "", i.field_name or i.column or "",
                              i.owner, i.sentence], f.text())
    if not items:
        ws.write_string(lr + 1, 0, "No required field is missing in what was read.", f.note())
    ws.autofilter(lr, 0, lr + max(1, len(items)), len(head) - 1)
    ws.set_column(len(read) + 2, len(read) + 8, 14)


# ------------------------------------------------------------------ 7. Audit Trail

EVENT_WORD = {
    "UPLOAD": "File uploaded", "REPORT_CREATED": "File uploaded", "MAPPING": "Mapping changed",
    "MAPPING_CONFIRMED": "Mapping confirmed", "SHEET_SKIPPED": "Sheet skipped", "SHEET_INCLUDED": "Sheet included",
    "JOB_QUEUED": "Job queued", "JOB_STARTED": "Job started", "JOB_SUCCEEDED": "Job finished",
    "JOB_FAILED": "Job failed", "EXPORT_GENERATED": "File exported", "AUDIT_PACK_EXPORTED": "Audit pack exported",
    "EXCEPTION_STATUS_CHANGED": "Finding status changed", "ISSUE_STATUS_CHANGED": "Issue status changed",
    "SOURCE_COLUMN_UNMAPPED": "Column left unmapped", "STATUS_CHANGED": "Report status changed",
}


def _detail(before, after) -> str:
    def flat(v) -> str:
        if not isinstance(v, dict):
            return "" if v is None else str(v)
        return "; ".join(f"{k}: {x}" for k, x in v.items() if x not in (None, "", [], {})
                         and k not in ("sha256", "history"))
    a, b = flat(after), flat(before)
    text = f"{b} → {a}" if b and a else a or b
    return text[:500]


def _audit(ctx: _Ctx, ws) -> None:
    f, d, m = ctx.f, ctx.data, ctx.data.meta
    ctx.print_setup(ws)
    ws.write_string(0, 0, "Audit trail", f.get(bold=True, font_size=16))
    ws.write_string(1, 0, "Every recorded action on this report, in order. Each entry is hash-chained to the one "
                          "before it, so a changed or removed entry is detectable.", f.note())
    confirmed = [c for c in d.columns if c.confirmed_at]
    facts = [
        ("Uploaded (UTC)", _utc(m.uploaded_at), m.uploaded_by or ""),
        ("Mapping confirmed", f"{len(confirmed):,} of {len(d.columns):,} columns",
         ", ".join(sorted({c.confirmed_by for c in confirmed if c.confirmed_by}))[:200]),
        ("Validated (UTC)", _utc(m.processed_at), f"Engine {m.engine_version} · ruleset {m.ruleset_version}"),
        ("This export (UTC)", _utc(m.exported_at), m.exported_by),
    ]
    for n, (k, v, extra) in enumerate(facts):
        r = 3 + n
        ws.write_string(r, 0, k, f.text(font_color=THEME["muted"]))
        if isinstance(v, dt.datetime):
            ws.write_datetime(r, 1, v, f.datetime(bold=True))
        else:
            ws.write(r, 1, v if v is not None else "Not recorded", f.text(bold=True))
        ws.write_string(r, 2, extra, f.text())
    hr = 9
    head = ["Seq", "Time (UTC)", "Event", "Actor", "Detail", "Entry hash"]
    ws.write_row(hr, 0, head, f.header())
    ws.freeze_panes(hr + 1, 0)
    ws.repeat_rows(hr)
    for n, e in enumerate(d.audit):
        row = hr + 1 + n
        ws.write_number(row, 0, e.seq, f.int())
        ws.write_datetime(row, 1, _utc(e.at), f.datetime())
        ws.write_string(row, 2, EVENT_WORD.get(e.action, e.action.replace("_", " ").capitalize()))
        ws.write_string(row, 3, e.actor or "")
        ws.write_string(row, 4, _detail(e.before, e.after), f.wrap())
        ws.write_string(row, 5, e.entry_hash or "", f.text(font_color=THEME["muted"], font_size=8))
    last = hr + max(1, len(d.audit))
    ws.autofilter(hr, 0, last, len(head) - 1)
    r = last + 2
    ws.write_string(r, 0, "Mapping confirmations", f.section())
    ws.write_row(r + 1, 0, ["Sheet", "Column", "Field", "Mapping state", "Confirmed by", "Confirmed (UTC)"],
                 f.header())
    for n, c in enumerate(confirmed):
        row = r + 2 + n
        ws.write_row(row, 0, [c.sheet, f"{c.letter} · {c.source_column}", c.field_name or "",
                              MAPPING_WORD.get(c.state, c.state), c.confirmed_by or ""])
        ws.write_datetime(row, 5, _utc(c.confirmed_at), f.datetime())
    if not confirmed:
        ws.write_string(r + 2, 0, "No column-level confirmation was recorded.", f.note())
    for i, w in enumerate((18, 19, 26, 24, 70, 20)):
        ws.set_column(i, i, w)


# ------------------------------------------------------------------ 8. About This Report

def _about(ctx: _Ctx, ws) -> None:
    f = ctx.f
    ctx.print_setup(ws, gridlines=False)
    ws.hide_gridlines(2)
    ws.set_column(0, 0, 2)
    ws.set_column(1, 1, 30)
    ws.set_column(2, 2, 18)
    ws.set_column(3, 3, 90)
    h = f.get(bold=True, font_size=16)
    p = f.wrap()
    r = 1
    ws.write_string(r, 1, "About this report", h)
    r += 2
    for para in (
        "This workbook was produced by TrueBind, which checks insurance bordereaux before they are submitted or "
        "accepted. It reads every sheet of the file, matches each column to a standard field, runs the checks "
        "below on every row, and records what it could not check as clearly as what it found.",
        "Start on the Summary sheet. The coverage banner at the top says how much of the file was read. Every "
        "count and the score cover only what was read: anything marked Couldn't check was not assessed.",
        "The Exceptions sheet is the working list: one row per finding. Status and Owner can be edited, so a team "
        "can work the file and send it back. Values are shown exactly as received; nothing in the source was "
        "changed.",
    ):
        ws.merge_range(r, 1, r, 3, para, p)
        ws.set_row(r, 44)
        r += 1
    r += 1
    ws.write_string(r, 1, "Colours", f.section())
    r += 1
    for word, tone, meaning in (
        ("Error", "error", "Must be fixed before the file is sent or accepted."),
        ("Warning", "warning", "Unusual, or read but not in a checkable form. Review it."),
        ("Couldn't check", "na", "Not assessed: a column couldn't be mapped, a sheet wasn't read, or the values "
                                 "needed were missing. The bold border marks it in greyscale print."),
        ("Mapped by AI", "info", "A column matched by the AI model and confirmed by a person."),
        ("Pass / Read", "pass", "Read and checked; nothing found."),
    ):
        ws.write_string(r, 1, word, f.status(tone))
        ws.write_string(r, 3, meaning, p)
        r += 1
    r += 1
    ws.write_string(r, 1, "How columns were mapped", f.section())
    r += 1
    ws.write_string(r, 3, "The Summary rolls these into three: mapped by alias (alias, memory and by hand), mapped "
                          "by AI, and couldn't map.", f.note())
    r += 1
    for state in ("MAPPED_BY_ALIAS", "MAPPED_BY_AI", "MAPPED_BY_MEMORY", "MANUAL", "UNMAPPED"):
        tone = "na" if state == "UNMAPPED" else "info" if state == "MAPPED_BY_AI" else "pass"
        ws.write_string(r, 1, MAPPING_WORD[state], f.status(tone))
        ws.write_string(r, 2, state, f.text(font_color=THEME["muted"], font_size=8))
        ws.write_string(r, 3, MAPPING_MEANING[state], p)
        r += 1
    r += 1
    ws.write_string(r, 1, "What each check means", f.section())
    r += 1
    ws.write_row(r, 1, ["Check", "Result if found", "What it means and how to fix it"], f.header())
    r += 1
    for rule in sorted(RULES.values(), key=lambda x: (x.check_type, SEVERITY_ORDER.get(x.severity, 9), x.label)):
        ws.write_string(r, 1, rule.label, f.wrap(bold=True))
        word = "Error" if rule.outcome == "FAIL" else "Warning"
        ws.write_string(r, 2, word, f.status(TONE[word]))
        ws.write_string(r, 3, f"{CHECK_WORD.get(rule.check_type, rule.check_type.title())}. {rule.fix}", p)
        r += 1
    ws.write_string(r, 1, "Total incurred could not be reconciled", f.wrap(bold=True))
    ws.write_string(r, 2, "Couldn't check", f.status("na"))
    ws.write_string(r, 3, "Arithmetic. A row's amounts were missing or unreadable, so its total could not be "
                          "recomputed. It is listed, never guessed.", p)
    r += 2
    ws.write_string(r, 1, "Disclaimer", f.section())
    r += 1
    ws.merge_range(r, 1, r, 3, "TrueBind reports what it found in the file as received, using the checks listed "
                               "above. It does not verify facts outside the file, and a clean result is not an "
                               "opinion on the claims themselves. Use it alongside your own controls.", p)
    ws.set_row(r, 32)
    r += 2
    ws.write_url(r, 1, "https://truebind.ie", f.link(), string="truebind.ie")
