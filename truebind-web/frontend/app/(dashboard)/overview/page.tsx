"use client";

import Link from "next/link";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { describeAudit } from "@/lib/audit";
import { formatDuration, formatNumber, timeAgo } from "@/lib/formatters";
import { stageLabel } from "@/lib/stages";
import type { WorkItem } from "@/lib/types";
import { ButtonLink } from "@/components/ui/Button";
import {
  BarList, EmptyState, ErrorState, FileCard, Icon, MetricCard, Panel, PageHeader, Pill, ProgressIndicator, Sparkbars,
  Timeline, ds, severityTone,
} from "@/components/ds";
import { PageSkeleton } from "@/components/layout/ShellSkeleton";
import { Recommendations } from "@/components/ops/Recommendations";
import { ReportTable, reportHref } from "@/components/ops/ReportTable";
import o_ from "./overview.module.css";

const PRIORITY_ICON: Record<string, "alertCircle" | "exceptions" | "info" | "clock"> = {
  CRITICAL: "alertCircle", HIGH: "exceptions", MEDIUM: "info", INFO: "clock",
};

function AttentionItem({ item }: { item: WorkItem }) {
  const body = (
    <>
      <span className={`${o_.attIcon} ${o_[`p-${item.priority}`]}`}><Icon name={PRIORITY_ICON[item.priority] ?? "info"} size={16} /></span>
      <span className={o_.attMain}>
        <span className={o_.attTitle}>{item.title}</span>
        <span className={o_.attDetail}>{item.detail}{item.file_name ? ` · ${item.file_name}` : ""}</span>
      </span>
      {item.count > 1 && <span className={o_.attCount}>{formatNumber(item.count)}</span>}
      <Icon name="chevronRight" size={16} className={o_.attGo} />
    </>
  );
  return item.href ? <Link href={item.href} className={o_.att}>{body}</Link> : <div className={o_.att}>{body}</div>;
}

