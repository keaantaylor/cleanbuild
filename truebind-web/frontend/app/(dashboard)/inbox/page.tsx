"use client";

import { useMemo, useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { ButtonLink } from "@/components/ui/Button";
import { EmptyState, ErrorState, Icon, Panel, PageHeader, Pill, SegmentedControl, ds } from "@/components/ds";
import { PageSkeleton } from "@/components/layout/ShellSkeleton";
import { ReportTable } from "@/components/ops/ReportTable";
import { IN_PROGRESS } from "@/lib/api";
import type { Report } from "@/lib/types";

const FILTERS = [
  { value: "all", label: "All" },
  { value: "active", label: "Processing" },
  { value: "review", label: "Needs review" },
  { value: "complete", label: "Complete" },
  { value: "failed", label: "Failed" },
];

function matches(r: Report, filter: string): boolean {
  return filter === "all" || (filter === "active" && IN_PROGRESS.has(r.status))
    || (filter === "review" && r.status === "WAITING_FOR_REVIEW") || (filter === "complete" && r.status === "COMPLETE")
    || (filter === "failed" && r.status === "FAILED");
}

export default function InboxPage() {
  const { data, error, loading, reload } = useApi(() => api.listReports(), [], 10_000);
  const { data: channels } = useApi(() => api.channels());
  const [filter, setFilter] = useState("all");
  const [q, setQ] = useState("");
  const rows = useMemo(() => (data ?? []).filter((r) => {
    const okF = matches(r, filter);
    const text = `${r.file_name} ${r.sender ?? ""} ${r.programme ?? ""}`.toLowerCase();
    return okF && (!q || text.includes(q.toLowerCase()));
  }), [data, filter, q]);

  if (loading && !data) return <PageSkeleton label="Loading inbox" />;
  if (error && !data) return <ErrorState title="The inbox could not be loaded" message={error} onRetry={reload} />;
  const active = (channels?.inbound ?? []).filter((c) => c.status === "active");

  return (
    <>
      <PageHeader eyebrow="Operate" title="Inbox"
        description="Every bordereau TrueBind has received, where it came from and where it is in processing."
        actions={<ButtonLink href="/upload" variant="primary">New intake</ButtonLink>} />
      <div className={ds.stack}>
        <div className={ds.toolbar}>
          <div className={ds.searchWrap}>
            <Icon name="search" />
            <input className={ds.input} placeholder="Search file, sender or programme" value={q}
                   onChange={(e) => setQ(e.target.value)} aria-label="Search inbox" />
          </div>
          <SegmentedControl label="Filter by status" value={filter} onChange={setFilter}
            options={FILTERS.map((f) => ({ value: f.value, label: f.label, count: (data ?? []).filter((r) => matches(r, f.value)).length }))} />
          <span className={ds.muted} style={{ marginLeft: "auto" }}>
            Receiving via {active.map((c) => c.name).join(", ") || "web upload"}
            {" · "}<a href="/automations">channels</a>
          </span>
        </div>
        <Panel flush>
          {(data ?? []).length === 0 ? (
            <EmptyState icon="inbox" title="Nothing received yet" body="Files you upload, or that arrive through a connected channel, appear here."
              action={<ButtonLink href="/upload" variant="primary">Upload a bordereau</ButtonLink>} />
          ) : rows.length === 0 ? (
            <EmptyState icon="search" title="No files match" body="Try a different search or status filter." />
          ) : <ReportTable reports={rows} detailed />}
        </Panel>
        <p className={ds.muted}><Pill tone="neutral" dot={false}>{rows.length}</Pill> of {(data ?? []).length} files shown · refreshes automatically</p>
      </div>
    </>
  );
}
