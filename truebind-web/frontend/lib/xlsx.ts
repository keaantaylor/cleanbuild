/* CSV → Excel conversion for downloads. The backend's CSV stays the source of
   truth; this only changes the container so the file opens cleanly in Excel:
   bold frozen header with filters, auto-sized columns, real numbers and dates.
   Identifiers that merely look numeric (leading zeros, long references) stay
   text so Excel never strips or rounds them. */

/** RFC 4180 CSV parser: quoted fields, doubled quotes, CRLF/LF, BOM. */
export function parseCsv(text: string): string[][] {
  const src = text.charCodeAt(0) === 0xfeff ? text.slice(1) : text;
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let quoted = false;
  for (let i = 0; i < src.length; i++) {
    const ch = src[i];
    if (quoted) {
      if (ch === '"') {
        if (src[i + 1] === '"') {
          field += '"';
          i++;
        } else quoted = false;
      } else field += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === ",") {
      row.push(field);
      field = "";
    } else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && src[i + 1] === "\n") i++;
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else field += ch;
  }
  if (field !== "" || row.length) {
    row.push(field);
    rows.push(row);
  }
  return rows;
}

export type Cell =
  | { kind: "text"; value: string }
  | { kind: "number"; value: number; decimals: number }
  | { kind: "date"; value: Date }
  | { kind: "datetime"; value: Date }
  | { kind: "empty" };

const NUM = /^-?(0|[1-9]\d{0,13})(\.\d{1,6})?$/;
const DATE = /^(\d{4})-(\d{2})-(\d{2})$/;
const DATETIME = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$/;
// Columns whose values are identifiers even when they look like numbers
// ("claim_reference", "policy_number", "umr"), but not counts like "row_number".
const ID_COLUMN = /(^|_)(id|ref|reference|number|no|code|umr|sha256|hash|postcode|zip|phone)$|^(policy|claim|certificate|umr)$/;
const ROW_COLUMN = /^(source_)?row(_number|_no)?$/;
const norm = (h: string) => h.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");

/** How one CSV value should be stored in Excel. */
export function inferCell(raw: string, header = ""): Cell {
  const v = raw.trim();
  if (v === "") return { kind: "empty" };
  const h = norm(header);
  if (ID_COLUMN.test(h) && !ROW_COLUMN.test(h)) return { kind: "text", value: raw };
  if (NUM.test(v)) return { kind: "number", value: Number(v), decimals: v.split(".")[1]?.length ?? 0 };
  let m = DATE.exec(v);
  if (m) {
    const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
    if (d.getUTCMonth() === +m[2] - 1) return { kind: "date", value: d };
  }
  m = DATETIME.exec(v);
  if (m) {
    const d = new Date(v.replace(" ", "T"));
    if (!Number.isNaN(d.getTime())) return { kind: "datetime", value: d };
  }
  return { kind: "text", value: raw };
}

/** Display width (characters) used to size a column. */
export function cellWidth(c: Cell): number {
  switch (c.kind) {
    case "empty":
      return 0;
    case "number":
      return c.value.toLocaleString("en-GB", { minimumFractionDigits: c.decimals, maximumFractionDigits: c.decimals }).length + 1;
    case "date":
      return 11;
    case "datetime":
      return 17;
    default:
      return Math.max(...c.value.split(/\r?\n/).map((l) => l.length));
  }
}

// Any fractional column shows at least 2 decimals (amounts), more if the data has them (rates).
const numFmt = (decimals: number) => (decimals ? `#,##0.${"0".repeat(Math.max(2, decimals))}` : "#,##0");

/** Builds an .xlsx workbook from CSV text. exceljs is loaded only when needed. */
export async function csvToXlsx(csv: string, sheetName: string): Promise<Blob> {
  const { default: ExcelJS } = await import("exceljs");
  const rows = parseCsv(csv);
  const header = rows[0] ?? [];
  const body = rows.slice(1).filter((r) => r.some((c) => c.trim() !== ""));
  const wb = new ExcelJS.Workbook();
  wb.creator = "TrueBind";
  wb.created = new Date();
  const ws = wb.addWorksheet(sheetName.replace(/[\\/?*[\]:]/g, " ").slice(0, 31) || "Sheet1", {
    views: [{ state: "frozen", ySplit: 1 }],
  });
  const widths = header.map((h) => h.length + 2);
  const decimals = header.map(() => 0);

  ws.addRow(header);
  for (const r of body) {
    const cells = header.map((h, i) => inferCell(r[i] ?? "", h));
    const row = ws.addRow(cells.map((c) => (c.kind === "empty" ? null : c.value)));
    cells.forEach((c, i) => {
      widths[i] = Math.max(widths[i], cellWidth(c) + 2);
      const cell = row.getCell(i + 1);
      if (c.kind === "number") {
        decimals[i] = Math.max(decimals[i], c.decimals);
        cell.numFmt = numFmt(c.decimals);
      } else if (c.kind === "date") cell.numFmt = "dd mmm yyyy";
      else if (c.kind === "datetime") cell.numFmt = "dd mmm yyyy hh:mm";
      else if (c.kind === "text" && c.value.includes("\n")) cell.alignment = { wrapText: true, vertical: "top" };
    });
    // Extra cells beyond the header are kept, never dropped.
    for (let i = header.length; i < r.length; i++) row.getCell(i + 1).value = r[i];
  }
  // Keep a column's numbers consistently formatted (e.g. 12.50 and 3 → 12.50 and 3.00).
  decimals.forEach((d, i) => {
    if (!d) return;
    ws.getColumn(i + 1).eachCell({ includeEmpty: false }, (cell, n) => {
      if (n > 1 && typeof cell.value === "number") cell.numFmt = numFmt(d);
    });
  });

  const head = ws.getRow(1);
  head.font = { bold: true };
  head.alignment = { vertical: "middle" };
  head.fill = { type: "pattern", pattern: "solid", fgColor: { argb: "FFEEF0F6" } };
  head.border = { bottom: { style: "thin", color: { argb: "FFB8BCCB" } } };
  widths.forEach((w, i) => {
    ws.getColumn(i + 1).width = Math.min(Math.max(w, 8), 60);
  });
  if (header.length) ws.autoFilter = { from: { row: 1, column: 1 }, to: { row: 1, column: header.length } };

  const buf = await wb.xlsx.writeBuffer();
  return new Blob([buf], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
}
