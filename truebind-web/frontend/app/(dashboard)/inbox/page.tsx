"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { MagnifyingGlass, Tray, UploadSimple } from "@phosphor-icons/react";
import { api, IN_PROGRESS } from "@/lib/api";
import type { Report } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { EmptyState, ErrorState, LoadingState, PageHeader } from "@/components/nocturne/ui";
import { ReportTable } from "@/components/nocturne/report-list";

const FILTERS = [
  ["all", "All"],
  ["active", "Processing"],
  ["review", "Needs mapping review"],
  ["complete", "Complete"],
  ["failed", "Failed"],
] as const;

function matches(r: Report, f: string) {
  return f === "all" || (f === "active" && IN_PROGRESS.has(r.status)) || (f === "review" && r.status === "WAITING_FOR_REVIEW") || (f === "complete" && r.status === "COMPLETE") || (f === "failed" && r.status === "FAILED");
}

export default function InboxPage() {
  const { data, error, loading, reload } = useApi(() => api.listReports(), [], 10_000);
  const channels = useApi(() => api.channels());
  const [filter, setFilter] = useState<string>("all");
  const [q, setQ] = useState("");
  const rows = useMemo(
    () => (data ?? []).filter((r) => matches(r, filter) && (!q || `${r.file_name} ${r.sender ?? ""} ${r.programme ?? ""}`.toLowerCase().includes(q.toLowerCase()))),
    [data, filter, q],
  );
  const live = (channels.data?.inbound ?? []).filter((c) => c.status === "active");

  return (
    <div className="flex max-w-[1440px] flex-col gap-6 px-4 pb-12 pt-8 sm:px-9">
      <PageHeader
        kicker="Operate"
        title="Inbox"
        sub="Every bordereau TrueBind has received, where it came from and where it is in processing."
        actions={
          <Link href="/upload" className="tb-btn tb-btn-primary">
            <UploadSimple />
            New intake
          </Link>
        }
      />
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex min-w-[240px] flex-1 items-center gap-2 rounded-lg px-3" style={{ boxShadow: "inset 0 0 0 1px var(--line2)", background: "var(--surface)" }}>
          <MagnifyingGlass style={{ color: "var(--faint)" }} />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search file, sender or programme" aria-label="Search inbox" className="h-[38px] flex-1 bg-transparent text-[14px] outline-none" />
        </div>
        <div className="flex flex-wrap gap-0.5 rounded-[9px] p-[3px]" style={{ boxShadow: "inset 0 0 0 1px var(--line2)" }} role="tablist" aria-label="Filter by status">
          {FILTERS.map(([k, l]) => (
            <button key={k} type="button" role="tab" aria-selected={filter === k} onClick={() => setFilter(k)} className="flex cursor-pointer items-center gap-1.5 rounded-[7px] px-3 py-1.5 text-[13px]" style={{ background: filter === k ? "var(--accentTint)" : "transparent", color: filter === k ? "var(--text)" : "var(--muted)" }}>
              {l}
              <span className="tnum text-[11.5px]" style={{ color: "var(--faint)" }}>{(data ?? []).filter((r) => matches(r, k)).length}</span>
            </button>
          ))}
        </div>
      </div>
      <span className="-mt-3 text-[12.5px]" style={{ color: "var(--faint)" }}>
        Receiving via {live.map((c) => c.name).join(", ") || "web upload"} ·{" "}
        <Link href="/automations" className="underline" style={{ color: "var(--accentText)" }}>channels</Link> · refreshes automatically
      </span>
      <div className="tb-card overflow-hidden">
        {loading && !data ? (
          <div className="p-5"><LoadingState label="Loading inbox" rows={6} /></div>
        ) : error && !data ? (
          <div className="p-5"><ErrorState title="The inbox could not be loaded" message={error} onRetry={reload} /></div>
        ) : (data ?? []).length === 0 ? (
          <EmptyState icon={<Tray />} title="Nothing received yet" body="Files you upload, or that arrive through a connected channel, appear here." action={<Link href="/upload" className="tb-btn tb-btn-primary">Upload a bordereau</Link>} />
        ) : rows.length === 0 ? (
          <EmptyState icon={<MagnifyingGlass />} title="No files match" body="Try a different search or status filter." />
        ) : (
          <ReportTable reports={rows} detailed />
        )}
      </div>
    </div>
  );
}
