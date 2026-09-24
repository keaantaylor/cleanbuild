"use client";

import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { ButtonLink } from "@/components/ui/Button";
import { EmptyState, ErrorState, Panel, PageHeader, StatTile, ds } from "@/components/ds";
import { PageSkeleton } from "@/components/layout/ShellSkeleton";
import { ReportTable } from "@/components/ops/ReportTable";

export default function ReportsPage() {
  const { data, error, loading, reload } = useApi(() => api.listReports(), [], 15_000);
  if (loading && !data) return <PageSkeleton label="Loading reports" />;
  if (error && !data) return <ErrorState title="Reports could not be loaded" message={error} onRetry={reload} />;
  const reports = data ?? [];
  const complete = reports.filter((r) => r.status === "COMPLETE");
  const avg = complete.length ? complete.reduce((a, r) => a + (r.score ?? 0), 0) / complete.length : null;
  const rows = complete.reduce((a, r) => a + r.rows_processed, 0);
  return (
    <>
      <PageHeader eyebrow="Analyse" title="Reports" description="Health reports for every processed bordereau."
        actions={<ButtonLink href="/upload" variant="primary">New intake</ButtonLink>} />
      <div className={ds.stack}>
        <div className={`${ds.grid} ${ds.cols4}`}>
          <StatTile label="Completed reports" value={complete.length} tone="good" icon="reports" />
          <StatTile label="Claim rows assessed" value={rows.toLocaleString("en-GB")} tone="info" icon="layers" />
          <StatTile label="Average health score" value={avg === null ? "—" : `${avg.toFixed(0)}/100`} tone={avg !== null && avg < 55 ? "warn" : "neutral"} icon="activity" />
          <StatTile label="Not yet complete" value={reports.length - complete.length} tone="neutral" icon="clock" href="/inbox" />
        </div>
        <Panel flush>
          {reports.length === 0 ? <EmptyState icon="reports" title="No reports yet" body="Upload a bordereau to produce its first health report."
            action={<ButtonLink href="/upload" variant="primary">Upload</ButtonLink>} /> : <ReportTable reports={reports} detailed />}
        </Panel>
      </div>
    </>
  );
}
