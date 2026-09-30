import type { Report, Severity } from "@/lib/types";

export type Tone = "ok" | "warn" | "err" | "med" | "muted";

/** A report's status in plain English, with the page where its next step happens. */
export function reportStatus(r: Report): { label: string; tone: Tone; href: string } {
  const resume = `/upload?reportId=${r.id}`;
  switch (r.status) {
    case "UPLOADED":
    case "QUEUED":
      return { label: "Queued", tone: "med", href: resume };
    case "INGESTING":
      return { label: "Reading workbook", tone: "med", href: resume };
    case "WAITING_FOR_REVIEW":
      return { label: "Needs mapping review", tone: "warn", href: resume };
    case "PROCESSING":
      return { label: "Processing", tone: "med", href: resume };
    case "COMPLETE":
      return (r.issues_found ?? 0) > 0
        ? { label: "Needs review", tone: "warn", href: `/reports/${r.id}` }
        : { label: "Checked · no findings", tone: "ok", href: `/reports/${r.id}` };
    case "FAILED":
      return { label: "Failed", tone: "err", href: resume };
    case "CANCELLED":
      return { label: "Cancelled", tone: "muted", href: resume };
    case "EXPIRED":
      return { label: "Expired", tone: "muted", href: `/reports/${r.id}` };
    default:
      return { label: String(r.status), tone: "muted", href: `/reports/${r.id}` };
  }
}

export const SEV: Record<Severity, { label: string; c: string; bg: string; tone: Tone }> = {
  CRITICAL: { label: "Critical", c: "var(--err)", bg: "var(--errT)", tone: "err" },
  HIGH: { label: "High", c: "var(--warn)", bg: "var(--warnT)", tone: "warn" },
  MEDIUM: { label: "Medium", c: "var(--med)", bg: "var(--medT)", tone: "med" },
  INFO: { label: "Info", c: "var(--muted)", bg: "var(--line)", tone: "muted" },
};

/** Sheet cell highlight colours (the spreadsheet stays light in both themes). */
export const SHEET: Record<Severity, { bg: string; fg: string; ring: string }> = {
  CRITICAL: { bg: "oklch(0.94 0.045 25)", fg: "oklch(0.48 0.17 25)", ring: "inset 0 0 0 1.5px oklch(0.62 0.18 25)" },
  HIGH: { bg: "oklch(0.95 0.06 85)", fg: "oklch(0.46 0.1 70)", ring: "inset 0 0 0 1.5px oklch(0.72 0.14 75)" },
  MEDIUM: { bg: "oklch(0.95 0.03 255)", fg: "oklch(0.45 0.1 255)", ring: "inset 0 0 0 1.5px oklch(0.6 0.1 255)" },
  INFO: { bg: "oklch(0.955 0.035 150)", fg: "oklch(0.4 0.1 150)", ring: "inset 0 0 0 1.5px oklch(0.6 0.12 150)" },
};
