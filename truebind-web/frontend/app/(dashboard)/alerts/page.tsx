"use client";

import Link from "next/link";
import { useState } from "react";
import { Bell, Checks } from "@phosphor-icons/react";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { useUi } from "@/lib/ui";
import { useShell } from "@/components/layout/ShellContext";
import { formatDateTime, timeAgo } from "@/lib/formatters";
import { EmptyState, ErrorState, LoadingState, PageHeader, StatusPill } from "@/components/nocturne/ui";
import { SEV } from "@/components/nocturne/status";

const SOURCE_LABEL: Record<string, string> = {
  INBOUND: "File received",
  REVIEW_NEEDED: "Mapping ready",
  REPORT_READY: "Report ready",
  PROCESSING_FAILED: "Processing failed",
  EXPORT_COMPLETE: "Export sent",
  EXPORT_FAILED: "Export not sent",
  COVERAGE: "Coverage",
  MANDATORY_FAIL: "Missing data",
  NOT_EVALUABLE: "Not evaluable",
  DUPLICATE: "Duplicates",
  MAPPING_COMPLETENESS: "Mapping gap",
  OVERDUE: "Follow-up overdue",
};
type Group = "all" | "intake" | "processing" | "quality" | "delivery";
const GROUP_OF: Record<string, Group> = {
  INBOUND: "intake",
  REVIEW_NEEDED: "processing",
  REPORT_READY: "processing",
  PROCESSING_FAILED: "processing",
  EXPORT_COMPLETE: "delivery",
  EXPORT_FAILED: "delivery",
  COVERAGE: "quality",
  MANDATORY_FAIL: "quality",
  NOT_EVALUABLE: "quality",
  DUPLICATE: "quality",
  MAPPING_COMPLETENESS: "quality",
};
function actionFor(source: string, reportId: string) {
  if (source === "REVIEW_NEEDED") return { href: `/upload?reportId=${reportId}`, label: "Review mapping" };
  if (source === "DUPLICATE") return { href: `/duplicates?reportId=${reportId}`, label: "Review duplicates" };
  if (source === "MANDATORY_FAIL" || source === "NOT_EVALUABLE") return { href: `/exceptions?reportId=${reportId}`, label: "Open exceptions" };
  if (source === "OVERDUE") return { href: "/todo", label: "Open work queue" };
  if (source.startsWith("EXPORT")) return { href: "/exports", label: "Open exports" };
  return { href: `/reports/${reportId}`, label: "Open report" };
}

