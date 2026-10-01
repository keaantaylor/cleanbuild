"use client";

import Link from "next/link";
import { use, useEffect, useRef, useState } from "react";
import { ArrowLeft, DownloadSimple, EnvelopeSimple, FileArchive, FilePdf, Printer } from "@phosphor-icons/react";
import { api, ApiError, IN_PROGRESS } from "@/lib/api";
import type { HealthRule, HealthView, Report, ReportSummary } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { useUi } from "@/lib/ui";
import { useShell } from "@/components/layout/ShellContext";
import { describeAudit } from "@/lib/audit";
import { provisionalReason } from "@/lib/findings";
import { TONE, severityLabel } from "@/lib/severity";
import { formatBytes, formatDateTime, formatDuration, formatMoney, formatNumber, timeAgo } from "@/lib/formatters";
import { EmptyState, ErrorState, LoadingState, Mark, Modal, StatusPill } from "@/components/nocturne/ui";
import { ProcessingPanel } from "@/components/nocturne/intake";
import { reportStatus } from "@/components/nocturne/status";
import { ChecksPanel } from "@/components/nocturne/checks";
import { exportFile } from "@/lib/exports";
import { downloadPdf, type PdfBlock } from "@/lib/pdf";

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

const PAPER = { text: "#1c1e2a", muted: "#3f424d", faint: "#555a69", line: "rgba(28,30,42,.12)" };

function moneyList(items: { currency: string; amount: number }[]) {
  return items.map((m) => (m.currency === "UNKNOWN" ? `${formatNumber(Math.round(m.amount))} (currency not stated)` : formatMoney(m.amount, m.currency))).join(" · ");
}

function plural(n: number, one: string, many = `${one}s`) {
  return `${formatNumber(n)} ${n === 1 ? one : many}`;
}

