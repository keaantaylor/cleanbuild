"""One design system for every Excel file TrueBind produces.

Colours come from the truebind.ie tokens (frontend/styles/globals.css, light
theme, which is the one that prints): ink #0f172a, accent #059669, ok #047857,
warn #b45309, err #b91c1c, med #1d4ed8, na #94a3b8. Excel fills are light tints
of those so text on them stays AA-readable, and every status is also written
as a word in the cell, so the file reads the same in greyscale.

``Formats`` is the write-once cache: XlsxWriter formats are created once per
distinct style and reused, never one per cell.
"""

from __future__ import annotations

THEME = {
    "font": "Calibri",
    "size": 10,
    "ink": "#0F172A",        # --bg (dark) / --text (light)
    "ink_text": "#F1F5F9",   # --text on ink
    "muted": "#475569",      # --muted (light)
    "faint": "#64748B",
    "line": "#CBD5E1",
    "band": "#F1F5F9",       # --bg2 (light)
    "accent": "#059669",     # --accent (light)
    "mint": "#34D399",       # --accent (dark), the logo mint
    "head": "#E2E8F0",
    "link": "#1D4ED8",
    # status: (fill, text)
    "error": ("#FDE2E2", "#991B1B"),
    "warning": ("#FEF3C7", "#92400E"),
    "info": ("#DBEAFE", "#1E3A8A"),
    "pass": ("#DCFCE7", "#14532D"),
    "pass_subtle": ("#F0F7F2", "#14532D"),  # annotated workbook: OK cells, kept quiet
    "na": ("#E2E8F0", "#334155"),           # couldn't check / couldn't map
}

# One word per status, always written into the cell next to its colour.
RESULT_WORD = {"FAIL": "Error", "REVIEW": "Warning", "NOT_EVALUABLE": "Couldn't check"}
TONE = {"Error": "error", "Warning": "warning", "Couldn't check": "na"}
PRIORITY_WORD = {"CRITICAL": "Critical", "HIGH": "High", "MEDIUM": "Medium", "INFO": "Info"}

MAPPING_WORD = {
    "MAPPED_BY_ALIAS": "Mapped by alias",
    "MAPPED_BY_AI": "Mapped by AI",
    "MAPPED_BY_MEMORY": "Mapped from memory",
    "MANUAL": "Mapped by hand",
    "UNMAPPED": "Couldn't map",
}
MAPPING_MEANING = {
    "MAPPED_BY_ALIAS": "The column heading matched a known name for this field (a deterministic rule).",
    "MAPPED_BY_AI": "The AI model proposed this match from the heading and sample values; a person confirmed the "
                    "sheet before checks ran.",
    "MAPPED_BY_MEMORY": "Reused from an earlier file from the same sender that a person confirmed.",
    "MANUAL": "A person chose this column for the field on the mapping screen.",
    "UNMAPPED": "Not matched to any field. The values are kept with each row but no check used them.",
}
# The Summary banner's three headline buckets.
MAPPING_BUCKET = {"MAPPED_BY_ALIAS": "alias", "MAPPED_BY_MEMORY": "alias", "MANUAL": "alias",
                  "MAPPED_BY_AI": "ai", "UNMAPPED": "none"}

DATE_FMT = "dd-mmm-yyyy"
DATETIME_FMT = "dd-mmm-yyyy hh:mm"
_CCY_FMT = {
    "GBP": '[$£-809]#,##0.00;-[$£-809]#,##0.00',
    "EUR": '[$€-1809]#,##0.00;-[$€-1809]#,##0.00',
    "USD": '[$$-409]#,##0.00;-[$$-409]#,##0.00',
}


def money_format(currency: str | None) -> str:
    """Number format for an amount in a currency; unknown codes keep the code as a suffix."""
    code = (currency or "").strip().upper()
    if code in _CCY_FMT:
        return _CCY_FMT[code]
    if len(code) == 3 and code.isalpha():
        return f'#,##0.00 "{code}";-#,##0.00 "{code}"'
    return "#,##0.00"


class Formats:
    """Write-once XlsxWriter format cache, keyed by the style's properties."""

    def __init__(self, workbook) -> None:
        self._wb = workbook
        self._cache: dict[tuple, object] = {}
        self.base = {"font_name": THEME["font"], "font_size": THEME["size"], "valign": "top"}

    def get(self, **props):
        key = tuple(sorted(props.items()))
        fmt = self._cache.get(key)
        if fmt is None:
            fmt = self._wb.add_format({**self.base, **props})
            self._cache[key] = fmt
        return fmt

    # Named styles used across sheets.
    def text(self, **kw):
        return self.get(**kw)

    def wrap(self, **kw):
        return self.get(text_wrap=True, **kw)

    def header(self):
        return self.get(bold=True, font_size=11, bg_color=THEME["head"], font_color=THEME["ink"],
                        bottom=1, bottom_color=THEME["line"], text_wrap=True, valign="vcenter")

    def section(self):
        return self.get(bold=True, font_size=12, font_color=THEME["ink"], bottom=2, bottom_color=THEME["accent"])

    def note(self, wrap: bool = False):
        """Muted italic text; unwrapped by default so a one-line note runs across empty cells."""
        return self.get(italic=True, font_color=THEME["muted"], text_wrap=wrap)

    def int(self, **kw):
        return self.get(num_format="#,##0", align="right", **kw)

    def money(self, currency: str | None, **kw):
        return self.get(num_format=money_format(currency), align="right", **kw)

    def date(self, **kw):
        return self.get(num_format=DATE_FMT, align="left", **kw)

    def datetime(self, **kw):
        return self.get(num_format=DATETIME_FMT, align="left", **kw)

    def link(self, **kw):
        return self.get(font_color=THEME["link"], underline=1, **kw)

    def status(self, tone: str, bold: bool = True, **kw):
        fill, text = THEME[tone]
        extra = {"border": 2, "border_color": THEME["faint"]} if tone == "na" else {}
        return self.get(bg_color=fill, font_color=text, bold=bold, **extra, **kw)

    def status_dxf(self, tone: str):
        """Conditional-format variant (only colours and weight are allowed there)."""
        key = ("dxf", tone)
        if key not in self._cache:
            fill, text = THEME[tone]
            self._cache[key] = self._wb.add_format({"bg_color": fill, "font_color": text, "bold": True})
        return self._cache[key]


def column_widths(rows, header, cap: int = 60, floor: int = 8) -> list[float]:
    """Widths from content (first 500 rows), capped so long text wraps instead."""
    widths = [max(floor, len(str(h)) + 2) for h in header]
    for row in rows[:500]:
        for i, v in enumerate(row):
            if i < len(widths) and v is not None:
                n = len(v) if isinstance(v, str) else len(f"{v:,.2f}") if isinstance(v, float) else len(str(v))
                widths[i] = max(widths[i], min(cap, n + 2))
    return widths


def safe_footer_text(value: str, limit: int = 90) -> str:
    """Header/footer text: '&' is a control character there."""
    return value[:limit].replace("&", "&&")
