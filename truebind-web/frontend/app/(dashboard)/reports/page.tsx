"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { FileText, MagnifyingGlass, Plus } from "@phosphor-icons/react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { formatNumber } from "@/lib/formatters";
import { EmptyState, ErrorState, LoadingState, PageHeader } from "@/components/nocturne/ui";
import { ReportTable } from "@/components/nocturne/report-list";

export default function ReportsPage() {
  const { data, error, loading, reload } = useApi(() => api.listReports(), [], 15_000);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("all");
  const complete = (data ?? []).filter((r) => r.status === "COMPLETE");
  const list = useMemo(
    () =>
      (data ?? []).filter(
        (r) => (status === "all" || (status === "complete" ? r.status === "COMPLETE" : r.status !== "COMPLETE")) && `${r.file_name} ${r.sender ?? ""} ${r.programme ?? ""}`.toLowerCase().includes(q.toLowerCase()),
      ),
    [data, q, status],
  );
  const rows = complete.reduce((a, r) => a + r.rows_processed, 0);
  const scored = complete.filter((r) => r.score != null);
  const avg = scored.length ? Math.round(scored.reduce((a, r) => a + (r.score ?? 0), 0) / scored.length) : null;

  return (
    <div className="flex max-w-[1440px] flex-col gap-6 px-4 pb-12 pt-8 sm:px-9">
      <PageHeader
        kicker="Investigate"
        title="Health Check reports"
        sub="One report per processed bordereau: what was checked, flagged, unmapped and not assessed, with the evidence."
        actions={
          <Link href="/upload" className="tb-btn tb-btn-primary">
            <Plus />
            New Health Check
          </Link>
        }
      />
      {data && data.length > 0 && (
        <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(170px,1fr))", boxShadow: "0 -1px 0 var(--line), 0 1px 0 var(--line)" }}>
          {[
            ["Completed reports", formatNumber(complete.length)],
            ["Claim rows assessed", formatNumber(rows)],
            ["Average health score", avg == null ? "—" : `${avg}/100`],
            ["Not yet complete", formatNumber((data?.length ?? 0) - complete.length)],
          ].map(([l, v]) => (
            <div key={l} className="flex flex-col gap-[5px] py-[18px] pr-5">
              <span className="text-[12.5px]" style={{ color: "var(--muted)" }}>{l}</span>
              <span className="tnum text-[26px] font-medium tracking-[-0.02em]">{v}</span>
            </div>
          ))}
        </div>
      )}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex min-w-[240px] flex-1 items-center gap-2 rounded-lg px-3" style={{ boxShadow: "inset 0 0 0 1px var(--line2)", background: "var(--surface)" }}>
          <MagnifyingGlass style={{ color: "var(--faint)" }} />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by file, sender or programme" aria-label="Search reports" className="h-[38px] flex-1 bg-transparent text-[14px] outline-none" />
        </div>
        <div className="flex flex-wrap gap-0.5 rounded-[9px] p-[3px]" style={{ boxShadow: "inset 0 0 0 1px var(--line2)" }} role="tablist">
          {[
            ["all", "All"],
            ["complete", "Complete"],
            ["pending", "In progress or failed"],
          ].map(([k, l]) => (
            <button key={k} type="button" role="tab" aria-selected={status === k} onClick={() => setStatus(k)} className="cursor-pointer rounded-[7px] px-3 py-1.5 text-[13px]" style={{ background: status === k ? "var(--accentTint)" : "transparent", color: status === k ? "var(--text)" : "var(--muted)" }}>
              {l}
            </button>
          ))}
        </div>
      </div>
      <div className="tb-card overflow-hidden">
        {loading && !data ? (
          <div className="p-5"><LoadingState label="Loading reports" rows={6} /></div>
        ) : error && !data ? (
          <div className="p-5"><ErrorState title="Reports could not be loaded" message={error} onRetry={reload} /></div>
        ) : (data ?? []).length === 0 ? (
          <EmptyState icon={<FileText />} title="No reports yet" body="Upload a bordereau and TrueBind produces a Health Check report for it." action={<Link href="/upload" className="tb-btn tb-btn-primary">Upload a bordereau</Link>} />
        ) : list.length === 0 ? (
          <EmptyState icon={<MagnifyingGlass />} title="No reports match" body="Try a different search or filter." />
        ) : (
          <ReportTable reports={list} detailed />
        )}
      </div>
    </div>
  );
}
