"use client";

import Link from "next/link";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { formatDuration, formatNumber, timeAgo } from "@/lib/formatters";
import { ButtonLink } from "@/components/ui/Button";
import { BarList, EmptyState, ErrorState, Panel, PageHeader, Pill, Sparkbars, StatTile, ds, severityTone } from "@/components/ds";
import { PageSkeleton } from "@/components/layout/ShellSkeleton";
import { ActivityFeed } from "@/components/ops/ActivityFeed";
import { Recommendations } from "@/components/ops/Recommendations";
import { ReportTable } from "@/components/ops/ReportTable";
import styles from "@/components/ops/ops.module.css";

export default function OverviewPage() {
  const { data: o, error, loading, reload } = useApi(() => api.overview(), [], 20_000);
  if (loading && !o) return <PageSkeleton label="Loading overview" />;
  if (error && !o) return <ErrorState title="The overview could not be loaded" message={error} onRetry={reload} />;
  if (!o) return null;

  const f = o.findings;
  const crit = f.open_by_severity?.CRITICAL ?? 0;
  const high = f.open_by_severity?.HIGH ?? 0;
  const dupes = (f.exact_duplicates ?? 0) + (f.probable_duplicates ?? 0);
  const empty = o.reports.total === 0;

  return (
    <>
      <PageHeader eyebrow="Command centre" title="Overview"
        description="The state of your bordereaux operation: what has arrived, what needs a decision, and what TrueBind found."
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
            <StatTile icon="inbox" label="Files received (7 days)" value={formatNumber(o.received.last_7d)}
              hint={`${o.received.last_24h} in the last 24 h · ${o.reports.total} total`} tone="info" href="/inbox" />
            <StatTile icon="todo" label="Awaiting mapping review" value={formatNumber(o.reports.awaiting_review)}
              hint={o.reports.in_flight ? `${o.reports.in_flight} processing now` : "Nothing processing"} tone={o.reports.awaiting_review ? "warn" : "good"} href="/todo" />
            <StatTile icon="exceptions" label="Critical & high findings" value={formatNumber(crit + high)}
              hint={`${formatNumber(crit)} critical · ${formatNumber(high)} high`} tone={crit ? "bad" : high ? "warn" : "good"} href="/exceptions" />
            <StatTile icon="duplicates" label="Duplicate candidates" value={formatNumber(dupes)}
              hint={`${f.exact_duplicates ?? 0} exact · ${f.development_pairs ?? 0} development (not duplicates)`} tone={f.exact_duplicates ? "warn" : "good"} href="/duplicates" />
          </div>

          <div className={`${ds.grid} ${ds.split}`}>
            <Panel title="Intake, last 14 days" icon="activity" subtitle={`${formatNumber(o.trend.reduce((a, d) => a + d.rows, 0))} rows processed in this window`}>
              <Sparkbars title="Files received per day, last 14 days" values={o.trend.map((d) => d.reports)} labels={o.trend.map((d) => d.date)} />
              <div className={styles.row} style={{ justifyContent: "space-between", marginTop: 6 }}>
                <span className={styles.sub}>{o.trend[0]?.date}</span><span className={styles.sub}>today</span>
              </div>
            </Panel>
            <Panel title="Processing health" icon="server"
              actions={o.processing.worker_available ? <Pill tone="live" pulse>Online</Pill> : <Pill tone="bad">Unavailable</Pill>}>
              <div className={styles.healthGrid}>
                <div><div className={styles.healthLabel}>Workers online</div><div className={styles.healthValue}>{o.processing.workers_alive}</div></div>
                <div><div className={styles.healthLabel}>Jobs, last 24 h</div><div className={styles.healthValue}>{o.processing.jobs_24h}</div></div>
                <div><div className={styles.healthLabel}>Failed, last 24 h</div><div className={styles.healthValue}>{o.processing.failed_24h}</div></div>
                <div><div className={styles.healthLabel}>Median job time</div><div className={styles.healthValue}>{formatDuration(o.processing.median_job_s)}</div></div>
              </div>
              {!o.processing.worker_available && <p className={styles.sub} style={{ marginTop: 12 }}>No processing worker has checked in recently. Uploads will wait until one is running.</p>}
            </Panel>
          </div>

          <div className={`${ds.grid} ${ds.split}`}>
            <Panel title="Recommended next actions" icon="sparkles" subtitle="Derived only from findings in your latest reports; each shows its evidence.">
              <Recommendations items={o.recommendations} showFile />
            </Panel>
            <Panel title="What TrueBind found" icon="layers" subtitle="Across completed reports">
              <BarList items={[
                { label: "Rows missing required data", value: f.missing_mandatory_rows ?? 0, tone: "bad" },
                { label: "Arithmetic mismatches", value: f.arithmetic_mismatches ?? 0, tone: "warn" },
                { label: "Rows not evaluable", value: f.arithmetic_not_evaluable ?? 0, tone: "violet" },
                { label: "Exact duplicates", value: f.exact_duplicates ?? 0, tone: "warn" },
                { label: "Probable duplicates", value: f.probable_duplicates ?? 0, tone: "neutral" },
                { label: "Unmapped source columns", value: f.unmapped_columns ?? 0, tone: "neutral" },
              ]} />
            </Panel>
          </div>

          <div className={`${ds.grid} ${ds.split}`}>
            <Panel title="Latest files" icon="inbox" flush actions={<Link href="/inbox" className={styles.sub}>Open inbox →</Link>}>
              <ReportTable reports={o.latest_reports} />
            </Panel>
            <div className={ds.stack}>
              <Panel title="Unread alerts" icon="bell" actions={<Link href="/alerts" className={styles.sub}>All alerts →</Link>}>
                {o.alerts.latest.length ? o.alerts.latest.map((a) => (
                  <div key={a.id} className={styles.alertItem}>
                    <Pill tone={severityTone(a.severity)} dot>{a.severity.toLowerCase()}</Pill>
                    <div><p className={styles.alertMsg}>{a.message}</p><span className={styles.sub}>{timeAgo(a.created_at)}</span></div>
                  </div>
                )) : <p className={styles.muted}>You are up to date.</p>}
              </Panel>
              <Panel title="Recent activity" icon="audit" actions={<Link href="/audit" className={styles.sub}>Audit trail →</Link>}>
                <ActivityFeed entries={o.activity.slice(0, 8)} compact />
              </Panel>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
