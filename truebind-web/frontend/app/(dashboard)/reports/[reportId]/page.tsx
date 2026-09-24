"use client";

import Link from "next/link";
import { use, useEffect, useRef, useState } from "react";
import { api, ApiError, IN_PROGRESS } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import type { Report, ReportSummary } from "@/lib/types";
import { formatBytes, formatDateTime, formatDuration, formatMoney, formatNumber, timeAgo } from "@/lib/formatters";
import { Button, ButtonLink } from "@/components/ui/Button";
import { BarList, Breadcrumbs, EmptyState, ErrorState, HealthRing, KeyValue, MetricCard, Panel, PageHeader, Pill, SectionHeading, StatusPill, Timeline, ds } from "@/components/ds";
import { describeAudit } from "@/lib/audit";
import { PageSkeleton } from "@/components/layout/ShellSkeleton";
import { useShell } from "@/components/layout/ShellContext";
import { ProcessingView } from "@/components/intake/ProcessingView";
import { Recommendations } from "@/components/ops/Recommendations";
import { ExcludedRowsPanel } from "@/components/report/ExcludedRowsPanel";
import styles from "./report.module.css";

const RULE_LABEL: Record<string, string> = {
  missing_mandatory_field: "Missing required field", arithmetic_mismatch: "Arithmetic mismatch", date_order: "Dates out of order",
  date_in_future: "Date in the future", invalid_currency: "Invalid currency", currency_inconsistency: "Currency inconsistent",
  invalid_status: "Unrecognised status", schema_violation: "Unreadable value",
};

/** A factual sentence built only from computed numbers. */
function executiveSummary(r: Report, s: ReportSummary): string {
  const parts = [`${formatNumber(s.total_claims ?? r.rows_processed)} claim rows across ${s.sheets_processed} of ${s.sheets_total} sheets were assessed`];
  parts.push(s.reconciliation.reconciles ? "and every source row is accounted for" : "but the row counts do NOT reconcile — review the reconciliation below");
  const issues = [];
  if (s.missing_mandatory_rows) issues.push(`${formatNumber(s.missing_mandatory_rows)} missing required data`);
  if (s.arithmetic_mismatches) issues.push(`${formatNumber(s.arithmetic_mismatches)} that do not reconcile to total incurred`);
  if (s.exact_duplicates) issues.push(`${formatNumber(s.exact_duplicates)} exact resubmission(s)`);
  const tail = issues.length ? ` TrueBind found ${issues.join(", ")}.` : " No blocking data issues were found.";
  const dev = s.development_pairs ? ` ${s.development_pairs} claim(s) show development from a previous period and are not treated as duplicates.` : "";
  return `${parts.join(" ")}.${tail}${dev}`;
}

