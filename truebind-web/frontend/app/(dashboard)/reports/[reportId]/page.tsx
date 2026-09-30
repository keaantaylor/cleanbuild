"use client";

import Link from "next/link";
import { use, useEffect, useRef, useState } from "react";
import { ArrowLeft, DownloadSimple, EnvelopeSimple, FileArchive, FilePdf, Printer } from "@phosphor-icons/react";
import { api, ApiError, IN_PROGRESS } from "@/lib/api";
import type { Report, ReportSummary } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { useUi } from "@/lib/ui";
import { useShell } from "@/components/layout/ShellContext";
import { describeAudit } from "@/lib/audit";
import { probableDuplicatesValue, provisionalReason } from "@/lib/findings";
import { formatBytes, formatDateTime, formatDuration, formatMoney, formatNumber, timeAgo } from "@/lib/formatters";
import { EmptyState, ErrorState, LoadingState, Mark, Modal, StatusPill } from "@/components/nocturne/ui";
import { ProcessingPanel } from "@/components/nocturne/intake";
import { Recommendations } from "@/components/nocturne/ops";
import { reportStatus } from "@/components/nocturne/status";
import { ChecksPanel } from "@/components/nocturne/checks";
import { exportFile } from "@/lib/exports";
import { downloadPdf, type PdfBlock } from "@/lib/pdf";

const RULE_LABEL: Record<string, string> = {
  missing_mandatory_field: "Required field missing",
  arithmetic_mismatch: "Total incurred does not reconcile",
  date_order: "Dates out of order",
  date_in_future: "Date in the future",
  invalid_currency: "Unrecognised currency code",
  currency_inconsistency: "Claim reported in several currencies",
  invalid_status: "Unrecognised claim status",
  schema_violation: "Value could not be read",
};
const RULE_SEV: Record<string, ["Critical" | "High" | "Medium" | "Info", string]> = {
  missing_mandatory_field: ["Critical", "oklch(0.54 0.17 25)"],
  arithmetic_mismatch: ["High", "oklch(0.54 0.12 65)"],
  date_order: ["Medium", "oklch(0.5 0.1 255)"],
  date_in_future: ["Medium", "oklch(0.5 0.1 255)"],
  invalid_currency: ["Medium", "oklch(0.5 0.1 255)"],
  currency_inconsistency: ["Medium", "oklch(0.5 0.1 255)"],
  invalid_status: ["Medium", "oklch(0.5 0.1 255)"],
  schema_violation: ["Info", "#676b7e"],
};

/** A factual headline built only from computed numbers. */
function headline(r: Report, s: ReportSummary) {
  const rows = s.total_claims ?? r.rows_processed;
  const flagged = s.reconciliation.rows_requiring_review;
  const na = s.not_assessed_checks?.length ?? 0;
  return `${formatNumber(rows)} rows checked. ${flagged ? `${formatNumber(flagged)} need attention before submission.` : "None need attention."}${na ? ` ${na} check${na === 1 ? "" : "s"} could not be assessed.` : ""}`;
}

export default function ReportPage({ params }: { params: Promise<{ reportId: string }> }) {
  const { reportId } = use(params);
  const shell = useShell();
  const rep = useApi(() => api.getReport(reportId), [reportId], (r) => (r && IN_PROGRESS.has(r.status) ? 800 : undefined));
  const report = rep.data;
  const settled = useRef<string | null>(null);
  useEffect(() => {
    if (report && !IN_PROGRESS.has(report.status) && settled.current !== report.status) {
      if (settled.current !== null) shell.refresh();
      settled.current = report.status;
    }
  }, [report, shell]);
  const complete = report?.status === "COMPLETE";
  const summary = useApi(() => (complete ? api.getReportSummary(reportId) : Promise.resolve(null)), [reportId, complete]);

  if (rep.loading && !rep.data) return <div className="px-4 pt-8 sm:px-9"><LoadingState label="Loading report" rows={8} /></div>;
  if (rep.error && !rep.data) return <div className="px-4 pt-8 sm:px-9"><ErrorState title="This report could not be loaded" message={rep.error} onRetry={rep.reload} /></div>;
  if (!report) return null;

  const st = reportStatus(report);
  const top = (
    <div className="no-print flex w-full flex-wrap items-center justify-between gap-3">
      <div className="flex flex-wrap items-center gap-2.5 text-[13px]" style={{ color: "var(--muted)" }}>
        <Link href="/reports" className="flex items-center gap-1.5 hover:text-[var(--text)]"><ArrowLeft />All reports</Link>
        <span style={{ color: "var(--faint)" }}>·</span>
        <span className="truncate">{report.file_name}</span>
        <StatusPill tone={st.tone}>{st.label}</StatusPill>
      </div>
    </div>
  );

  if (IN_PROGRESS.has(report.status) || report.status === "FAILED" || report.status === "CANCELLED")
    return (
      <div className="flex max-w-[1240px] flex-col gap-6 px-4 pb-16 pt-7 sm:px-9">
        {top}
        <ProcessingPanel report={report} system={shell.system} onCancel={IN_PROGRESS.has(report.status) ? () => void api.cancelReport(reportId).then(rep.reload) : undefined} onRetry={() => void api.retryReport(reportId).then(rep.reload).catch(rep.reload)} />
      </div>
    );
  if (report.status === "WAITING_FOR_REVIEW")
    return (
      <div className="flex max-w-[1240px] flex-col gap-6 px-4 pb-16 pt-7 sm:px-9">
        {top}
        <div className="tb-card"><EmptyState icon={<DownloadSimple />} title="Mapping needs your review" body="The workbook has been read. Confirm each sheet’s column mapping and TrueBind will produce the Health Check." action={<Link href={`/upload?reportId=${reportId}`} className="tb-btn tb-btn-primary">Review mapping</Link>} /></div>
      </div>
    );
  if (!complete)
    return (
      <div className="flex max-w-[1240px] flex-col gap-6 px-4 pb-16 pt-7 sm:px-9">
        {top}
        <div className="tb-card p-4 sm:p-6 text-[14px]">This report is {report.status.toLowerCase()}. Its source file is no longer available.</div>
      </div>
    );

  const s = summary.data;
  return (
    <div className="flex flex-col items-center gap-6 px-4 pb-16 pt-7 sm:px-9">
      <div className="w-full max-w-[1100px]">{top}</div>
      {!s ? (
        summary.error ? <div className="w-full max-w-[1100px]"><ErrorState title="The summary could not be loaded" message={summary.error} onRetry={summary.reload} /></div> : <div className="w-full max-w-[1100px]"><LoadingState label="Loading summary" rows={8} /></div>
      ) : (
        <ReportBody report={report} s={s} />
      )}
    </div>
  );
}