/** The PDF follows the page: verdict, three counts, top fixes, couldn't check, then the sections. */
function healthPdf(report: Report, s: ReportSummary, hv: HealthView): PdfBlock[] {
  const W3 = [0.34, 0.33, 0.33];
  const rule = (r: HealthRule): PdfBlock[] => [
    { kind: "row", cells: [r.outcome === "FAIL" ? "Error" : "Warning", `${severityLabel(r.severity)} · ${r.label}`, plural(r.findings, "finding")], widths: [0.14, 0.66, 0.2], tones: [r.outcome === "FAIL" ? "err" : "warn"] },
    ...r.examples.slice(0, 1).map((e) => ({ kind: "muted" as const, text: `${e.where}: ${e.sentence}` })),
    ...(r.money_at_risk.length ? [{ kind: "muted" as const, text: `Money on these rows: ${moneyList(r.money_at_risk)}` }] : []),
    { kind: "muted", text: `Fix: ${r.fix}` },
    { kind: "space", h: 4 },
  ];
  const byOwner = (owner: "sender" | "us") => hv.rules.filter((r) => r.owner === owner);
  return [
    { kind: "kicker", text: `TRUEBIND · BORDEREAU HEALTH CHECK · ${report.id.slice(0, 8).toUpperCase()}` },
    { kind: "muted", text: `${report.file_name} · received ${formatDateTime(report.created_at)}${report.sender ? ` · from ${report.sender}` : ""}` },
    { kind: "space", h: 8 },
    { kind: "callout", text: hv.verdict_label, sub: hv.verdict_reason, tone: hv.verdict === "ready" ? "ok" : "err" },
    { kind: "row", cells: ["Errors", "Warnings", "Couldn't check"], widths: W3, bold: true },
    { kind: "row", cells: [`${formatNumber(hv.counts.errors)} on ${plural(hv.counts.error_rows, "row")}`, formatNumber(hv.counts.warnings), plural(hv.counts.couldnt_check, "check")], widths: W3, tones: ["err", "warn", "muted"] },
    { kind: "rule" },
    { kind: "heading", text: hv.top_fixes.length ? `Top ${hv.top_fixes.length} fixes` : "Nothing to fix" },
    ...hv.top_fixes.flatMap(rule),
    ...(hv.couldnt_check.length
      ? [{ kind: "rule" as const }, { kind: "heading" as const, text: "Couldn't check" }, ...hv.couldnt_check.map((c) => ({ kind: "text" as const, text: `${c.label}${c.rows ? ` (${plural(c.rows, "row")})` : ""}: ${c.reason}${c.fix === "mapping" ? " Fix: map the column." : ""}` }))]
      : []),
    { kind: "rule" },
    { kind: "heading", text: "Findings by who must fix them" },
    { kind: "text", text: "The sender (query them):" },
    ...(byOwner("sender").length ? byOwner("sender").map((r) => ({ kind: "row" as const, cells: [r.outcome === "FAIL" ? "Error" : "Warning", r.label, plural(r.findings, "finding")], widths: [0.14, 0.66, 0.2], tones: [r.outcome === "FAIL" ? ("err" as const) : ("warn" as const)] })) : [{ kind: "muted" as const, text: "Nothing." }]),
    { kind: "text", text: "Us (safe fixes in the corrected copy, or a mapping change):" },
    ...(byOwner("us").length ? byOwner("us").map((r) => ({ kind: "row" as const, cells: [r.outcome === "FAIL" ? "Error" : "Warning", r.label, plural(r.findings, "finding")], widths: [0.14, 0.66, 0.2], tones: [r.outcome === "FAIL" ? ("err" as const) : ("warn" as const)] })) : [{ kind: "muted" as const, text: "Nothing." }]),
    { kind: "rule" },
    { kind: "heading", text: "Duplicates" },
    { kind: "row", cells: ["Exact duplicates", "Probable (confidence 60+)", "Of which 80+", "Claim development"], widths: [0.25, 0.25, 0.25, 0.25], bold: true },
    { kind: "row", cells: [formatNumber(hv.duplicates.exact_pairs), hv.duplicates.probable_pairs == null ? "not run" : formatNumber(hv.duplicates.probable_pairs), formatNumber(hv.duplicates.probable_high_confidence), formatNumber(hv.duplicates.development_pairs)], widths: [0.25, 0.25, 0.25, 0.25] },
    { kind: "rule" },
    { kind: "heading", text: "Money by currency (never added together)" },
    { kind: "row", cells: ["Currency", "Rows", "Paid to date", "Reserve", "Total incurred"], widths: [0.16, 0.12, 0.24, 0.24, 0.24], bold: true },
    ...hv.money_by_currency.map((t) => ({ kind: "row" as const, cells: [t.currency === "UNKNOWN" ? "Not stated" : t.currency, formatNumber(t.rows), formatMoney(t.paid_to_date, t.currency), formatMoney(t.reserve, t.currency), formatMoney(t.incurred, t.currency)], widths: [0.16, 0.12, 0.24, 0.24, 0.24] })),
    { kind: "rule" },
    { kind: "heading", text: "Mapping" },
    ...(s.sheet_audit ?? []).map((a) => ({ kind: "row" as const, cells: [a.sheet_name, a.status.replace(/_/g, " "), `${formatNumber(a.rows_processed)} rows`, `${a.fields_mapped} fields`], widths: [0.34, 0.26, 0.2, 0.2] })),
    ...s.field_completeness.filter((f) => f.never_mapped).slice(0, 1).map(() => ({ kind: "muted" as const, text: `Not mapped: ${s.field_completeness.filter((f) => f.never_mapped).map((f) => f.field_name).join(", ")}.` })),
    { kind: "rule" },
    { kind: "row", cells: ["Source file", `sha256 ${report.source_sha256 ?? "—"}`], widths: [0.2, 0.8] },
    { kind: "row", cells: ["Rows", rec(s)], widths: [0.2, 0.8] },
    { kind: "row", cells: ["Source values", "Unchanged. TrueBind never edits the file it was sent."], widths: [0.2, 0.8] },
  ];
}

