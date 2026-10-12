/* One set of result colours for the health report, its PDF and the annotated
   workbook: red = error, amber = warning (unusual or can't validate),
   green = checked OK, grey = couldn't check / structural. The hex pairs are the
   workbooks' cell fills and text colours (backend app/exports/theme.py uses the
   same pairs), so a finding looks the same in every output. The annotated
   workbook uses a lighter green (#F0F7F2) for OK cells so problems stand out. */

import type { Severity } from "./types";

export type ResultTone = "err" | "warn" | "ok" | "muted";

export const TONE: Record<ResultTone, { bg: string; fg: string; label: string }> = {
  err: { bg: "#FFC7CE", fg: "#9C0006", label: "Error" },
  warn: { bg: "#FFF2CC", fg: "#7F6000", label: "Warning" },
  ok: { bg: "#E2F0D9", fg: "#375623", label: "OK" },
  muted: { bg: "#E7E6E6", fg: "#3A3A3A", label: "Couldn’t check" },
};

/** FAIL is an error, REVIEW a warning, NOT_EVALUABLE couldn't check. */
export function resultTone(status: string | null | undefined): ResultTone {
  return status === "FAIL" ? "err" : status === "REVIEW" ? "warn" : status === "NOT_EVALUABLE" ? "muted" : "ok";
}

export const SEVERITY_LABEL: Record<Severity, string> = { CRITICAL: "Critical", HIGH: "High", MEDIUM: "Medium", INFO: "Info" };

export function severityLabel(s: string | null | undefined): string {
  return SEVERITY_LABEL[(s ?? "").toUpperCase() as Severity] ?? "Info";
}

/** The Excel Health Report's brand colours (backend app/exports/theme.py THEME),
 * for previews that must look like the workbook rather than the app. */
export const XLSX_BRAND = {
  ink: "#0F172A",
  inkText: "#F1F5F9",
  mint: "#34D399",
  accent: "#059669",
  band: "#F1F5F9",
  line: "#CBD5E1",
  ai: { bg: "#DBEAFE", fg: "#1E3A8A" },
} as const;
