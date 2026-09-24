"use client";

import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { formatDateTime, timeAgo } from "@/lib/formatters";
import { Button } from "@/components/ui/Button";
import { EmptyState, ErrorState, Panel, PageHeader, Pill, SegmentedControl, severityTone } from "@/components/ds";
import { PageSkeleton } from "@/components/layout/ShellSkeleton";
import { useShell } from "@/components/layout/ShellContext";
import styles from "@/components/ops/ops.module.css";

const SOURCE_LABEL: Record<string, string> = {
  INBOUND: "File received", REVIEW_NEEDED: "Mapping ready", REPORT_READY: "Report ready",
  PROCESSING_FAILED: "Processing failed", EXPORT_COMPLETE: "Export sent", EXPORT_FAILED: "Export not sent",
  COVERAGE: "Coverage", MANDATORY_FAIL: "Missing data", NOT_EVALUABLE: "Not evaluable", DUPLICATE: "Duplicates",
  MAPPING_COMPLETENESS: "Mapping gap",
};

type Group = "all" | "intake" | "processing" | "quality" | "delivery";
const GROUP_OF: Record<string, Group> = {
  INBOUND: "intake", REVIEW_NEEDED: "processing", REPORT_READY: "processing", PROCESSING_FAILED: "processing",
  EXPORT_COMPLETE: "delivery", EXPORT_FAILED: "delivery", COVERAGE: "quality", MANDATORY_FAIL: "quality",
  NOT_EVALUABLE: "quality", DUPLICATE: "quality", MAPPING_COMPLETENESS: "quality",
};

function actionFor(source: string, reportId: string): { href: string; label: string } {
  if (source === "REVIEW_NEEDED") return { href: `/upload?reportId=${reportId}`, label: "Review mapping" };
  if (source === "DUPLICATE") return { href: `/duplicates?reportId=${reportId}`, label: "Review duplicates" };
  if (source === "MANDATORY_FAIL" || source === "NOT_EVALUABLE") return { href: `/exceptions?reportId=${reportId}`, label: "Open exceptions" };
  if (source.startsWith("EXPORT")) return { href: "/exports", label: "Open exports" };
  return { href: `/reports/${reportId}`, label: "Open report" };
}

export default function AlertsPage() {
  const [unreadOnly, setUnreadOnly] = useState(true);
  const [group, setGroup] = useState<Group>("all");
  const { data, error, loading, reload } = useApi(() => api.listAlertsPage({ acknowledged: unreadOnly ? false : undefined, limit: 200 }), [unreadOnly], 15_000);
  const shell = useShell();
  const [busy, setBusy] = useState(false);

  async function markRead(ids: string[]) {
    setBusy(true);
    try {
      await Promise.all(ids.map((id) => api.acknowledgeAlert(id)));
      reload();
      shell.refresh();
    } finally {
      setBusy(false);
    }
  }

  if (loading && !data) return <PageSkeleton label="Loading alerts" />;
  if (error && !data) return <ErrorState title="Alerts could not be loaded" message={error} onRetry={reload} />;
  const allItems = data?.items ?? [];
  const count = (g: Group) => allItems.filter((a) => g === "all" || (GROUP_OF[a.source] ?? "processing") === g).length;
  const items = allItems.filter((a) => group === "all" || (GROUP_OF[a.source] ?? "processing") === group);
  return (
    <>
      <PageHeader eyebrow="Govern" title="Alerts" description="What happened that needs your attention, newest first."
        actions={<>
          <Button variant="secondary" onClick={() => setUnreadOnly(!unreadOnly)}>{unreadOnly ? "Show all" : "Unread only"}</Button>
          {items.some((a) => !a.acknowledged) && <Button variant="primary" loading={busy} onClick={() => markRead(items.filter((a) => !a.acknowledged).map((a) => a.id))}>Mark all read</Button>}
        </>} />
      <div style={{ marginBottom: 12 }}>
        <SegmentedControl label="Alert type" value={group} onChange={setGroup} options={[
          { value: "all", label: "All", count: count("all") }, { value: "intake", label: "Intake", count: count("intake") },
          { value: "processing", label: "Processing", count: count("processing") }, { value: "quality", label: "Data quality", count: count("quality") },
          { value: "delivery", label: "Delivery", count: count("delivery") }]} />
      </div>
      <Panel flush>
        {items.length === 0 ? <EmptyState icon="bell" title={unreadOnly ? "No unread alerts" : "No alerts yet"} body="Alerts appear when files arrive, need review, complete, fail, or are sent." /> : (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead><tr><th scope="col">Severity</th><th scope="col">Type</th><th scope="col">What happened</th><th scope="col">When</th><th scope="col">Action</th><th scope="col"><span className="sr-only">Read</span></th></tr></thead>
              <tbody>
                {items.map((a) => {
                  const act = actionFor(a.source, a.report_id);
                  return (
                    <tr key={a.id} style={{ fontWeight: a.acknowledged ? 400 : 600 }}>
                      <td><Pill tone={severityTone(a.severity)}>{a.severity.toLowerCase()}</Pill></td>
                      <td className={styles.sub}>{SOURCE_LABEL[a.source] ?? a.source}</td>
                      <td style={{ maxWidth: 560 }}>{a.message}</td>
                      <td><time dateTime={a.created_at} title={formatDateTime(a.created_at)}>{timeAgo(a.created_at)}</time></td>
                      <td><Link href={act.href}>{act.label}</Link></td>
                      <td>{a.acknowledged ? <span className={styles.sub}>Read</span> :
                        <Button size="sm" variant="ghost" onClick={() => markRead([a.id])}>Mark read</Button>}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}