export default function AlertsPage() {
  const { toast } = useUi();
  const shell = useShell();
  const [unreadOnly, setUnreadOnly] = useState(true);
  const [group, setGroup] = useState<Group>("all");
  const [busy, setBusy] = useState(false);
  const { data, error, loading, reload } = useApi(() => api.listAlertsPage({ acknowledged: unreadOnly ? false : undefined, limit: 200 }), [unreadOnly], 15_000);

  const markRead = async (ids: string[]) => {
    setBusy(true);
    try {
      await Promise.all(ids.map((id) => api.acknowledgeAlert(id)));
      toast(ids.length > 1 ? `${ids.length} alerts marked read` : "Alert marked read", "ok");
      reload();
      shell.refresh();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Alerts could not be marked read.", "err");
    } finally {
      setBusy(false);
    }
  };

  const all = data?.items ?? [];
  const count = (g: Group) => all.filter((a) => g === "all" || (GROUP_OF[a.source] ?? "processing") === g).length;
  const items = all.filter((a) => group === "all" || (GROUP_OF[a.source] ?? "processing") === group);
  const unread = items.filter((a) => !a.acknowledged);

  return (
    <div className="flex max-w-[1200px] flex-col gap-6 px-4 pb-12 pt-8 sm:px-9">
      <PageHeader
        kicker="Govern"
        title="Alerts"
        sub="What happened that needs your attention, newest first. Each alert links to where the work is."
        actions={
          <>
            <button type="button" className="tb-btn" onClick={() => setUnreadOnly((v) => !v)}>{unreadOnly ? "Show all" : "Unread only"}</button>
            <button type="button" className="tb-btn tb-btn-primary" disabled={busy || unread.length === 0} onClick={() => void markRead(unread.map((a) => a.id))}>
              <Checks />
              Mark all read
            </button>
          </>
        }
      />
      <div className="flex flex-wrap gap-0.5 self-start rounded-[9px] p-[3px]" style={{ boxShadow: "inset 0 0 0 1px var(--line2)" }} role="tablist" aria-label="Alert type">
        {(
          [
            ["all", "All"],
            ["intake", "Intake"],
            ["processing", "Processing"],
            ["quality", "Data quality"],
            ["delivery", "Delivery"],
          ] as [Group, string][]
        ).map(([k, l]) => (
          <button key={k} type="button" role="tab" aria-selected={group === k} onClick={() => setGroup(k)} className="flex cursor-pointer items-center gap-1.5 rounded-[7px] px-3 py-1.5 text-[13px]" style={{ background: group === k ? "var(--accentTint)" : "transparent", color: group === k ? "var(--text)" : "var(--muted)" }}>
            {l}
            <span className="tnum text-[11.5px]" style={{ color: "var(--faint)" }}>{count(k)}</span>
          </button>
        ))}
      </div>
      <div className="tb-card overflow-hidden">
        {loading && !data ? (
          <div className="p-5"><LoadingState label="Loading alerts" rows={6} /></div>
        ) : error && !data ? (
          <div className="p-5"><ErrorState title="Alerts could not be loaded" message={error} onRetry={reload} /></div>
        ) : items.length === 0 ? (
          <EmptyState icon={<Bell />} title={unreadOnly ? "No unread alerts" : "No alerts yet"} body="Alerts appear when files arrive, need review, complete, fail, or are sent." />
        ) : (
          items.map((a) => {
            const act = actionFor(a.source, a.report_id);
            return (
              <div key={a.id} className="grid grid-cols-[10px_minmax(0,1fr)_auto] items-start gap-4 px-5 py-4 transition-colors hover:bg-[var(--accentTint)]" style={{ boxShadow: "0 1px 0 var(--line)" }}>
                <span className="mt-1.5 h-2 w-2 rounded-full" style={{ background: SEV[a.severity]?.c ?? "var(--muted)" }} />
                <span className="flex min-w-0 flex-col gap-1">
                  <span className="flex flex-wrap items-center gap-2 text-[13.5px]" style={{ fontWeight: a.acknowledged ? 400 : 600 }}>
                    {a.message}
                    {!a.acknowledged && <span className="h-1.5 w-1.5 flex-none rounded-full" style={{ background: "var(--accent)" }} aria-label="unread" />}
                  </span>
                  <span className="text-[12px]" style={{ color: "var(--faint)" }}>
                    {SOURCE_LABEL[a.source] ?? a.source} · <time dateTime={a.created_at} title={formatDateTime(a.created_at)}>{timeAgo(a.created_at)}</time> ·{" "}
                    <Link href={act.href} style={{ color: "var(--accentText)" }} onClick={() => !a.acknowledged && void api.acknowledgeAlert(a.id).then(shell.refresh).catch(() => undefined)}>{act.label}</Link>
                  </span>
                </span>
                <span className="flex items-center gap-2">
                  <StatusPill tone={SEV[a.severity]?.tone ?? "muted"}>{SEV[a.severity]?.label ?? a.severity}</StatusPill>
                  {a.acknowledged ? (
                    <span className="text-[12px]" style={{ color: "var(--faint)" }}>Read</span>
                  ) : (
                    <button type="button" className="tb-btn tb-btn-ghost !px-2 !py-1 text-[12px]" disabled={busy} onClick={() => void markRead([a.id])}>Mark read</button>
                  )}
                </span>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