function rec(s: ReportSummary) {
  const r = s.reconciliation;
  return `${formatNumber(r.exported_rows)} claim rows from ${formatNumber(r.source_data_rows)} source rows${r.reconciles ? "; every row accounted for" : "; rows do not reconcile"}`;
}

function ReportBody({ report, s }: { report: Report; s: ReportSummary }) {
  const { toast } = useUi();
  const [send, setSend] = useState(false);
  const [tab, setTab] = useState<"owner" | "duplicates" | "money" | "mapping" | "more">("owner");
  const [reprocessing, setReprocessing] = useState(false);
  const name = report.file_name.replace(/\.\w+$/, "");
  const hv = s.health_view;

  if (!hv)
    return (
      <div className="tb-card flex w-full max-w-[1100px] flex-col items-start gap-3 p-6">
        <span className="text-[15px] font-medium">This report was produced before the new health report.</span>
        <span className="text-[13.5px]" style={{ color: "var(--muted)" }}>Process it again to see the verdict, the top fixes and every finding with its cell. The source file is unchanged; this takes a few seconds.</span>
        <button type="button" className="tb-btn tb-btn-solid" disabled={reprocessing} onClick={() => { setReprocessing(true); void api.processReport(report.id).then(() => window.location.reload()).catch((e) => { setReprocessing(false); toast(e instanceof ApiError ? e.message : "Could not start processing.", "err"); }); }}>
          {reprocessing ? "Starting…" : "Process again"}
        </button>
      </div>
    );

  const pdf = () => {
    downloadPdf(`${name}_Health_Check.pdf`, healthPdf(report, s, hv), `TrueBind Health Check · ${report.file_name}`);
    toast(`Downloaded ${name}_Health_Check.pdf`, "ok");
  };
  const ready = hv.verdict === "ready";
  const verdictTone = TONE[ready ? "ok" : "err"];
  const mappingFixes = hv.couldnt_check.filter((c) => c.fix === "mapping");
  const fixMapping = `/upload?reportId=${report.id}`;

  return (
    <>
      <div className="no-print grid w-full max-w-[1100px] grid-cols-2 gap-2 sm:flex sm:flex-wrap sm:justify-end">
        <Link href={`/exceptions?reportId=${report.id}`} className="tb-btn">All findings</Link>
        <Link href={`/duplicates?reportId=${report.id}`} className="tb-btn">Duplicates</Link>
        <button type="button" className="tb-btn" onClick={() => window.print()} title="Print" aria-label="Print"><Printer /><span className="sm:hidden">Print</span></button>
        <button type="button" className="tb-btn" onClick={pdf}><FilePdf />PDF</button>
        <button type="button" className="tb-btn !whitespace-normal text-center" onClick={() => void exportFile(api.exportExceptionsUrl(report.id), `${name}_findings`, toast)}><DownloadSimple className="flex-none" />Export findings</button>
        <button type="button" className="tb-btn" onClick={() => void exportFile(api.auditPackUrl(report.id), `${name}_audit_pack`, toast)}><FileArchive />Audit pack</button>
        <button type="button" className="tb-btn tb-btn-primary" onClick={() => setSend(true)}><EnvelopeSimple />Send</button>
      </div>

      <article className="flex w-full max-w-[1100px] flex-col gap-8 rounded-md px-6 pb-[48px] pt-[52px] sm:px-[60px]" style={{ background: "#fbfbfd", color: PAPER.text, boxShadow: "0 0 0 1px rgba(28,30,42,.08), 0 20px 50px rgba(0,0,0,.25)" }}>
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-[9px] text-[15px] font-semibold"><Mark size={24} radius={6} />TrueBind</div>
          <div className="tnum text-right text-[12px] leading-[1.6]" style={{ color: PAPER.faint }}>
            {report.id.slice(0, 8).toUpperCase()}
            <br />
            {report.sender ? `From ${report.sender}` : "Sender not recorded"}
            <br />
            {new Date(report.created_at).toLocaleDateString("en-IE", { day: "numeric", month: "long", year: "numeric" })}
          </div>
        </div>

        <div className="flex flex-col gap-2">
          <span className="text-[12px] font-semibold uppercase tracking-[.1em]" style={{ color: "#4a3f85" }}>Bordereau Health Check</span>
          <p className="m-0 text-[14px] leading-[1.6]" style={{ color: PAPER.muted }}>
            {[report.file_name, `${s.sheets_processed} of ${s.sheets_total} sheet${s.sheets_total === 1 ? "" : "s"}`, `${formatNumber(s.reconciliation.exported_rows)} claim rows`, `received ${formatDateTime(report.created_at)}`].join(" · ")}
          </p>
        </div>

        <section aria-label="Verdict" className="flex flex-col gap-1.5 rounded-md px-5 py-4" style={{ background: verdictTone.bg, color: verdictTone.fg }}>
          <h1 className="m-0 text-[28px] font-semibold leading-[1.15] tracking-[-0.02em] sm:text-[32px]">{hv.verdict_label}</h1>
          <p className="m-0 text-[14.5px] font-medium">{hv.verdict_reason}</p>
          {provisionalReason(s) && <p className="m-0 text-[13px]">{provisionalReason(s)}</p>}
        </section>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {([
            ["err", "Errors", formatNumber(hv.counts.errors), `on ${plural(hv.counts.error_rows, "row")} · must be fixed`, `/exceptions?reportId=${report.id}&status=FAIL`],
            ["warn", "Warnings", formatNumber(hv.counts.warnings), "unusual, or read but not in a checkable form", `/exceptions?reportId=${report.id}&status=REVIEW`],
            ["muted", "Couldn’t check", formatNumber(hv.counts.couldnt_check), hv.counts.couldnt_check ? "checks that could not run; see why below" : "every check ran", null],
          ] as const).map(([tone, label, n, sub, href]) => (
            <div key={label} className="flex flex-col gap-1 rounded-md p-4" style={{ background: TONE[tone].bg, color: TONE[tone].fg }}>
              <span className="text-[13px] font-semibold">{label}</span>
              <span className="tnum text-[30px] font-semibold leading-none">{n}</span>
              <span className="text-[12.5px]">{sub}</span>
              {href ? (
                <Link href={href} className="no-print mt-1 self-start text-[12.5px] font-semibold underline underline-offset-2">Show them</Link>
              ) : mappingFixes.length ? (
                <Link href={fixMapping} className="no-print mt-1 self-start rounded px-2 py-1 text-[12.5px] font-semibold" style={{ background: "#3A3A3A", color: "#fff" }}>Fix mapping</Link>
              ) : null}
            </div>
          ))}
        </div>

        <section className="flex flex-col gap-3" aria-labelledby="top-fixes">
          <h2 id="top-fixes" className="m-0 text-[17px] font-semibold">{hv.top_fixes.length ? `Top ${hv.top_fixes.length} fix${hv.top_fixes.length === 1 ? "" : "es"}` : "Nothing to fix"}</h2>
          {hv.top_fixes.length > 0 && <p className="m-0 text-[13px]" style={{ color: PAPER.muted }}>Ranked by severity and the money on the affected rows.</p>}
          <ol className="m-0 flex list-none flex-col p-0">
            {hv.top_fixes.map((r, i) => {
              const t = TONE[r.outcome === "FAIL" ? "err" : "warn"];
              const ex = r.examples[0];
              return (
                <li key={r.rule} className="grid grid-cols-[28px_minmax(0,1fr)] gap-x-3 py-3.5" style={{ boxShadow: `0 1px 0 ${PAPER.line}` }}>
                  <span className="tnum text-[15px] font-semibold" style={{ color: PAPER.faint }}>{i + 1}</span>
                  <div className="flex min-w-0 flex-col gap-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="rounded px-1.5 py-0.5 text-[11.5px] font-semibold" style={{ background: t.bg, color: t.fg }}>{t.label} · {severityLabel(r.severity)}</span>
                      <span className="text-[14.5px] font-semibold">{r.label}</span>
                      <span className="tnum text-[13px]" style={{ color: PAPER.muted }}>{plural(r.findings, "finding")} on {plural(r.rows, "row")}</span>
                      <span className="rounded px-1.5 py-0.5 text-[11.5px] font-medium" style={{ boxShadow: `inset 0 0 0 1px ${PAPER.line}`, color: PAPER.muted }}>{r.owner === "sender" ? "Sender fixes" : "We fix"}</span>
                    </div>
                    {ex && <span className="text-[13.5px]"><b className="tnum font-semibold">{ex.where}</b>{ex.claim_ref ? ` (${ex.claim_ref})` : ""}: {ex.sentence}</span>}
                    {r.money_at_risk.length > 0 && <span className="tnum text-[13px]" style={{ color: PAPER.muted }}>Money on these rows: {moneyList(r.money_at_risk)}</span>}
                    <span className="text-[13px]" style={{ color: PAPER.muted }}>Fix: {r.fix}</span>
                  </div>
                </li>
              );
            })}
          </ol>
        </section>

        {hv.couldnt_check.length > 0 && (
          <section className="flex flex-col gap-2" aria-labelledby="couldnt">
            <h2 id="couldnt" className="m-0 text-[17px] font-semibold">Couldn’t check</h2>
            <ul className="m-0 flex list-none flex-col p-0">
              {hv.couldnt_check.map((c) => (
                <li key={c.key} className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-2.5 text-[13.5px]" style={{ boxShadow: `0 1px 0 ${PAPER.line}` }}>
                  <span className="min-w-0 flex-1"><b className="font-semibold">{c.label}</b>{c.rows ? <span className="tnum" style={{ color: PAPER.muted }}> · {plural(c.rows, "row")}</span> : null}<br /><span style={{ color: PAPER.muted }}>{c.reason}</span></span>
                  {c.fix === "mapping" ? <Link href={fixMapping} className="no-print rounded px-2 py-1 text-[12.5px] font-semibold" style={{ background: "#3A3A3A", color: "#fff" }}>Fix mapping</Link> : <span className="text-[12.5px]" style={{ color: PAPER.muted }}>Ask the sender</span>}
                </li>
              ))}
            </ul>
          </section>
        )}

        <div className="pt-3 text-[12px]" style={{ boxShadow: `0 -1px 0 ${PAPER.line}`, color: PAPER.faint }}>
          {rec(s)}. Source values unchanged. sha256 {report.source_sha256 ? `${report.source_sha256.slice(0, 12)}…` : "—"}
        </div>
      </article>

      <div className="no-print flex w-full max-w-[1100px] flex-col gap-5">
        <div role="tablist" aria-label="Report sections" className="flex flex-wrap gap-1 rounded-[9px] p-1" style={{ background: "var(--surface)", boxShadow: "inset 0 0 0 1px var(--line)" }}>
          {([["owner", "Who must fix"], ["duplicates", "Duplicates"], ["money", "Money by currency"], ["mapping", "Mapping"], ["more", "Other checks & evidence"]] as const).map(([k, l]) => (
            <button key={k} type="button" role="tab" aria-selected={tab === k} onClick={() => setTab(k)} className="cursor-pointer rounded-[7px] px-3 py-1.5 text-[13.5px]" style={{ background: tab === k ? "var(--accentTint)" : "transparent", color: tab === k ? "var(--text)" : "var(--muted)", fontWeight: tab === k ? 500 : 400 }}>{l}</button>
          ))}
        </div>
        {tab === "owner" && <OwnerTab hv={hv} reportId={report.id} />}
        {tab === "duplicates" && <DuplicatesTab hv={hv} reportId={report.id} />}
        {tab === "money" && <MoneyTab hv={hv} />}
        {tab === "mapping" && <MappingTab report={report} s={s} />}
        {tab === "more" && (
          <>
            <Section id="checks" kicker="Checks" title="Binder, leakage and sanctions checks" sub="Each check says what it assessed and what it could not.">
              <ChecksPanel report={report} />
            </Section>
            <Lineage report={report} />
            <Outputs report={report} name={name} />
          </>
        )}
      </div>

      <SendModal open={send} onClose={() => setSend(false)} report={report} />
    </>
  );
}