export default function ReportWorkspace({ params }: { params: Promise<{ reportId: string }> }) {
  const { reportId } = use(params);
  const shell = useShell();
  // Poll fast only while a job is running for this report; stop once it settles.
  const rep = useApi(() => api.getReport(reportId), [reportId], (r) => (r && IN_PROGRESS.has(r.status) ? 800 : undefined));
  const report = rep.data;
  const settledRef = useRef<string | null>(null);
  useEffect(() => {
    // When a job settles while watching, refresh the chrome's live status at once.
    if (report && !IN_PROGRESS.has(report.status) && settledRef.current !== report.status) {
      if (settledRef.current !== null) shell.refresh();
      settledRef.current = report.status;
    }
  }, [report, shell]);
  const complete = report?.status === "COMPLETE";
  const summary = useApi(() => (complete ? api.getReportSummary(reportId) : Promise.resolve(null)), [reportId, complete]);

  if (rep.loading && !rep.data) return <PageSkeleton label="Loading report" />;
  if (rep.error && !rep.data) return <ErrorState title="This report could not be loaded" message={rep.error} onRetry={rep.reload} />;
  if (!report) return null;

  const header = (
    <PageHeader eyebrow="Report" breadcrumbs={<Breadcrumbs items={[{ label: "Reports", href: "/reports" }, { label: report.file_name }]} />} title={report.file_name}
      description={<>{report.sender ? `${report.sender} · ` : ""}{report.programme ? `${report.programme} · ` : ""}received {timeAgo(report.created_at)} · {formatBytes(report.file_size_bytes)}</>}
      actions={<>
        <StatusPill status={report.status} />
        {complete && <ButtonLink href={`/exceptions?reportId=${reportId}`} variant="secondary">Exceptions</ButtonLink>}
        {complete && <ButtonLink href={`/duplicates?reportId=${reportId}`} variant="secondary">Duplicates</ButtonLink>}
        {complete && <Button variant="primary" onClick={() => window.open(api.exportClaimsUrl(reportId), "_blank")}>Export claims</Button>}
      </>} />
  );

  if (IN_PROGRESS.has(report.status) || report.status === "FAILED" || report.status === "CANCELLED") {
    return (<>{header}<ProcessingView report={report} system={shell.system}
      onCancel={IN_PROGRESS.has(report.status) ? () => api.cancelReport(reportId).then(() => rep.reload()) : undefined}
      onRetry={report.status === "FAILED" ? () => api.retryReport(reportId).then(() => rep.reload()).catch(() => rep.reload()) : shell.refresh} /></>);
  }
  if (report.status === "WAITING_FOR_REVIEW") {
    return (<>{header}<Panel><EmptyState icon="layers" title="Mapping needs your review"
      body="The workbook has been read. Confirm each sheet's column mapping and TrueBind will produce the health report."
      action={<ButtonLink href={`/upload?reportId=${reportId}`} variant="primary">Review mapping</ButtonLink>} /></Panel></>);
  }
  if (!complete) return <>{header}<Panel><p style={{ margin: 0 }}>This report is {report.status.toLowerCase()}.</p></Panel></>;

  const s = summary.data;
  return (
    <>
      {header}
      {!s ? (summary.error ? <ErrorState message={summary.error} onRetry={summary.reload} /> : <PageSkeleton label="Loading summary" />)
        : <ReportBody report={report} s={s} />}
    </>
  );
}

const SECTIONS = [
  ["financial", "Financial"], ["claims", "Claims"], ["quality", "Data quality"], ["exceptions", "Exceptions"],
  ["duplicates", "Duplicates"], ["mapping", "Mapping"], ["period", "Reporting period"], ["lineage", "Lineage"],
  ["history", "Processing history"], ["exports", "Exports"],
] as const;

function ReportBody({ report, s }: { report: Report; s: ReportSummary }) {
  // Old deep links (?tab=sheets|history|outputs) land on the matching section.
  useEffect(() => {
    const tab = new URLSearchParams(window.location.search).get("tab");
    const id = tab === "sheets" ? "mapping" : tab === "history" ? "lineage" : tab === "outputs" ? "exports" : null;
    if (id) document.getElementById(id)?.scrollIntoView({ block: "start" });
  }, []);
  return (
    <div className={ds.stack}>
      <HealthHero report={report} s={s} />
      <nav className={styles.sectionNav} aria-label="Report sections">
        {SECTIONS.map(([id, label]) => <a key={id} href={`#${id}`}>{label}</a>)}
      </nav>
      <OverviewTab report={report} s={s} />
      <section><SectionHeading id="mapping" eyebrow="Mapping" title="Sheets and column mapping"
        description="How each sheet was understood. Change the mapping and reprocess at any time; every change is audited." />
        <SheetsTab reportId={report.id} s={s} /></section>
      <HistoryTab report={report} />
      <section><SectionHeading id="exports" eyebrow="Exports" title="Outputs and deliveries"
        description="Every export is generated from the stored results and recorded in the audit trail." />
        <OutputsTab reportId={report.id} /></section>
    </div>
  );
}

