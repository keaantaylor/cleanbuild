"use client";

import { useState } from "react";
import { CircleNotch, DownloadSimple, FileXls, WarningCircle } from "@phosphor-icons/react";
import { api } from "@/lib/api";
import { downloadServerFile, ExportError } from "@/lib/exports";
import { formatNumber } from "@/lib/formatters";
import { TONE, XLSX_BRAND } from "@/lib/severity";
import { useUi } from "@/lib/ui";
import type { Report, ReportSummary } from "@/lib/types";

/* "Download the Health Report": a faithful miniature of the workbook's Summary
   sheet (coverage banner first, then the tiles and the colour legend), and the
   two downloads. The colours are the workbook's own (backend app/exports/theme.py). */

type Phase = { state: "idle" } | { state: "busy" } | { state: "error"; message: string } | { state: "unavailable"; message: string };

const SHEET_TABS = ["Summary", "Coverage", "Exceptions", "Duplicates", "Reconciliation", "Missing Data", "Audit Trail", "About"];

function useDownload(url: string, fallback: string, label: string) {
  const { toast } = useUi();
  const [phase, setPhase] = useState<Phase>({ state: "idle" });
  const run = async () => {
    setPhase({ state: "busy" });
    try {
      const name = await downloadServerFile(url, fallback);
      setPhase({ state: "idle" });
      toast(`Downloaded ${name}`, "ok");
    } catch (e) {
      const message = e instanceof Error ? e.message : `The ${label} could not be built.`;
      if (e instanceof ExportError && e.status === 409) setPhase({ state: "unavailable", message });
      else setPhase({ state: "error", message });
    }
  };
  return { phase, run };
}