function OwnerTab({ hv, reportId }: { hv: HealthView; reportId: string }) {
  const col = (owner: "sender" | "us", title: string, sub: string) => {
    const rules = hv.rules.filter((r) => r.owner === owner);
    return (
      <div className="tb-card flex flex-col gap-2 p-5">
        <span className="text-[15px] font-medium">{title}</span>
        <span className="text-[13px]" style={{ color: "var(--muted)" }}>{sub}</span>
        {rules.length === 0 && <span className="text-[13px]" style={{ color: "var(--faint)" }}>Nothing.</span>}
        <ul className="m-0 flex list-none flex-col p-0">
          {rules.map((r) => (
            <li key={r.rule} className="flex flex-col gap-1 py-3" style={{ boxShadow: "0 1px 0 var(--line)" }}>
              <span className="flex flex-wrap items-center gap-2">
                <StatusPill tone={r.outcome === "FAIL" ? "err" : "warn"}>{r.outcome === "FAIL" ? "Error" : "Warning"} · {severityLabel(r.severity)}</StatusPill>
                <span className="text-[14px] font-medium">{r.label}</span>
                <span className="tnum text-[12.5px]" style={{ color: "var(--muted)" }}>{plural(r.findings, "finding")}</span>
              </span>
              {r.examples.map((e, i) => (
                <span key={i} className="text-[13px]"><b className="tnum font-medium">{e.where}</b>: {e.sentence}</span>
              ))}
              {r.findings > r.examples.length && <Link href={`/exceptions?reportId=${reportId}&checkType=${r.check_type}`} className="text-[12.5px]" style={{ color: "var(--accentText)" }}>See all {formatNumber(r.findings)} →</Link>}
            </li>
          ))}
        </ul>
      </div>
    );
  };
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-2">
      {col("sender", "The sender must fix", "Only the sender can supply or correct these values. The query letter lists them by row.")}
      {col("us", "We can fix", "Formatting only: the corrected copy fixes these safely and logs every change. Mapping gaps are fixed on the Mapping tab.")}
    </div>
  );
}