function HealthHero({ report, s }: { report: Report; s: ReportSummary }) {
  const rec = s.reconciliation;
  const open = (s.missing_mandatory_rows ?? 0) + (s.arithmetic_mismatches ?? 0);
  return (
    <section className={styles.hero} aria-label="Report health">
      <div className={styles.heroScore}>
        <HealthRing score={s.composite_score ?? report.score ?? 0} label="Composite health score" />
        <div>
          <p className={styles.heroEyebrow}>Health</p>
          <p className={styles.heroGrade}>Grade {report.grade ?? s.grade ?? "—"}<span> / 5</span></p>
          <p className={styles.heroLabel}>{s.grade_label ?? ""}{s.score_reliable === false ? " · provisional" : ""}</p>
        </div>
      </div>
      <div className={styles.heroText}>
        <p className={styles.lead}>{executiveSummary(report, s)}</p>
        <div className={styles.heroFacts}>
          <Pill tone={rec.reconciles ? "good" : "bad"}>{rec.reconciles ? "Every source row reconciles" : "Rows do not reconcile"}</Pill>
          <Pill tone={open ? "warn" : "good"}>{open ? `${formatNumber(open)} row finding(s) open` : "No row findings"}</Pill>
          {s.exact_duplicates > 0 && <Pill tone="warn">{formatNumber(s.exact_duplicates)} exact resubmission(s)</Pill>}
          {(s.development_pairs ?? 0) > 0 && <Pill tone="info">{formatNumber(s.development_pairs)} development (not duplicates)</Pill>}
        </div>
        {s.score_reliable === false && <p className={styles.caveat}>The grade is provisional: at least one sheet was only partly understood.</p>}
      </div>
    </section>
  );
}