export default function OverviewPage() {
  const { data: o, error, loading, reload } = useApi(() => api.overview(), [],
    (d) => (d && d.reports.in_flight > 0 ? 3_000 : 20_000));
  const { data: queue } = useApi(() => api.workQueue(), [], 20_000);
  if (loading && !o) return <PageSkeleton label="Loading overview" />;
  if (error && !o) return <ErrorState title="The overview could not be loaded" message={error} onRetry={reload} />;
  if (!o) return null;

  const f = o.findings;
  const crit = f.open_by_severity?.CRITICAL ?? 0;
  const high = f.open_by_severity?.HIGH ?? 0;
  const empty = o.reports.total === 0;
  const inFlight = o.in_flight_reports ?? o.latest_reports.filter((r) => ["UPLOADED", "QUEUED", "INGESTING", "PROCESSING"].includes(r.status));
  const attention = (queue?.items ?? []).slice(0, 5);
  const rows14 = o.trend.reduce((a, d) => a + d.rows, 0);

  const headline = empty ? "Nothing received yet."
    : attention.length ? `${formatNumber(queue?.total ?? attention.length)} item${(queue?.total ?? 0) === 1 ? "" : "s"} need${(queue?.total ?? 0) === 1 ? "s" : ""} a decision.`
    : "Everything received has been handled.";

  return (
    <>
      <PageHeader eyebrow="Command centre" title="Overview" description={headline}
        actions={<><ButtonLink href="/todo" variant="secondary">Work queue</ButtonLink><ButtonLink href="/upload" variant="primary">New intake</ButtonLink></>} />

      {empty ? (
        <Panel>
          <EmptyState icon="upload" title="No bordereaux yet"
            body="Upload a claims bordereau (.xlsx, .xlsm, .xls or .csv). TrueBind reads every sheet, proposes a column mapping, validates the data and reconciles every source row."
            action={<ButtonLink href="/upload" variant="primary">Upload your first file</ButtonLink>} />
        </Panel>
      ) : (
        <div className={ds.stack}>
          <div className={`${ds.grid} ${ds.cols4}`}>
            <MetricCard icon="inbox" label="Files received · 7 days" value={formatNumber(o.received.last_7d)} tone="brand" href="/inbox"
              caption={`${o.received.last_24h} in the last 24 h · ${o.reports.total} total`} />
            <MetricCard icon="layers" label="Rows assessed" value={formatNumber(f.claims ?? 0)} tone="neutral" href="/reports"
              caption={`across ${formatNumber(o.reports.complete)} completed report${o.reports.complete === 1 ? "" : "s"}`} />
            <MetricCard icon="exceptions" label="Critical & high findings" value={formatNumber(crit + high)} href="/exceptions"
              tone={crit ? "bad" : high ? "warn" : "good"} caption={`${formatNumber(crit)} critical · ${formatNumber(high)} high`} />
            <MetricCard icon="duplicates" label="Exact resubmissions" value={formatNumber(f.exact_duplicates ?? 0)} href="/duplicates"
              tone={f.exact_duplicates ? "warn" : "good"}
              caption={`${formatNumber(f.probable_duplicates ?? 0)} probable · ${formatNumber(f.development_pairs ?? 0)} development (not duplicates)`} />
          </div>

          <div className={o_.columns}>
            <div className={ds.stack}>
              <Panel title="Attention required" icon="alertCircle"
                subtitle="Ranked by priority from your work queue — every item links to where it is resolved."
                actions={<Link href="/todo" className={o_.link}>Work queue →</Link>}>
                {attention.length ? <div className={o_.attList}>{attention.map((it, i) => <AttentionItem key={i} item={it} />)}</div>
                  : <div className={o_.clear}><Icon name="check" size={18} /> Nothing needs a decision right now.</div>}
              </Panel>
              <Panel title="Recommended next actions" icon="sparkles" subtitle="Derived only from findings in your latest reports; each shows its evidence.">
                <Recommendations items={o.recommendations} showFile />
              </Panel>
              <Panel title="Intake · last 14 days" icon="activity" subtitle={`${formatNumber(rows14)} rows processed in this window`}>
                <Sparkbars title="Files received per day, last 14 days" values={o.trend.map((d) => d.reports)} labels={o.trend.map((d) => d.date)} />
                <div className={o_.axis}><span>{o.trend[0]?.date}</span><span>today</span></div>
              </Panel>
              <Panel title="Latest files" icon="inbox" flush actions={<Link href="/inbox" className={o_.link}>Open inbox →</Link>}>
                <ReportTable reports={o.latest_reports} />
              </Panel>
            </div>
            <div className={ds.stack}>
              <Panel title="Processing now" icon="activity"
                actions={o.processing.worker_available
                  ? <Pill tone={inFlight.length ? "info" : "live"} pulse={inFlight.length > 0}>{inFlight.length ? `${inFlight.length} in flight` : "Engine idle"}</Pill>
                  : <Pill tone="bad">Engine offline</Pill>}>
                {inFlight.length ? (
                  <ul className={o_.flight}>
                    {inFlight.map((r) => (
                      <li key={r.id} className={o_.flightItem}>
                        <FileCard name={r.file_name} href={reportHref(r)} meta={stageLabel(r.job)} />
                        <ProgressIndicator label={`${r.file_name}: ${stageLabel(r.job)}`} />
                      </li>
                    ))}
                  </ul>
                ) : (
                  <div className={o_.engineStats}>
                    <div><span>Jobs · 24 h</span><strong>{formatNumber(o.processing.jobs_24h)}</strong></div>
                    <div><span>Failed · 24 h</span><strong className={o.processing.failed_24h ? o_.bad : ""}>{formatNumber(o.processing.failed_24h)}</strong></div>
                    <div><span>Median job</span><strong>{formatDuration(o.processing.median_job_s)}</strong></div>
                    <div><span>Workers</span><strong>{o.processing.workers_alive}</strong></div>
                  </div>
                )}
                {!o.processing.worker_available && <p className={o_.warn}>No processing engine has checked in recently. Uploads wait safely until one is running.</p>}
              </Panel>
              <Panel title="Data health" icon="shield" subtitle="Open findings across completed reports">
                <BarList items={[
                  { label: "Rows missing required data", value: f.missing_mandatory_rows ?? 0, tone: "bad", href: "/exceptions?checkType=MANDATORY_FIELD" },
                  { label: "Arithmetic mismatches", value: f.arithmetic_mismatches ?? 0, tone: "warn", href: "/exceptions?checkType=ARITHMETIC" },
                  { label: "Rows not evaluable", value: f.arithmetic_not_evaluable ?? 0, tone: "violet" },
                  { label: "Exact duplicates", value: f.exact_duplicates ?? 0, tone: "warn", href: "/duplicates" },
                  { label: "Probable duplicates", value: f.probable_duplicates ?? 0, tone: "neutral", href: "/duplicates" },
                  { label: "Unmapped source columns", value: f.unmapped_columns ?? 0, tone: "neutral" },
                ]} />
              </Panel>
              <Panel title="Unread alerts" icon="bell" actions={<Link href="/alerts" className={o_.link}>All alerts →</Link>}>
                {o.alerts.latest.length ? (
                  <ul className={o_.alerts}>
                    {o.alerts.latest.slice(0, 4).map((a) => (
                      <li key={a.id}><Pill tone={severityTone(a.severity)}>{a.severity.toLowerCase()}</Pill>
                        <span className={o_.alertMsg} title={a.message}>{a.message}</span>
                        <span className={o_.alertTime}>{timeAgo(a.created_at)}</span></li>
                    ))}
                  </ul>
                ) : <p className={o_.quiet}>You are up to date.</p>}
              </Panel>
              <Panel title="Recent activity" icon="audit" actions={<Link href="/audit" className={o_.link}>Audit trail →</Link>}>
                <Timeline items={o.activity.slice(0, 7).map((e) => {
                  const d = describeAudit(e);
                  return { id: e.id, icon: d.icon, tone: d.tone === "info" ? "brand" : d.tone, title: d.title,
                           meta: `${timeAgo(e.created_at)} · ${e.actor}` };
                })} />
              </Panel>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