function DuplicatesTab({ hv, reportId }: { hv: HealthView; reportId: string }) {
  const d = hv.duplicates;
  return (
    <div className="tb-card flex flex-col gap-4 p-5">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {([
          ["Exact duplicates", d.exact_pairs, "Same claim, same period, identical figures: an error."],
          ["Probable duplicates", d.probable_pairs, "Different reference, but the same loss on corroborating evidence (policy, amounts, currency). Confidence 60 or more."],
          ["Of which confidence 80+", d.probable_high_confidence, "Check these first."],
          ["Claim development", d.development_pairs, "The same claim reported again with movement: normal, never a duplicate."],
        ] as const).map(([l, v, sub]) => (
          <div key={l} className="flex flex-col gap-1">
            <span className="text-[12.5px]" style={{ color: "var(--muted)" }}>{l}</span>
            <span className="tnum text-[24px] font-medium">{v == null ? "not run" : formatNumber(v)}</span>
            <span className="text-[12px]" style={{ color: "var(--faint)" }}>{sub}</span>
          </div>
        ))}
      </div>
      {d.repeat_period_unknown > 0 && <span className="text-[13px]" style={{ color: "var(--warn)" }}>{plural(d.repeat_period_unknown, "repeat")} could be duplicates or development: no reporting period is mapped.</span>}
      <Link href={`/duplicates?reportId=${reportId}`} className="tb-btn self-start">Review pairs side by side</Link>
    </div>
  );
}