function OverviewTab({ report, s }: { report: Report; s: ReportSummary }) {
  const excluded = useApi(() => api.listExcludedRows(report.id), [report.id]);
  const rec = s.reconciliation;
  const rules = Object.entries(s.exception_counts_by_rule ?? {}).sort((a, b) => b[1] - a[1]);
  const completeness = [...s.field_completeness].sort((a, b) => (a.present / Math.max(a.denominator, 1)) - (b.present / Math.max(b.denominator, 1)));
  const statuses = Object.entries(s.claim_status_counts ?? {});
  const periods = Object.entries(s.reporting_periods ?? {}).sort((a, b) => a[0].localeCompare(b[0]));
  const totals = s.totals_by_currency ?? [];
  return (
    <>
      <section>
        <SectionHeading id="financial" eyebrow="Financial" title="Money by currency"
          description="Sums of the values reported in the file. Currencies are never added together; blanks are not treated as zero." />
        <div className={ds.stack}>
          {totals.length > 0 && (
            <div className={`${ds.grid} ${totals.length > 1 ? ds.cols2 : ds.cols3}`}>
              {totals.slice(0, 3).map((t) => (
                <MetricCard key={t.currency} icon="pound" tone="brand" label={`Total incurred · ${t.currency === "UNKNOWN" ? "currency not stated" : t.currency}`}
                  value={formatMoney(t.incurred, t.currency)} caption={`${formatNumber(t.incurred_rows ?? t.rows)} of ${formatNumber(t.rows)} rows report a value`} />
              ))}
            </div>
          )}
          <Panel flush>
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead><tr><th scope="col">Currency</th><th scope="col" className={styles.num}>Rows</th><th scope="col" className={styles.num}>Paid to date</th>
                  <th scope="col" className={styles.num}>Paid expenses / ALAE</th><th scope="col" className={styles.num}>Reserve</th><th scope="col" className={styles.num}>Total incurred</th></tr></thead>
                <tbody>
                  {totals.map((t) => (
                    <tr key={t.currency}>
                      <td><strong>{t.currency === "UNKNOWN" ? "Not stated" : t.currency}</strong></td>
                      <td className={styles.num}>{formatNumber(t.rows)}</td>
                      <td className={styles.num}>{formatMoney(t.paid_to_date, t.currency)}</td>
                      <td className={styles.num}>{t.fees_rows ? formatMoney(t.fees_paid_to_date ?? 0, t.currency) : "—"}</td>
                      <td className={styles.num}>{formatMoney(t.reserve, t.currency)}</td>
                      <td className={styles.num}>{formatMoney(t.incurred, t.currency)}</td>
                    </tr>
                  ))}
                  {!totals.length && <tr><td colSpan={6} className={styles.small}>No monetary columns were mapped in this file.</td></tr>}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>
      </section>

      <section>
        <SectionHeading id="claims" eyebrow="Claims" title="What the file contains"
          description={`${formatNumber(s.total_claims ?? report.rows_processed)} claim rows across ${s.sheets_processed} of ${s.sheets_total} sheets.`} />
        <div className={`${ds.grid} ${ds.cols2}`}>
          <Panel title="Claims by status" icon="layers" subtitle="As reported in the status column">
            {statuses.length ? <BarList items={statuses.map(([k, v]) => ({ label: k.charAt(0).toUpperCase() + k.slice(1), value: v, tone: k === "Not stated" ? "neutral" as const : undefined }))} />
              : <p className={styles.small}>No claim-status column was mapped{Object.keys(s).includes("claim_status_counts") ? "." : " (reprocess to see the breakdown)."}</p>}
          </Panel>
          <Panel title="Row reconciliation" icon="check"
            actions={rec.reconciles ? <Pill tone="good">Reconciles</Pill> : <Pill tone="bad">Does not reconcile</Pill>}>
            <KeyValue items={[
              ["Source data rows", formatNumber(rec.source_data_rows)],
              ["Claim rows exported", formatNumber(rec.exported_rows)],
              ["Structural rows excluded", formatNumber(rec.rejected_rows)],
              ["Rows on unmapped sheets", formatNumber(rec.unmapped_rows)],
              ["Summary-sheet rows (not claims)", formatNumber(rec.non_claim_summary_rows)],
              ["Duplicate rows (kept, flagged)", formatNumber(rec.duplicate_rows)],
              ["Rows requiring review", formatNumber(rec.rows_requiring_review)],
            ]} />
            <p className={styles.caveat}>Every source row is either a claim or a recorded exclusion with a reason; nothing is silently dropped.</p>
          </Panel>
        </div>
      </section>

      <section>
        <SectionHeading id="quality" eyebrow="Data quality" title="Completeness and structure" />
        <div className={ds.stack}>
          <div className={`${ds.grid} ${ds.cols2}`}>
            <Panel title="Field completeness" icon="layers" subtitle="Share of rows where each field has a value">
              <BarList max={100} format={(n) => `${n.toFixed(0)}%`} items={completeness.map((f) => ({
                label: f.never_mapped ? `${f.field_name} (not in file)` : f.field_name,
                value: f.never_mapped ? 0 : (100 * f.present) / Math.max(f.denominator, 1),
                tone: f.never_mapped ? "neutral" as const : f.present === f.denominator ? "good" as const : "warn" as const,
              }))} />
            </Panel>
            <div className={ds.stack}>
              {(s.unmapped_source_columns ?? []).length > 0 && (
                <Panel title="Unmapped source columns" icon="info" subtitle="Not validated, but kept on every row and included in the claims export.">
                  <ul className={styles.chips}>
                    {(s.unmapped_source_columns ?? []).flatMap((u) => u.columns.map((c) => (
                      <li key={`${u.sheet_name}-${c}`} className={styles.chip}><strong>{c}</strong><span>{u.sheet_name}</span></li>
                    )))}
                  </ul>
                </Panel>
              )}
              <Panel title="Rows excluded before assessment" icon="x" subtitle="Blank, title, total and repeated-header rows: recorded with their reason, never counted as claims.">
                {(excluded.data ?? []).length ? <ExcludedRowsPanel rows={excluded.data ?? []} /> : <p className={styles.small}>No rows were excluded.</p>}
              </Panel>
            </div>
          </div>
        </div>
      </section>

      <section>
        <SectionHeading id="exceptions" eyebrow="Exceptions" title="What failed a check"
          actions={<ButtonLink href={`/exceptions?reportId=${report.id}`} size="sm" variant="secondary">Open exception centre</ButtonLink>} />
        <div className={`${ds.grid} ${ds.cols2}`}>
          <Panel title="Findings by type" icon="exceptions">
            {rules.length ? <BarList items={rules.map(([k, v]) => ({ label: RULE_LABEL[k] ?? k.replace(/_/g, " "), value: v,
              tone: k === "missing_mandatory_field" ? "bad" as const : "warn" as const, href: `/exceptions?reportId=${report.id}` }))} /> : <p className={styles.small}>No failed checks.</p>}
            {s.arithmetic_not_evaluable > 0 && <p className={styles.caveat}>{formatNumber(s.arithmetic_not_evaluable)} row(s) could not be checked for arithmetic: {Object.entries(s.not_evaluable_by_reason).map(([k, v]) => `${k.replace(/_/g, " ")} (${v})`).join(", ")}.</p>}
          </Panel>
          <Panel title="Recommended next actions" icon="sparkles" subtitle="Every item cites its evidence from this report.">
            <Recommendations items={s.recommendations ?? []} reportId={report.id} />
          </Panel>
        </div>
      </section>

      <section>
        <SectionHeading id="duplicates" eyebrow="Duplicates" title="Resubmissions and development"
          actions={<ButtonLink href={`/duplicates?reportId=${report.id}`} size="sm" variant="secondary">Compare pairs</ButtonLink>} />
        <div className={`${ds.grid} ${ds.cols3}`}>
          <MetricCard icon="duplicates" label="Exact resubmissions" value={formatNumber(s.exact_duplicates)} tone={s.exact_duplicates ? "warn" : "good"}
            caption="Same reference, period and amounts" href={`/duplicates?reportId=${report.id}`} />
          <MetricCard icon="search" label="Probable duplicates" value={formatNumber(s.probable_duplicates)} tone={s.probable_duplicates ? "warn" : "good"}
            caption="Close match — needs a decision" href={`/duplicates?reportId=${report.id}`} />
          <MetricCard icon="activity" label="Development" value={formatNumber(s.development_pairs ?? 0)} tone="neutral"
            caption="Same claim, later period, moved amounts — not a duplicate" />
        </div>
      </section>

      <section>
        <SectionHeading id="period" eyebrow="Reporting period" title="Periods in this file"
          description="Rows per reporting period as stated in the file." />
        <Panel>
          {periods.length ? <BarList items={periods.map(([k, v]) => ({ label: k, value: v, tone: k === "Not stated" ? "neutral" as const : undefined }))} />
            : <p className={styles.small}>{Object.keys(s).includes("reporting_periods") ? "No reporting-period column was mapped in this file." : "Reprocess this file to see its reporting periods."}</p>}
          {(s.period_unknown_repeats ?? 0) > 0 && <p className={styles.caveat}>{formatNumber(s.period_unknown_repeats)} repeated reference(s) could not be classified because the period is missing.</p>}
        </Panel>
      </section>
    </>
  );
}

