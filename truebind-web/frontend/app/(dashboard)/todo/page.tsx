"use client";

import Link from "next/link";
import { useState } from "react";
import { CheckCircle, CheckSquare, Clock, Info, Warning, WarningCircle } from "@phosphor-icons/react";
import { api, ApiError } from "@/lib/api";
import type { Obligation } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { useUi } from "@/lib/ui";
import { formatDate, formatNumber } from "@/lib/formatters";
import { EmptyState, ErrorState, LoadingState, PageHeader, StatTile, StatusPill } from "@/components/nocturne/ui";
import { SEV } from "@/components/nocturne/status";

export default function WorkQueuePage() {
  const { toast } = useUi();
  const q = useApi(() => api.workQueue(), [], 15_000);
  const obligations = useApi(() => api.listObligations({}), []);
  const [sev, setSev] = useState<string>("all");
  const items = q.data?.items ?? [];
  const by = (p: string) => items.filter((i) => i.priority === p).length;
  const open = (obligations.data ?? []).filter((o) => o.status !== "RESOLVED");
  const shown = sev === "all" || sev === "followups" ? items : items.filter((i) => i.priority === sev);

  const update = async (o: Obligation, status: string) => {
    try {
      await api.updateObligation(o.id, { status });
      obligations.reload();
      q.reload();
      toast(status === "RESOLVED" ? "Follow-up resolved · recorded in the audit trail" : "Follow-up updated", "ok");
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "The follow-up could not be updated.", "err");
    }
  };

  return (
    <div className="flex max-w-[1440px] flex-col gap-6 px-4 pb-12 pt-8 sm:px-6">
      <PageHeader kicker="Operate" title="Work queue" sub="Everything waiting on a person, most urgent first. Items leave the queue when the underlying work is done." />
      {q.loading && !q.data ? (
        <LoadingState label="Loading work queue" rows={6} />
      ) : q.error && !q.data ? (
        <ErrorState title="The work queue could not be loaded" message={q.error} onRetry={q.reload} />
      ) : (
        <>
          <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(200px,1fr))" }}>
            <StatTile label="Critical" value={by("CRITICAL")} color="var(--err)" icon={<WarningCircle size={15} />} active={sev === "CRITICAL"} onClick={() => setSev(sev === "CRITICAL" ? "all" : "CRITICAL")} note="Blocks a clean submission" />
            <StatTile label="High" value={by("HIGH")} color="var(--warn)" icon={<Warning size={15} />} active={sev === "HIGH"} onClick={() => setSev(sev === "HIGH" ? "all" : "HIGH")} note="Resolve before sending" />
            <StatTile label="Medium" value={by("MEDIUM")} color="var(--med)" icon={<Info size={15} />} active={sev === "MEDIUM"} onClick={() => setSev(sev === "MEDIUM" ? "all" : "MEDIUM")} note="Review this week" />
            <StatTile label="Open follow-ups" value={open.length} color="var(--line2)" icon={<CheckSquare size={15} />} active={sev === "followups"} onClick={() => setSev(sev === "followups" ? "all" : "followups")} note="Created from findings" />
          </div>

          {sev !== "followups" && (
            <div className="tb-card overflow-hidden">
              {shown.length === 0 ? (
                <EmptyState icon={<CheckCircle />} title="Nothing waiting on you" body="New files, mapping reviews, critical findings and duplicate candidates will appear here." action={<Link href="/upload" className="tb-btn">Upload a bordereau</Link>} />
              ) : (
                shown.map((i, idx) => (
                  <div key={idx} className="grid grid-cols-[10px_minmax(0,1fr)_auto] items-center gap-4 px-5 py-3.5 transition-colors hover:bg-[var(--accentTint)]" style={{ boxShadow: "0 1px 0 var(--line)" }}>
                    <span className="h-2 w-2 rounded-full" style={{ background: SEV[i.priority]?.c ?? "var(--muted)" }} />
                    <span className="flex min-w-0 flex-col gap-0.5">
                      <span className="truncate text-[13.5px] font-medium">
                        {i.title}
                        {i.count > 1 && <span className="tnum ml-2 text-[12px]" style={{ color: "var(--faint)" }}>{formatNumber(i.count)}</span>}
                      </span>
                      <span className="truncate text-[12px]" style={{ color: "var(--faint)" }}>{i.detail}{i.file_name ? ` · ${i.file_name}` : ""}</span>
                    </span>
                    <span className="flex items-center gap-2">
                      <StatusPill tone={SEV[i.priority]?.tone ?? "muted"}>{SEV[i.priority]?.label ?? i.priority}</StatusPill>
                      {i.href && <Link href={i.href} className="tb-btn tb-btn-primary !px-2.5 !py-1.5 text-[12.5px]">Open</Link>}
                    </span>
                  </div>
                ))
              )}
            </div>
          )}

          <div className="flex flex-col gap-3">
            <div className="flex items-baseline justify-between">
              <span className="text-[15px] font-medium">Assigned follow-ups</span>
              <span className="text-[12px]" style={{ color: "var(--faint)" }}>Created from findings on the Exceptions page</span>
            </div>
            <div className="tb-card overflow-hidden">
              {obligations.error && !obligations.data ? (
                <div className="p-4"><ErrorState title="Follow-ups could not be loaded" message={obligations.error} onRetry={obligations.reload} /></div>
              ) : !obligations.data ? (
                <div className="p-4"><LoadingState label="Loading follow-ups" rows={3} /></div>
              ) : open.length === 0 ? (
                <EmptyState icon={<Clock />} title="No open follow-ups" body="When you create a follow-up from a finding, it waits here until it’s resolved." action={<Link href="/exceptions" className="tb-btn">Go to Exceptions</Link>} />
              ) : (
                open.map((o) => (
                  <div key={o.id} className="flex flex-wrap items-center gap-4 px-5 py-3.5" style={{ boxShadow: "0 1px 0 var(--line)" }}>
                    <Clock size={18} style={{ color: o.status === "OVERDUE" ? "var(--err)" : "var(--accentText)" }} />
                    <span className="flex min-w-[240px] flex-1 flex-col">
                      <span className="text-[13.5px] font-medium">{o.note || "Follow-up on a finding"}</span>
                      <span className="text-[12px]" style={{ color: "var(--faint)" }}>
                        {o.owner ? `Owner ${o.owner}` : "Unassigned"} · {o.deadline ? `due ${formatDate(o.deadline)}` : "no deadline"} · created by {o.created_by ?? "-"}
                      </span>
                    </span>
                    <StatusPill tone={o.status === "OVERDUE" ? "err" : o.status === "IN_PROGRESS" ? "med" : "muted"}>{o.status.toLowerCase().replace("_", " ")}</StatusPill>
                    {o.status === "OPEN" && (
                      <button type="button" className="tb-btn !px-2.5 !py-1.5 text-[12.5px]" onClick={() => void update(o, "IN_PROGRESS")}>Start</button>
                    )}
                    <button type="button" className="tb-btn !px-2.5 !py-1.5 text-[12.5px]" onClick={() => void update(o, "RESOLVED")}>Resolve</button>
                    <Link href={`/reports/${o.report_id}`} className="tb-btn tb-btn-primary !px-2.5 !py-1.5 text-[12.5px]">Report</Link>
                  </div>
                ))
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