function ReportBody({ report, s }: { report: Report; s: ReportSummary }) {
  const { toast } = useUi();
  const [send, setSend] = useState(false);
  const rec = s.reconciliation;
  const flagged = rec.rows_requiring_review;
  const excluded = rec.rejected_rows + rec.non_claim_summary_rows;
  const base = Math.max(1, rec.source_data_rows);
  const clean = Math.max(0, rec.exported_rows - flagged);
  const unmappedCols = (s.unmapped_source_columns ?? []).reduce((a, u) => a + u.columns.length, 0);
  const na = s.not_assessed_checks ?? [];
  const pct = (n: number) => `${Math.max(0, (n / base) * 100)}%`;
  const rules = Object.entries(s.exception_counts_by_rule ?? {}).sort((a, b) => b[1] - a[1]);
  const periods = Object.entries(s.reporting_periods ?? {}).sort((a, b) => a[0].localeCompare(b[0]));
  const totals = s.totals_by_currency ?? [];
  const impact = totals.map((t) => formatMoney(t.incurred, t.currency)).join(" · ") || "—";
  const name = report.file_name.replace(/\.\w+$/, "");

  const pdf = () => {
    const blocks: PdfBlock[] = [
      { kind: "kicker", text: `TRUEBIND · BORDEREAU HEALTH CHECK · ${report.id.slice(0, 8).toUpperCase()}` },
      { kind: "muted", text: `${report.file_name} · received ${formatDateTime(report.created_at)}${report.sender ? ` · from ${report.sender}` : ""}` },
      { kind: "space", h: 8 },
      { kind: "title", text: headline(report, s) },
      { kind: "rule" },
      { kind: "heading", text: "Coverage" },
      { kind: "row", cells: ["Checked", "Flagged", "Unmapped", "Not assessed"], widths: [0.25, 0.25, 0.25, 0.25], bold: true },
      { kind: "row", cells: [`${formatNumber(clean)} rows`, `${formatNumber(flagged)} rows`, `${unmappedCols} column${unmappedCols === 1 ? "" : "s"}`, `${na.length} check${na.length === 1 ? "" : "s"}`], widths: [0.25, 0.25, 0.25, 0.25] },
      { kind: "space", h: 6 },
      { kind: "row", cells: ["Sheets", "Source rows", "Findings", "Health score"], widths: [0.25, 0.25, 0.25, 0.25], bold: true },
      { kind: "row", cells: [`${s.sheets_processed} of ${s.sheets_total}`, formatNumber(rec.source_data_rows), formatNumber(report.issues_found ?? 0), s.composite_score != null ? `${Math.round(s.composite_score)}/100 · grade ${report.grade ?? s.grade ?? "—"}` : "—"], widths: [0.25, 0.25, 0.25, 0.25] },
      { kind: "rule" },
      { kind: "heading", text: "Findings" },
      { kind: "row", cells: ["Severity", "Check", "Rows"], widths: [0.2, 0.6, 0.2], bold: true },
      ...rules.map(([k, v]) => ({ kind: "row" as const, cells: [RULE_SEV[k]?.[0] ?? "Medium", RULE_LABEL[k] ?? k.replace(/_/g, " "), formatNumber(v)], widths: [0.2, 0.6, 0.2] })),
      { kind: "row", cells: ["Medium", "Exact resubmissions", formatNumber(s.exact_duplicates)], widths: [0.2, 0.6, 0.2] },
      { kind: "row", cells: ["Info", "Claim development (not duplicates)", formatNumber(s.development_pairs ?? 0)], widths: [0.2, 0.6, 0.2] },
      { kind: "rule" },
      { kind: "heading", text: "What was not checked" },
      ...(s.unmapped_source_columns ?? []).flatMap((u) => u.columns.map((c) => ({ kind: "text" as const, text: `“${c}” (${u.sheet_name}) — unmapped. Kept on every row; not validated.` }))),
      ...na.map((c) => ({ kind: "text" as const, text: `${c.label} — not assessed. ${c.reason}` })),
      ...(unmappedCols === 0 && na.length === 0 ? [{ kind: "text" as const, text: "Every column was mapped and every check was assessed." }] : []),
      { kind: "rule" },
      { kind: "heading", text: "Evidence" },
      { kind: "row", cells: ["Source hash", `sha256 ${report.source_sha256 ?? "—"}`], widths: [0.25, 0.75] },
      { kind: "row", cells: ["Ruleset", "Lloyd’s CRS v5.2"], widths: [0.25, 0.75] },
      { kind: "row", cells: ["Rows reconcile", rec.reconciles ? "Yes — every source row accounted for" : "No — see the reconciliation"], widths: [0.25, 0.75] },
      { kind: "row", cells: ["Source values", "Unchanged"], widths: [0.25, 0.75] },
    ];
    downloadPdf(`${name}_Health_Check.pdf`, blocks, `TrueBind Health Check · ${report.file_name}`);
    toast(`Downloaded ${name}_Health_Check.pdf`, "ok");
  };

  return (
    <>
      <div className="no-print grid w-full max-w-[1100px] grid-cols-2 gap-2 sm:flex sm:flex-wrap sm:justify-end">
        <Link href={`/exceptions?reportId=${report.id}`} className="tb-btn">Exceptions</Link>
        <Link href={`/duplicates?reportId=${report.id}`} className="tb-btn">Duplicates</Link>
        <button type="button" className="tb-btn" onClick={() => window.print()} title="Print" aria-label="Print"><Printer /><span className="sm:hidden">Print</span></button>
        <button type="button" className="tb-btn" onClick={pdf}><FilePdf />PDF</button>
        <button type="button" className="tb-btn !whitespace-normal text-center" onClick={() => void exportFile(api.exportExceptionsUrl(report.id), `${name}_exceptions`, toast)}><DownloadSimple className="flex-none" />Export exceptions</button>
        <button type="button" className="tb-btn" onClick={() => void exportFile(api.auditPackUrl(report.id), `${name}_audit_pack`, toast)}><FileArchive />Audit pack</button>
        <button type="button" className="tb-btn tb-btn-primary col-span-2" onClick={() => setSend(true)}><EnvelopeSimple />Send</button>
      </div>

      <article className="flex w-full max-w-[1100px] flex-col gap-9 rounded-md px-6 pb-[52px] pt-[60px] sm:px-[68px]" style={{ background: "#fbfbfd", color: "#1c1e2a", boxShadow: "0 0 0 1px rgba(28,30,42,.08), 0 20px 50px rgba(0,0,0,.25)" }}>
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-[9px] text-[15px] font-semibold"><Mark size={24} radius={6} />TrueBind</div>
          <div className="tnum text-right text-[11px] leading-[1.6]" style={{ color: "#595d6c" }}>
            {report.id.slice(0, 8).toUpperCase()}
            <br />
            {report.sender ? `From ${report.sender}` : "Sender not recorded"}
            <br />
            {new Date(report.created_at).toLocaleDateString("en-IE", { day: "numeric", month: "long", year: "numeric" })}
          </div>
        </div>
        <div className="flex flex-col gap-3">
          <span className="text-[11.5px] font-medium uppercase tracking-[.1em]" style={{ color: "#5d5294" }}>Bordereau Health Check</span>
          <h1 className="m-0 text-[26px] font-medium leading-[1.15] tracking-[-0.025em] [text-wrap:balance] sm:text-[32px]">{headline(report, s)}</h1>
          <p className="m-0 text-[14px] leading-[1.6]" style={{ color: "#3f424d" }}>
            {[report.sender, report.programme, report.file_name, `${s.sheets_total} sheet${s.sheets_total === 1 ? "" : "s"}`, `received ${formatDateTime(report.created_at)}`].filter(Boolean).join(" · ")}
          </p>
          {provisionalReason(s) && <p className="m-0 text-[13px]" style={{ color: "#9d5d03" }}>{provisionalReason(s)}</p>}
        </div>
        <div className="flex flex-col gap-3">
          <div className="flex h-3 gap-0.5 overflow-hidden rounded-[3px]" style={{ background: "rgba(28,30,42,.06)" }}>
            <div style={{ width: pct(clean), background: "oklch(0.58 0.12 155)" }} />
            <div style={{ width: pct(flagged), background: "oklch(0.75 0.14 75)" }} />
            <div style={{ width: pct(rec.unmapped_rows), boxShadow: "inset 0 0 0 1px #676b7e", background: "repeating-linear-gradient(45deg,#676b7e 0 2px,transparent 2px 4px)" }} />
            <div style={{ width: pct(excluded), background: "#b2b6ca" }} />
          </div>
          <div className="grid grid-cols-2 gap-4 text-[12.5px] sm:grid-cols-4">
            {[
              ["oklch(0.58 0.12 155)", "Checked", `${formatNumber(clean)} rows`],
              ["oklch(0.75 0.14 75)", "Flagged", `${formatNumber(flagged)} rows`],
              ["hatch", "Unmapped", `${unmappedCols} column${unmappedCols === 1 ? "" : "s"}${rec.unmapped_rows ? ` · ${formatNumber(rec.unmapped_rows)} rows` : ""}`],
              ["#b2b6ca", "Not assessed", `${na.length} check${na.length === 1 ? "" : "s"} · ${formatNumber(excluded)} rows excluded`],
            ].map(([c, l, v]) => (
              <div key={l} className="flex flex-col gap-[3px]">
                <span className="flex items-center gap-[7px]" style={{ color: "#595d6c" }}>
                  <span className="h-2 w-2 rounded-[2px]" style={c === "hatch" ? { boxShadow: "inset 0 0 0 1px #676b7e", background: "repeating-linear-gradient(45deg,#676b7e 0 2px,transparent 2px 4px)" } : { background: c }} />
                  {l}
                </span>
                <span className="text-[15px] font-medium">{v}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4" style={{ boxShadow: "0 -1px 0 rgba(28,30,42,.12), 0 1px 0 rgba(28,30,42,.12)" }}>
          {[
            ["Sheets processed", `${s.sheets_processed} of ${s.sheets_total}`],
            ["Source rows", formatNumber(rec.source_data_rows)],
            ["Findings", formatNumber(report.issues_found ?? 0)],
            ["Health score", s.composite_score != null ? `${Math.round(s.composite_score)}/100` : "—", [s.grade_label, s.score_reliable === false ? "provisional" : null].filter(Boolean).join(" · ")],
          ].map(([l, v, note], i) => (
            <div key={l} className="flex flex-col gap-1 py-4" style={{ paddingLeft: i ? 14 : 0, paddingRight: 14, boxShadow: i ? "-1px 0 0 rgba(28,30,42,.08)" : "none" }}>
              <span className="text-[12px]" style={{ color: "#595d6c" }}>{l}</span>
              <span className="tnum text-[24px] font-medium">{v}</span>
              {note && <span className="text-[12px]" style={{ color: "#595d6c" }}>{note}</span>}
            </div>
          ))}
        </div>
        <div className="flex flex-col gap-2.5">
          <span className="text-[15px] font-semibold">Findings</span>
          <div className="overflow-x-auto">
            <div>
              <div className="grid gap-x-3.5 pb-2 text-[11px] font-medium uppercase tracking-[.06em]" style={{ gridTemplateColumns: "76px minmax(0,1fr) 56px", boxShadow: "0 1px 0 rgba(28,30,42,.12)", color: "#676b7e" }}>
                <span>Severity</span>
                <span>Check</span>
                <span className="text-right">Rows</span>
              </div>
              {[
                ...rules.map(([k, v]) => ({ k, sev: RULE_SEV[k] ?? (["Medium", "oklch(0.5 0.1 255)"] as const), label: RULE_LABEL[k] ?? k.replace(/_/g, " "), n: formatNumber(v), href: `/exceptions?reportId=${report.id}` })),
                { k: "exact", sev: ["Medium", "oklch(0.5 0.1 255)"] as const, label: "Exact resubmission", n: formatNumber(s.exact_duplicates), href: `/duplicates?reportId=${report.id}` },
                { k: "probable", sev: ["Medium", "oklch(0.5 0.1 255)"] as const, label: "Probable duplicate", n: probableDuplicatesValue(s), href: `/duplicates?reportId=${report.id}` },
                { k: "dev", sev: ["Info", "#676b7e"] as const, label: "Claim development (not duplicates)", n: formatNumber(s.development_pairs ?? 0), href: `/duplicates?reportId=${report.id}` },
              ].map((f) => (
                <Link key={f.k} href={f.href} className="tnum grid items-baseline gap-x-3.5 py-2.5 text-[13px] hover:bg-[rgba(121,108,191,.06)]" style={{ gridTemplateColumns: "76px minmax(0,1fr) 56px", boxShadow: "0 1px 0 rgba(28,30,42,.06)" }}>
                  <span className="flex items-center gap-[7px] text-[12px]" style={{ color: f.sev[1] }}>
                    <span className="h-[7px] w-[7px] rounded-full" style={{ background: f.sev[1] }} />
                    {f.sev[0]}
                  </span>
                  <span>{f.label}</span>
                  <span className="text-right">{f.n}</span>
                </Link>
              ))}
            </div>
          </div>
        </div>
        <div className="grid gap-9" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(260px,1fr))" }}>
          <div className="flex flex-col gap-2.5">
            <span className="text-[15px] font-semibold">What was not checked</span>
            <div className="flex flex-col gap-2 text-[13px] leading-[1.5]" style={{ color: "#3f424d" }}>
              {(s.unmapped_source_columns ?? []).flatMap((u) => u.columns.map((c) => <span key={`${u.sheet_name}-${c}`}>“{c}” ({u.sheet_name}) — unmapped. Kept on every row; not validated.</span>))}
              {na.map((c) => <span key={c.check}>{c.label} — not assessed. {c.reason}</span>)}
              {[...s.skipped_sheets, ...s.unmapped_sheets].map((x) => <span key={x.sheet_name}>Sheet “{x.sheet_name}” — {x.reason}</span>)}
              {unmappedCols === 0 && na.length === 0 && s.skipped_sheets.length === 0 && s.unmapped_sheets.length === 0 && <span>Every column was mapped and every check was assessed.</span>}
            </div>
          </div>
          <div className="flex flex-col gap-2.5">
            <span className="text-[15px] font-semibold">Evidence</span>
            <div className="tnum grid grid-cols-[minmax(84px,110px)_minmax(0,1fr)] [overflow-wrap:anywhere] gap-y-1.5 text-[12.5px]">
              <span style={{ color: "#595d6c" }}>Source hash</span>
              <span className="truncate" title={report.source_sha256 ?? ""}>sha256 {report.source_sha256 ? `${report.source_sha256.slice(0, 10)}…${report.source_sha256.slice(-6)}` : "—"}</span>
              <span style={{ color: "#595d6c" }}>Ruleset</span>
              <span>Lloyd’s CRS v5.2</span>
              <span style={{ color: "#595d6c" }}>Reconciliation</span>
              <span>{rec.reconciles ? "Every source row accounted for" : "Rows do not reconcile"}</span>
              <span style={{ color: "#595d6c" }}>Audit chain</span>
              <Link href={`/audit?reportId=${report.id}`} className="underline decoration-[#b2b6ca] underline-offset-2">View and verify</Link>
              <span style={{ color: "#595d6c" }}>Retained until</span>
              <span>{formatDateTime(report.expires_at)}</span>
              <span style={{ color: "#595d6c" }}>Source values</span>
              <span>Unchanged</span>
            </div>
          </div>
        </div>
        {s.coverage_statement && (
          <div className="pt-4 text-[11px]" style={{ boxShadow: "0 -1px 0 rgba(28,30,42,.12)", color: "#676b7e" }}>{s.coverage_statement}</div>
        )}
      </article>

      <div className="no-print flex w-full max-w-[1100px] flex-col gap-8">
        <Section id="financial" kicker="Financial" title="Money by currency" sub="Sums of the values reported in the file. Currencies are never added together; blanks are not treated as zero.">
          <div className="tb-card overflow-x-auto">
            <table className="w-full min-w-[640px] border-collapse text-[13px]">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-[.06em]" style={{ color: "var(--faint)" }}>
                  {["Currency", "Rows", "Paid to date", "Paid expenses / ALAE", "Reserve", "Total incurred"].map((h, i) => <th key={h} className={`px-4 py-2.5 font-medium ${i ? "text-right" : ""}`}>{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {totals.map((t) => (
                  <tr key={t.currency} className="tnum" style={{ boxShadow: "0 -1px 0 var(--line)" }}>
                    <td className="px-4 py-2.5 font-medium">{t.currency === "UNKNOWN" ? "Not stated" : t.currency}</td>
                    <td className="px-4 py-2.5 text-right">{formatNumber(t.rows)}</td>
                    <td className="px-4 py-2.5 text-right">{formatMoney(t.paid_to_date, t.currency)}</td>
                    <td className="px-4 py-2.5 text-right">{t.fees_rows ? formatMoney(t.fees_paid_to_date ?? 0, t.currency) : "—"}</td>
                    <td className="px-4 py-2.5 text-right">{formatMoney(t.reserve, t.currency)}</td>
                    <td className="px-4 py-2.5 text-right">
                      <div className="font-medium">{formatMoney(t.incurred, t.currency)}</div>
                      <div className="text-[11.5px]" style={{ color: "var(--faint)" }}>{formatNumber(t.incurred_rows ?? t.rows)} of {formatNumber(t.rows)} rows report a value</div>
                    </td>
                  </tr>
                ))}
                {!totals.length && <tr><td colSpan={6} className="px-4 py-4" style={{ color: "var(--faint)" }}>No monetary columns were mapped in this file.</td></tr>}
              </tbody>
            </table>
          </div>
          <span className="text-[12px]" style={{ color: "var(--faint)" }}>Total incurred across currencies: {impact}</span>
        </Section>

        <Section id="claims" kicker="Claims" title="What the file contains">
          <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-2">
            <div className="tb-card flex flex-col gap-3 p-5">
              <span className="text-[14px] font-medium">Claims by status</span>
              <Bars items={Object.entries(s.claim_status_counts ?? {}).map(([k, v]) => [k.charAt(0).toUpperCase() + k.slice(1), v])} empty="No claim-status column was mapped." />
            </div>
            <div className="tb-card flex flex-col gap-3 p-5">
              <span className="flex items-center justify-between text-[14px] font-medium">Row reconciliation <StatusPill tone={rec.reconciles ? "ok" : "err"}>{rec.reconciles ? "Reconciles" : "Does not reconcile"}</StatusPill></span>
              <dl className="tnum m-0 grid grid-cols-[1fr_auto] gap-y-1.5 text-[13px]">
                {[
                  ["Source data rows", rec.source_data_rows],
                  ["Claim rows exported", rec.exported_rows],
                  ["Structural rows excluded", rec.rejected_rows],
                  ["Rows on unmapped sheets", rec.unmapped_rows],
                  ["Summary-sheet rows (not claims)", rec.non_claim_summary_rows],
                  ["Duplicate rows (kept, flagged)", rec.duplicate_rows],
                  ["Rows requiring review", rec.rows_requiring_review],
                ].map(([l, v]) => (
                  <div key={l as string} className="contents">
                    <dt style={{ color: "var(--muted)" }}>{l}</dt>
                    <dd className="m-0 text-right">{formatNumber(v as number)}</dd>
                  </div>
                ))}
              </dl>
              <span className="text-[12px]" style={{ color: "var(--faint)" }}>Every source row is either a claim or a recorded exclusion with a reason; nothing is silently dropped.</span>
            </div>
          </div>
        </Section>

        <Section id="quality" kicker="Data quality" title="Completeness and structure">
          <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-2">
            <div className="tb-card flex flex-col gap-3 p-5">
              <span className="text-[14px] font-medium">Field completeness</span>
              <Bars pct items={[...s.field_completeness].sort((a, b) => a.present / Math.max(a.denominator, 1) - b.present / Math.max(b.denominator, 1)).map((f) => [f.never_mapped ? `${f.field_name} (not in file)` : f.field_name, f.never_mapped ? 0 : (100 * f.present) / Math.max(f.denominator, 1)])} empty="No fields assessed." />
              {s.arithmetic_not_evaluable > 0 && (
                <span className="text-[12.5px]" style={{ color: "var(--warn)" }}>
                  {formatNumber(s.arithmetic_not_evaluable)} row{s.arithmetic_not_evaluable === 1 ? "" : "s"} could not be checked for arithmetic: {Object.entries(s.not_evaluable_by_reason ?? {}).map(([k, v]) => `${k.replace(/_/g, " ")} (${v})`).join(", ")}.
                </span>
              )}
            </div>
            <div className="tb-card flex flex-col gap-3 p-4 sm:p-6 lg:col-start-1" id="period">
              <span className="text-[14px] font-medium">Periods in this file</span>
              <span className="text-[12.5px]" style={{ color: "var(--muted)" }}>Rows per reporting period as stated in the file.</span>
              {periods.length ? (
                <Bars items={periods} empty="" />
              ) : (
                <span className="text-[12.5px]" style={{ color: "var(--faint)" }}>{Object.keys(s).includes("reporting_periods") ? "No reporting-period column was mapped in this file." : "Reprocess this file to see its reporting periods."}</span>
              )}
              {(s.period_unknown_repeats ?? 0) > 0 && (
                <span className="text-[12.5px]" style={{ color: "var(--warn)" }}>{formatNumber(s.period_unknown_repeats ?? 0)} repeated reference(s) could not be classified because the period is missing.</span>
              )}
            </div>
            <div className="flex flex-col gap-4">
              <div className="tb-card flex flex-col gap-3 p-5">
                <span className="text-[14px] font-medium">Recommended next actions</span>
                <Recommendations items={s.recommendations ?? []} reportId={report.id} />
              </div>
              <ExcludedRows reportId={report.id} />
            </div>
          </div>
        </Section>

        <Section id="checks" kicker="Checks" title="Binder, leakage and sanctions checks" sub="Each check says what it assessed and what it could not. Findings point to the sheet, row and column; confirm or dismiss each one.">
          <ChecksPanel report={report} />
        </Section>

        <Sheets reportId={report.id} s={s} />
        <Lineage report={report} />
        <Outputs report={report} name={name} />
      </div>

      <SendModal open={send} onClose={() => setSend(false)} report={report} />
    </>
  );
}

function Section({ id, kicker, title, sub, children }: { id: string; kicker: string; title: string; sub?: string; children: React.ReactNode }) {
  return (
    <section id={id} className="flex scroll-mt-20 flex-col gap-3">
      <div className="flex flex-col gap-1">
        <span className="kicker">{kicker}</span>
        <h2 className="m-0 text-[20px] font-medium tracking-[-0.015em]">{title}</h2>
        {sub && <p className="m-0 max-w-[720px] text-[13.5px]" style={{ color: "var(--muted)" }}>{sub}</p>}
      </div>
      {children}
    </section>
  );
}

function Bars({ items, pct, empty }: { items: [string, number][]; pct?: boolean; empty: string }) {
  if (!items.length) return <span className="text-[13px]" style={{ color: "var(--faint)" }}>{empty}</span>;
  const max = pct ? 100 : Math.max(1, ...items.map(([, v]) => v));
  return (
    <ul className="m-0 flex list-none flex-col gap-2 p-0">
      {items.map(([l, v]) => (
        <li key={l} className="grid grid-cols-[minmax(0,1fr)_minmax(80px,1.2fr)_56px] items-center gap-3 text-[12.5px]">
          <span className="truncate" style={{ color: "var(--muted)" }}>{l}</span>
          <span className="h-1.5 rounded-full" style={{ background: "var(--line)" }}>
            <span className="block h-1.5 rounded-full" style={{ width: `${(v / max) * 100}%`, background: pct ? (v >= 99.5 ? "var(--ok)" : "var(--warn)") : "var(--accent)" }} />
          </span>
          <span className="tnum text-right">{pct ? `${v.toFixed(0)}%` : formatNumber(v)}</span>
        </li>
      ))}
    </ul>
  );
}

function ExcludedRows({ reportId }: { reportId: string }) {
  const rows = useApi(() => api.listExcludedRows(reportId), [reportId]);
  const [open, setOpen] = useState(false);
  const list = rows.data ?? [];
  return (
    <div className="tb-card flex flex-col gap-2 p-5">
      <button type="button" className="tb-hit flex cursor-pointer items-center justify-between gap-3 text-left text-[14px] font-medium" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        Rows excluded before assessment
        <span className="tnum text-[12.5px] font-normal" style={{ color: "var(--faint)" }}>{rows.data ? `${formatNumber(list.length)} · ${open ? "hide" : "show"}` : "…"}</span>
      </button>
      <span className="text-[12px]" style={{ color: "var(--faint)" }}>Blank, title, total and repeated-header rows: recorded with their reason, never counted as claims.</span>
      {open && (
        <ul className="m-0 flex max-h-[260px] list-none flex-col overflow-y-auto p-0 text-[12.5px]">
          {list.length === 0 && <li style={{ color: "var(--faint)" }}>No rows were excluded.</li>}
          {list.map((r) => (
            <li key={r.id} className="grid grid-cols-[minmax(84px,110px)_minmax(0,1fr)] [overflow-wrap:anywhere] gap-2 py-1" style={{ boxShadow: "0 1px 0 var(--line)" }}>
              <span className="tnum" style={{ color: "var(--muted)" }}>{r.sheet_name} · {r.row_number}{r.row_count && r.row_count > 1 ? `+${r.row_count - 1}` : ""}</span>
              <span>{r.reason.replace(/_/g, " ")} — {r.detail}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Sheets({ reportId, s }: { reportId: string; s: ReportSummary }) {
  const sheets = useApi(() => api.listSheets(reportId), [reportId]);
  const byName = Object.fromEntries((sheets.data ?? []).map((x) => [x.sheet_name, x]));
  const TONE: Record<string, "ok" | "warn" | "err" | "muted" | "med"> = { mapped: "ok", partial: "warn", unmapped: "err", empty: "muted", error: "err", non_claim_summary: "med" };
  return (
    <Section id="sheets" kicker="Mapping" title="Sheets and column mapping" sub="How each sheet was understood. Every mapping change is audited.">
      <span id="mapping" className="absolute" />
      <Link href={`/upload?reportId=${reportId}`} className="tb-btn self-start">Change mapping</Link>
      <div className="tb-card overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-[13px]">
          <thead>
            <tr className="text-left text-[11px] uppercase tracking-[.06em]" style={{ color: "var(--faint)" }}>
              {["Sheet", "Status", "Rows assessed", "Excluded", "Fields mapped", "Notes"].map((h, i) => <th key={h} className={`px-4 py-2.5 font-medium ${i >= 2 && i <= 4 ? "text-right" : ""}`}>{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {(s.sheet_audit ?? []).map((a) => {
              const sh = byName[a.sheet_name];
              return (
                <tr key={a.sheet_name} style={{ boxShadow: "0 -1px 0 var(--line)" }}>
                  <td className="px-4 py-2.5 font-medium">{a.sheet_name}{sh?.hidden ? <span className="ml-2 text-[11.5px] font-normal" style={{ color: "var(--faint)" }}>hidden</span> : null}</td>
                  <td className="px-4 py-2.5"><StatusPill tone={TONE[a.status] ?? "muted"}>{a.status.replace(/_/g, " ")}</StatusPill><div className="mt-1 text-[12px]" style={{ color: "var(--faint)" }}>{a.reason}</div></td>
                  <td className="tnum px-4 py-2.5 text-right">{formatNumber(a.rows_processed)}</td>
                  <td className="tnum px-4 py-2.5 text-right">{formatNumber(a.rows_rejected)}</td>
                  <td className="tnum px-4 py-2.5 text-right">{a.fields_mapped}</td>
                  <td className="px-4 py-2.5 text-[12px]" style={{ color: "var(--muted)" }}>{[...(sh?.notes ?? []), sh?.trailing_blank_rows ? `${sh.trailing_blank_rows} trailing blank rows` : ""].filter(Boolean).join(" · ") || "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Section>
  );
}

function Lineage({ report }: { report: Report }) {
  const jobs = useApi(() => api.reportJobs(report.id), [report.id]);
  const audit = useApi(() => api.getAuditLog(report.id), [report.id]);
  return (
    <Section id="lineage" kicker="Lineage" title="Where every number came from" sub="The source file’s fingerprint and every recorded step, newest first. The audit trail is hash-chained.">
      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        <div className="tb-card flex flex-col gap-3 p-5">
          <span className="text-[14px] font-medium">Recorded steps</span>
          {audit.error ? <ErrorState title="Steps could not be loaded" message={audit.error} onRetry={audit.reload} /> : !audit.data ? <LoadingState label="Loading steps" rows={5} /> : (
            <ol className="m-0 flex list-none flex-col gap-2 p-0">
              {audit.data.slice(0, 12).map((e) => {
                const d = describeAudit(e);
                return (
                  <li key={e.id} className="flex flex-col text-[12.5px]" style={{ boxShadow: "0 1px 0 var(--line)", paddingBottom: 6 }}>
                    <span>{d.title}</span>
                    {d.detail && <span style={{ color: "var(--muted)" }}>{d.detail}</span>}
                    <span className="tnum text-[11.5px]" style={{ color: "var(--faint)" }}>{formatDateTime(e.created_at)} · {e.actor}{e.seq !== undefined ? ` · #${e.seq}` : ""}</span>
                  </li>
                );
              })}
            </ol>
          )}
          {(audit.data?.length ?? 0) > 12 && <Link href={`/audit?reportId=${report.id}`} className="text-[12.5px]" style={{ color: "var(--accentText)" }}>See all {audit.data?.length} entries →</Link>}
        </div>
        <div className="flex flex-col gap-4">
          <div className="tb-card flex flex-col gap-3 p-5">
            <span className="text-[14px] font-medium">Source file</span>
            <dl className="tnum m-0 grid grid-cols-[minmax(84px,110px)_minmax(0,1fr)] [overflow-wrap:anywhere] gap-y-1.5 text-[12.5px]">
              {[
                ["File", report.file_name],
                ["Type", (report.file_kind ?? "").toUpperCase()],
                ["Size", formatBytes(report.file_size_bytes)],
                ["SHA-256", report.source_sha256 ? `${report.source_sha256.slice(0, 20)}…` : "—"],
                ["Channel", report.source_channel === "upload" ? "Web upload" : report.source_channel ?? "—"],
                ["Sender", report.sender ?? "—"],
                ["Programme", report.programme ?? "—"],
                ["Received", formatDateTime(report.created_at)],
                ["Retained until", formatDateTime(report.expires_at)],
              ].map(([l, v]) => (
                <div key={l} className="contents">
                  <dt style={{ color: "var(--faint)" }}>{l}</dt>
                  <dd className="m-0 truncate" title={l === "SHA-256" ? report.source_sha256 ?? "" : undefined}>{v}</dd>
                </div>
              ))}
            </dl>
          </div>
          <div id="history" className="tb-card flex flex-col gap-3 p-5">
            <span className="text-[14px] font-medium">Processing history</span>
            {(jobs.data ?? []).map((j) => {
              const m = (j.metrics ?? {}) as Record<string, unknown>;
              const dur = j.started_at && j.finished_at ? (new Date(j.finished_at).getTime() - new Date(j.started_at).getTime()) / 1000 : null;
              return (
                <div key={j.id} className="flex flex-col gap-0.5 text-[12.5px]">
                  <span className="flex items-center justify-between gap-2">
                    <span className="font-medium">{j.kind === "INGEST" ? "Read workbook & propose mapping" : "Validate & build report"}</span>
                    <StatusPill tone={j.status === "SUCCEEDED" ? "ok" : j.status === "FAILED" ? "err" : "med"}>{j.status.toLowerCase()}</StatusPill>
                  </span>
                  <span className="tnum" style={{ color: "var(--faint)" }}>{formatDateTime(j.created_at)} · attempt {j.attempts} · {formatDuration(dur)}{typeof m.rows === "number" ? ` · ${formatNumber(m.rows as number)} rows` : ""}{typeof m.ai_calls === "number" ? ` · ${m.ai_calls} AI call${m.ai_calls === 1 ? "" : "s"}` : ""}</span>
                  {Object.keys((m.stage_timings ?? {}) as Record<string, number>).length > 0 && (
                    <span className="tnum flex flex-wrap gap-x-3" style={{ color: "var(--muted)" }}>
                      {Object.entries(m.stage_timings as Record<string, number>).map(([k, v]) => <span key={k}>{k.replace(/_/g, " ")} <b className="font-medium">{formatDuration(v)}</b></span>)}
                    </span>
                  )}
                  {j.error_message && <span style={{ color: "var(--err)" }}>{j.error_message}</span>}
                </div>
              );
            })}
            {jobs.data && !jobs.data.length && <span className="text-[12.5px]" style={{ color: "var(--faint)" }}>No jobs recorded.</span>}
          </div>
        </div>
      </div>
    </Section>
  );
}

function Outputs({ report, name }: { report: Report; name: string }) {
  const { toast } = useUi();
  const deliveries = useApi(() => api.listDeliveries(), [report.id]);
  const mine = (deliveries.data?.items ?? []).filter((d) => d.report_id === report.id);
  const outputs = [
    { title: "Claims", body: "Every claim row with its source sheet and row, unmapped columns and findings.", url: api.exportClaimsUrl(report.id), file: `${name}_claims` },
    { title: "Exceptions", body: "Every finding with severity, rule and the source row it concerns.", url: api.exportExceptionsUrl(report.id), file: `${name}_exceptions` },
    { title: "Audit trail", body: "Hash-chained history of everything that happened to this file.", url: api.exportAuditCsvUrl(report.id), file: `${name}_audit` },
  ];
  return (
    <Section id="exports" kicker="Exports" title="Outputs and deliveries" sub="Every export is generated from the stored results and recorded in the audit trail.">
      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 md:grid-cols-3">
        {outputs.map((o) => (
          <div key={o.title} className="tb-card flex flex-col gap-2 p-5">
            <span className="text-[14px] font-medium">{o.title}</span>
            <span className="flex-1 text-[12.5px]" style={{ color: "var(--muted)" }}>{o.body}</span>
            <button type="button" className="tb-btn self-start" onClick={() => void exportFile(o.url, o.file, toast).then(() => setTimeout(deliveries.reload, 800))}><DownloadSimple />Download</button>
          </div>
        ))}
      </div>
      <div className="tb-card flex flex-col gap-2 p-5">
        <span className="text-[14px] font-medium">Delivered outputs</span>
        {mine.length ? (
          mine.map((d) => (
            <span key={d.id} className="flex flex-wrap items-center gap-2 text-[12.5px]">
              <StatusPill tone={d.status === "DELIVERED" ? "ok" : d.status === "FAILED" ? "err" : "muted"}>{d.status.toLowerCase().replace("_", " ")}</StatusPill>
              {d.kind.replace("_csv", "")} · {d.channel}{d.destination ? ` → ${d.destination}` : ""} · {timeAgo(d.created_at)}
              {d.error && <span style={{ color: "var(--err)" }}>· {d.error}</span>}
            </span>
          ))
        ) : (
          <span className="text-[12.5px]" style={{ color: "var(--faint)" }}>Nothing delivered from this report yet.</span>
        )}
      </div>
    </Section>
  );
}

function SendModal({ open, onClose, report }: { open: boolean; onClose: () => void; report: Report }) {
  const { toast } = useUi();
  const channels = useApi(() => (open ? api.channels() : Promise.resolve(null)), [open]);
  const [kind, setKind] = useState("exceptions_csv");
  const [to, setTo] = useState("");
  const [busy, setBusy] = useState(false);
  const email = channels.data?.outbound.find((c) => c.id === "email");
  const ready = email?.status === "active";
  const submit = async () => {
    setBusy(true);
    try {
      const d = await api.sendDelivery(report.id, kind, to.trim());
      toast(d.status === "DELIVERED" ? `Sent to ${d.destination} · recorded in the audit trail` : d.error ?? "Not sent.", d.status === "DELIVERED" ? "ok" : "warn");
      if (d.status === "DELIVERED") onClose();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Could not send.", "err");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      open={open}
      onClose={onClose}
      kicker="Send an output"
      title="Email this report’s output"
      actions={
        <>
          <button className="tb-btn" onClick={onClose}>Cancel</button>
          <button className="tb-btn tb-btn-solid" disabled={!ready || busy || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(to)} onClick={() => void submit()}>{busy ? "Sending…" : "Send"}</button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        {!channels.data ? <span>Checking the email channel…</span> : !ready ? <span style={{ color: "var(--warn)" }}>{email?.detail ?? "Outbound email isn’t configured on this server."} Downloads work now.</span> : <span>The file is generated from the stored results and the delivery is recorded in the audit trail.</span>}
        <div>
          <label className="tb-label" htmlFor="sd-kind">Output</label>
          <select id="sd-kind" className="tb-input" value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="claims_csv">Claims</option>
            <option value="exceptions_csv">Exceptions</option>
            <option value="audit_csv">Audit trail</option>
          </select>
        </div>
        <div>
          <label className="tb-label" htmlFor="sd-to">Recipient</label>
          <input id="sd-to" className="tb-input" type="email" value={to} onChange={(e) => setTo(e.target.value)} placeholder="recipient@company.com" />
        </div>
      </div>
    </Modal>
  );
}