function SheetsTab({ reportId, s }: { reportId: string; s: ReportSummary }) {
  const sheets = useApi(() => api.listSheets(reportId), [reportId]);
  const byName = Object.fromEntries((sheets.data ?? []).map((x) => [x.sheet_name, x]));
  const TONE: Record<string, "good" | "warn" | "bad" | "neutral" | "info"> = { mapped: "good", partial: "warn", unmapped: "bad", empty: "neutral", error: "bad", non_claim_summary: "info" };
  return (
    <Panel title="Sheets" icon="layers" flush actions={<ButtonLink href={`/upload?reportId=${reportId}`} size="sm">Change mapping</ButtonLink>}>
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead><tr><th scope="col">Sheet</th><th scope="col">Status</th><th scope="col" className={styles.num}>Rows assessed</th><th scope="col" className={styles.num}>Excluded</th><th scope="col" className={styles.num}>Fields mapped</th><th scope="col">Notes</th></tr></thead>
          <tbody>
            {(s.sheet_audit ?? []).map((a) => {
              const sh = byName[a.sheet_name];
              return (
                <tr key={a.sheet_name}>
                  <td><strong>{a.sheet_name}</strong>{sh?.hidden && <Pill tone="neutral" dot={false}>hidden</Pill>}</td>
                  <td><Pill tone={TONE[a.status] ?? "neutral"}>{a.status.replace(/_/g, " ")}</Pill><div className={styles.small}>{a.reason}</div></td>
                  <td className={styles.num}>{formatNumber(a.rows_processed)}</td>
                  <td className={styles.num}>{formatNumber(a.rows_rejected)}</td>
                  <td className={styles.num}>{a.fields_mapped}</td>
                  <td className={styles.small}>{[...(sh?.notes ?? []), sh?.trailing_blank_rows ? `${sh.trailing_blank_rows} trailing blank rows` : ""].filter(Boolean).join(" · ") || "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function HistoryTab({ report }: { report: Report }) {
  const jobs = useApi(() => api.reportJobs(report.id), [report.id]);
  const audit = useApi(() => api.getAuditLog(report.id), [report.id]);
  return (
    <>
      <section>
        <SectionHeading id="lineage" eyebrow="Lineage" title="Where every number came from"
          description="The source file's fingerprint and every recorded step, newest first. The audit trail is hash-chained." />
        <div className={`${ds.grid} ${ds.split}`}>
          <Panel title="Recorded steps" icon="lineage">
            {audit.data ? <Timeline items={audit.data.slice(0, 12).map((e) => {
              const d = describeAudit(e);
              return { id: e.id, icon: d.icon, tone: d.tone === "info" ? "brand" : d.tone, title: d.title, body: d.detail,
                       meta: `${formatDateTime(e.created_at)} · ${e.actor} · #${e.seq ?? ""}` };
            })} /> : <PageSkeleton />}
            {(audit.data?.length ?? 0) > 12 && <p className={styles.small}><Link href={`/audit?reportId=${report.id}`}>See all {audit.data?.length} entries →</Link></p>}
          </Panel>
          <Panel title="Source file" icon="file">
            <KeyValue items={[
              ["File", report.file_name], ["Type", (report.file_kind ?? "").toUpperCase()], ["Size", formatBytes(report.file_size_bytes)],
              ["SHA-256", <span key="h" className={ds.mono} title={report.source_sha256 ?? ""}>{report.source_sha256?.slice(0, 20)}…</span>],
              ["Channel", report.source_channel === "upload" ? "Web upload" : report.source_channel],
              ["Sender", report.sender ?? "—"], ["Programme", report.programme ?? "—"],
              ["Received", formatDateTime(report.created_at)], ["Retained until", formatDateTime(report.expires_at)],
            ]} />
          </Panel>
        </div>
      </section>
      <section>
        <SectionHeading id="history" eyebrow="Processing history" title="Jobs that ran on this file" />
        <Panel>
          {(jobs.data ?? []).map((j) => {
            const m = (j.metrics ?? {}) as Record<string, unknown>;
            const st = (m.stage_timings ?? {}) as Record<string, number>;
            const dur = j.started_at && j.finished_at ? (new Date(j.finished_at).getTime() - new Date(j.started_at).getTime()) / 1000 : null;
            return (
              <div key={j.id} className={styles.job}>
                <div className={styles.jobHead}><strong>{j.kind === "INGEST" ? "Read workbook & propose mapping" : "Validate & build report"}</strong>
                  <Pill tone={j.status === "SUCCEEDED" ? "good" : j.status === "FAILED" ? "bad" : "info"}>{j.status.toLowerCase()}</Pill></div>
                <p className={styles.small}>{formatDateTime(j.created_at)} · attempt {j.attempts} · {formatDuration(dur)}{typeof m.rows === "number" ? ` · ${formatNumber(m.rows as number)} rows` : ""}{typeof m.ai_calls === "number" ? ` · ${m.ai_calls} AI calls` : ""}</p>
                {Object.keys(st).length > 0 && (
                  <div className={styles.timings}>{Object.entries(st).map(([k, v]) => <span key={k}>{k} <strong>{formatDuration(v)}</strong></span>)}</div>
                )}
                {j.error_message && <p className={styles.small}>{j.error_message}</p>}
              </div>
            );
          })}
          {jobs.data && !jobs.data.length && <p className={styles.small}>No jobs recorded.</p>}
        </Panel>
      </section>
    </>
  );
}

function OutputsTab({ reportId }: { reportId: string }) {
  const deliveries = useApi(() => api.listDeliveries(), [reportId]);
  const [recipient, setRecipient] = useState("");
  const [kind, setKind] = useState("exceptions_csv");
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const mine = (deliveries.data?.items ?? []).filter((d) => d.report_id === reportId);
  const outputs = [
    { kind: "claims_csv", title: "Claims", body: "Every claim row with its source sheet and row, unmapped columns and findings.", url: api.exportClaimsUrl(reportId) },
    { kind: "exceptions_csv", title: "Exceptions", body: "Every finding with severity, rule and the source row it concerns.", url: api.exportExceptionsUrl(reportId) },
    { kind: "audit_csv", title: "Audit trail", body: "Hash-chained history of everything that happened to this file.", url: api.exportAuditCsvUrl(reportId) },
  ];
  async function send(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const d = await api.sendDelivery(reportId, kind, recipient);
      setMsg(d.status === "DELIVERED" ? `Sent to ${d.destination}.` : d.error ?? "Not sent.");
      deliveries.reload();
    } catch (err) {
      setMsg(err instanceof ApiError ? err.message : "Could not send.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className={ds.stack}>
      <div className={`${ds.grid} ${ds.cols3}`}>
        {outputs.map((o) => (
          <Panel key={o.kind} title={o.title} icon="download">
            <p className={styles.small} style={{ marginTop: 0 }}>{o.body}</p>
            <Button variant="secondary" onClick={() => { window.open(o.url, "_blank"); setTimeout(deliveries.reload, 1200); }}>Download CSV</Button>
          </Panel>
        ))}
      </div>
      <div className={`${ds.grid} ${ds.cols2}`}>
        <Panel title="Send by e-mail" icon="mail">
          <form onSubmit={send} className={ds.toolbar}>
            <select className={ds.select} value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Output">
              {outputs.map((o) => <option key={o.kind} value={o.kind}>{o.title}</option>)}
            </select>
            <input className={ds.input} type="email" required placeholder="recipient@company.example" value={recipient} onChange={(e) => setRecipient(e.target.value)} aria-label="Recipient" />
            <Button type="submit" loading={busy}>Send</Button>
          </form>
          {msg && <p role="status" className={styles.small}>{msg}</p>}
        </Panel>
        <Panel title="Delivered outputs" icon="exports">
          {mine.length ? mine.map((d) => (
            <p key={d.id} className={styles.small}><Pill tone={d.status === "DELIVERED" ? "good" : d.status === "FAILED" ? "bad" : "neutral"}>{d.status.toLowerCase().replace("_", " ")}</Pill>{" "}
              {d.kind.replace("_csv", "")} · {d.channel}{d.destination ? ` → ${d.destination}` : ""} · {timeAgo(d.created_at)}</p>
          )) : <p className={styles.small}>Nothing delivered from this report yet.</p>}
        </Panel>
      </div>
    </div>
  );
}