export function HealthReportDownload({ report, s, name }: { report: Report; s: ReportSummary; name: string }) {
  const health = useDownload(api.healthReportUrl(report.id), `TrueBind_Health_Report_${name}.xlsx`, "Health Report");
  const annotated = useDownload(api.annotatedWorkbookUrl(report.id), `${name}_REVIEWED.xlsx`, "annotated file");
  const busy = health.phase.state === "busy";
  const aBusy = annotated.phase.state === "busy";
  return (
    <section className="no-print tb-card flex w-full max-w-[1100px] flex-col gap-5 p-5 sm:p-6" aria-labelledby="hr-download">
      <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)] lg:items-center">
        <SummaryPreview report={report} s={s} />
        <div className="flex min-w-0 flex-col gap-3">
          <span className="text-[12px] font-semibold uppercase tracking-[.1em]" style={{ color: "var(--kicker)" }}>Excel workbook</span>
          <h2 id="hr-download" className="m-0 text-[20px] font-medium leading-[1.25]">Download the Health Report</h2>
          <p className="m-0 text-[13.5px] leading-[1.55]" style={{ color: "var(--muted)" }}>
            Eight sheets, ready to forward to underwriters, auditors or the sender. No TrueBind login is needed to read it.
            What couldn’t be checked comes first, then every finding with its sheet, row and cell, the duplicates, the
            reconciliation with live formulas, and the audit trail.
          </p>
          <div className="flex flex-col gap-2 pt-1 sm:flex-row sm:flex-wrap">
            <button
              type="button"
              className="tb-btn tb-btn-primary justify-center"
              onClick={() => void health.run()}
              disabled={busy}
              aria-busy={busy}
              aria-describedby="hr-download-status"
            >
              {busy ? <CircleNotch className="motion-safe:animate-spin" aria-hidden /> : <DownloadSimple aria-hidden />}
              {busy ? "Building your report…" : "Download Health Report (.xlsx)"}
            </button>
            <button
              type="button"
              className="tb-btn justify-center"
              onClick={() => void annotated.run()}
              disabled={aBusy || annotated.phase.state === "unavailable"}
              aria-busy={aBusy}
              aria-describedby="hr-annotated-status"
            >
              {aBusy ? <CircleNotch className="motion-safe:animate-spin" aria-hidden /> : <FileXls aria-hidden />}
              {aBusy ? "Building your file…" : "Download annotated file"}
            </button>
          </div>
          <div id="hr-download-status" aria-live="polite" className="min-h-0">
            {health.phase.state === "error" || health.phase.state === "unavailable" ? (
              <Problem message={health.phase.message} onRetry={() => void health.run()} />
            ) : null}
          </div>
          <div id="hr-annotated-status" aria-live="polite">
            {annotated.phase.state === "error" ? (
              <Problem message={annotated.phase.message} onRetry={() => void annotated.run()} />
            ) : annotated.phase.state === "unavailable" ? (
              <p className="m-0 text-[13px] leading-[1.5]" style={{ color: "var(--muted)" }}>
                The annotated file isn’t available: {annotated.phase.message} The Health Report doesn’t need the original and still downloads.
              </p>
            ) : (
              <p className="m-0 text-[12.5px] leading-[1.5]" style={{ color: "var(--faint)" }}>
                The annotated file is your own workbook with problem cells coloured and a note on each.
              </p>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

function Problem({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div role="alert" className="flex flex-wrap items-start gap-2 rounded-md px-3 py-2 text-[13px]" style={{ background: "var(--surface2)", boxShadow: "inset 0 0 0 1px var(--line2)" }}>
      <WarningCircle className="mt-[2px] shrink-0" style={{ color: "var(--err)" }} aria-hidden />
      <span className="min-w-0 flex-1">{message}</span>
      <button type="button" className="tb-btn !py-0.5 text-[12.5px]" onClick={onRetry}>Try again</button>
    </div>
  );
}

function SummaryPreview({ report, s }: { report: Report; s: ReportSummary }) {
  const hv = s.health_view;
  const unmappedCols = (s.unmapped_source_columns ?? []).reduce((n, x) => n + x.columns.length, 0);
  const couldnt = hv?.couldnt_check.length ?? 0;
  const complete = s.sheets_processed >= s.sheets_total && unmappedCols === 0 && couldnt === 0;
  const banner = complete ? TONE.ok : TONE.warn;
  const score = s.composite_score ?? report.score;
  const tiles: [string, string, "err" | "warn" | null][] = [
    [score != null ? `${Math.round(score)} / 100` : "Not scored", "Health score", null],
    [formatNumber(hv?.counts.errors ?? 0), "Errors", "err"],
    [formatNumber(hv?.counts.warnings ?? 0), "Warnings", "warn"],
    [formatNumber(s.missing_mandatory_rows), "Rows missing data", null],
  ];
  const label = `Preview of the Summary sheet: ${s.sheets_processed} of ${s.sheets_total} sheets read, ${unmappedCols} columns couldn't be mapped, ${couldnt} checks couldn't run, ${hv?.counts.errors ?? 0} errors and ${hv?.counts.warnings ?? 0} warnings.`;
  return (
    <figure className="m-0 flex min-w-0 flex-col overflow-hidden rounded-md" style={{ background: "#fff", color: "#1c1e2a", boxShadow: "0 0 0 1px var(--line2), 0 12px 32px -18px rgba(0,0,0,.45)" }} role="img" aria-label={label}>
      <div className="flex flex-col gap-0.5 px-4 py-3" style={{ background: XLSX_BRAND.ink }}>
        <span className="text-[14px] font-semibold" style={{ color: XLSX_BRAND.inkText }}>TrueBind Health Report</span>
        <span className="truncate text-[11px]" style={{ color: XLSX_BRAND.mint }}>{report.file_name}</span>
      </div>
      <div className="m-3 mb-2 flex flex-col gap-1.5 px-3 py-2" style={{ background: banner.bg, color: banner.fg, boxShadow: `inset 0 2px 0 ${banner.fg}, inset 0 -2px 0 ${banner.fg}` }}>
        <span className="text-[11px] font-semibold">COVERAGE: {complete ? "everything was read and every check ran" : "Couldn’t check everything"}</span>
        <div className="grid grid-cols-3 gap-2">
          {([
            [`${s.sheets_processed} of ${s.sheets_total}`, "sheets read"],
            [formatNumber(unmappedCols), "columns couldn’t map"],
            [formatNumber(couldnt), "checks couldn’t run"],
          ] as const).map(([v, l]) => (
            <div key={l} className="flex min-w-0 flex-col">
              <span className="tnum text-[13px] font-semibold" style={{ color: "#1c1e2a" }}>{v}</span>
              <span className="text-[10px] leading-tight">{l}</span>
            </div>
          ))}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2 px-3 sm:grid-cols-4">
        {tiles.map(([v, l, tone]) => {
          const t = tone ? TONE[tone] : { bg: XLSX_BRAND.band, fg: "#1c1e2a" };
          return (
            <div key={l} className="flex min-w-0 flex-col gap-0.5 px-2.5 py-2" style={{ background: t.bg, color: t.fg, boxShadow: `inset 3px 0 0 ${tone ? t.fg : XLSX_BRAND.accent}` }}>
              <span className="tnum truncate text-[15px] font-semibold leading-tight">{v}</span>
              <span className="truncate text-[10px] font-medium">{l}</span>
            </div>
          );
        })}
      </div>
      <div className="flex flex-wrap gap-1.5 px-3 pb-3 pt-2.5" aria-hidden>
        {([["Error", TONE.err], ["Warning", TONE.warn], ["Couldn’t check", TONE.muted], ["Mapped by AI", XLSX_BRAND.ai], ["Pass", TONE.ok]] as const).map(([l, t]) => (
          <span key={l} className="rounded-[3px] px-1.5 py-0.5 text-[10px] font-semibold" style={{ background: t.bg, color: t.fg, boxShadow: l === "Couldn’t check" ? `inset 0 0 0 1.5px ${t.fg}` : undefined }}>{l}</span>
        ))}
      </div>
      <div className="flex gap-px overflow-hidden text-[10px]" style={{ background: XLSX_BRAND.line, boxShadow: `0 -1px 0 ${XLSX_BRAND.line}` }} aria-hidden>
        {SHEET_TABS.map((t, i) => (
          <span key={t} className="shrink-0 px-2 py-1" style={{ background: i === 0 ? "#fff" : XLSX_BRAND.band, color: i === 0 ? "#1c1e2a" : "#555a69", fontWeight: i === 0 ? 600 : 400 }}>{t}</span>
        ))}
      </div>
    </figure>
  );
}
