/* "Export this view": the Exceptions page's currently filtered findings as an
   .xlsx built in the browser with ExcelJS, styled like the server's Health
   Report Exceptions sheet (same header, same result colours, same words). The
   full Health Report is always built by the server. */

import type { ExceptionRow } from "./types";
import { severityLabel, TONE, resultTone } from "./severity";

export const VIEW_HEAD = ["Severity", "Priority", "Check", "Sheet", "Source row", "Cell", "Claim reference", "Column",
  "Explanation", "Who fixes", "Amount", "Currency", "Status", "Owner", "Notes"] as const;

const RESULT_WORD = { FAIL: "Error", REVIEW: "Warning", NOT_EVALUABLE: "Couldn't check", PASS: "Pass" } as const;
const STATUS_WORD: Record<string, string> = { open: "Open", in_review: "Open", resolved: "Resolved", accepted: "Accepted",
  false_positive: "Accepted" };

export type ViewCell = string | number | null;

/** One spreadsheet row per finding, in VIEW_HEAD order. */
export function viewRow(x: ExceptionRow, labels: Record<string, string>): ViewCell[] {
  return [
    RESULT_WORD[x.status as keyof typeof RESULT_WORD] ?? x.status,
    severityLabel(x.severity),
    labels[x.rule ?? ""] ?? x.rule ?? x.check_type,
    x.sheet_name ?? null,
    x.source_row_number ?? null,
    x.cell ?? null,
    x.claim_reference ?? null,
    x.source_column ?? null,
    x.sentence ?? x.message,
    x.owner === "sender" ? "Sender" : x.owner === "us" ? "Us" : null,
    x.amount ?? null,
    x.currency ?? null,
    STATUS_WORD[x.review_status ?? "open"] ?? "Open",
    x.assignee ?? null,
    x.note ?? null,
  ];
}

const argb = (hex: string) => `FF${hex.replace("#", "").toUpperCase()}`;

export async function exceptionsViewToXlsx(rows: ExceptionRow[], labels: Record<string, string>, meta: { file: string; filters: string }): Promise<Blob> {
  const { default: ExcelJS } = await import("exceljs");
  const wb = new ExcelJS.Workbook();
  wb.creator = "TrueBind";
  wb.created = new Date();
  const ws = wb.addWorksheet("Exceptions (view)", { views: [{ state: "frozen", ySplit: 1, xSplit: 1 }] });
  ws.properties.defaultRowHeight = 15;
  ws.addRow([...VIEW_HEAD]);
  const font = { name: "Calibri", size: 10 };
  for (const x of rows) {
    const row = ws.addRow(viewRow(x, labels));
    row.font = font;
    row.alignment = { vertical: "top" };
    const tone = TONE[resultTone(x.status)];
    const sev = row.getCell(1);
    sev.fill = { type: "pattern", pattern: "solid", fgColor: { argb: argb(tone.bg) } };
    sev.font = { ...font, bold: true, color: { argb: argb(tone.fg) } };
    if (x.status === "NOT_EVALUABLE") sev.border = { top: { style: "medium" }, bottom: { style: "medium" }, left: { style: "medium" }, right: { style: "medium" } };
    row.getCell(11).numFmt = "#,##0.00";
    row.getCell(9).alignment = { vertical: "top", wrapText: true };
  }
  const head = ws.getRow(1);
  head.font = { name: "Calibri", size: 11, bold: true, color: { argb: "FF0F172A" } };
  head.alignment = { vertical: "middle", wrapText: true };
  head.fill = { type: "pattern", pattern: "solid", fgColor: { argb: "FFE2E8F0" } };
  head.border = { bottom: { style: "thin", color: { argb: "FFCBD5E1" } } };
  head.height = 28;
  const widths = [14, 10, 30, 18, 10, 8, 18, 22, 60, 10, 14, 9, 18, 16, 30];
  widths.forEach((w, i) => (ws.getColumn(i + 1).width = w));
  ws.autoFilter = { from: { row: 1, column: 1 }, to: { row: 1, column: VIEW_HEAD.length } };
  const last = rows.length + 1;
  if (rows.length) {
    for (let r = 2; r <= last; r++) {
      ws.getCell(r, 13).dataValidation = { type: "list", allowBlank: true, formulae: ['"Open,Queried with sender,Resolved,Accepted"'] };
    }
  }
  ws.headerFooter.oddFooter = `&L&8TrueBind · ${meta.file.replace(/&/g, "&&").slice(0, 80)} · ${meta.filters.replace(/&/g, "&&").slice(0, 80)}&R&8Page &P of &N`;
  ws.pageSetup = { orientation: "landscape", fitToPage: true, fitToWidth: 1, fitToHeight: 0, printTitlesRow: "1:1" };
  const buf = await wb.xlsx.writeBuffer();
  return new Blob([buf], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
}