function MoneyTab({ hv }: { hv: HealthView }) {
  const totals = hv.money_by_currency;
  return (
    <div className="flex flex-col gap-2">
      <div className="tb-card overflow-x-auto">
        <table className="w-full min-w-[640px] border-collapse text-[13px]">
          <thead>
            <tr className="text-left text-[11.5px] uppercase tracking-[.06em]" style={{ color: "var(--muted)" }}>
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
                <td className="px-4 py-2.5 text-right font-medium">{formatMoney(t.incurred, t.currency)}</td>
              </tr>
            ))}
            {!totals.length && <tr><td colSpan={6} className="px-4 py-4" style={{ color: "var(--muted)" }}>No amount columns were mapped in this file.</td></tr>}
          </tbody>
        </table>
      </div>
      <span className="text-[12.5px]" style={{ color: "var(--muted)" }}>Currencies are never added together. Variants such as “€”, “Euro” and “eur” are read as EUR (each is listed as a warning so the sender can standardise). Blanks are not treated as zero.</span>
    </div>
  );
}

function MappingTab({ report, s }: { report: Report; s: ReportSummary }) {
  const fields = [...s.field_completeness].sort((a, b) => Number(a.never_mapped) - Number(b.never_mapped) || a.present / Math.max(a.denominator, 1) - b.present / Math.max(b.denominator, 1));
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-2">
        <div className="tb-card flex flex-col gap-3 p-5">
          <span className="text-[14px] font-medium">Field completeness</span>
          <ul className="m-0 flex list-none flex-col gap-2 p-0">
            {fields.map((f) => {
              const pct = f.never_mapped ? null : (100 * f.present) / Math.max(f.denominator, 1);
              return (
                <li key={f.field_code} className="grid grid-cols-[minmax(0,1fr)_minmax(80px,1.2fr)_84px] items-center gap-3 text-[12.5px]">
                  <span className="truncate" style={{ color: "var(--muted)" }}>{f.field_name}</span>
                  <span className="h-1.5 rounded-full" style={{ background: "var(--line)" }}>
                    {pct != null && <span className="block h-1.5 rounded-full" style={{ width: `${pct}%`, background: pct >= 99.5 ? "var(--ok)" : "var(--warn)" }} />}
                  </span>
                  <span className="tnum text-right" style={{ color: pct == null ? "var(--faint)" : undefined }}>{pct == null ? "Not mapped" : `${pct.toFixed(0)}%`}</span>
                </li>
              );
            })}
          </ul>
        </div>
        <div className="flex flex-col gap-4">
          <div className="tb-card flex flex-col gap-3 p-5">
            <span className="flex items-center justify-between text-[14px] font-medium">Row reconciliation <StatusPill tone={s.reconciliation.reconciles ? "ok" : "err"}>{s.reconciliation.reconciles ? "Reconciles" : "Does not reconcile"}</StatusPill></span>
            <dl className="tnum m-0 grid grid-cols-[1fr_auto] gap-y-1.5 text-[13px]">
              {([
                ["Source data rows", s.reconciliation.source_data_rows],
                ["Claim rows checked", s.reconciliation.exported_rows],
                ["Structural rows excluded", s.reconciliation.rejected_rows],
                ["Rows on unmapped sheets", s.reconciliation.unmapped_rows],
                ["Summary-sheet rows (not claims)", s.reconciliation.non_claim_summary_rows],
              ] as const).map(([l, v]) => (
                <div key={l} className="contents">
                  <dt style={{ color: "var(--muted)" }}>{l}</dt>
                  <dd className="m-0 text-right">{formatNumber(v)}</dd>
                </div>
              ))}
            </dl>
          </div>
          <ExcludedRows reportId={report.id} />
        </div>
      </div>
      <Sheets reportId={report.id} s={s} />
    </div>
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
