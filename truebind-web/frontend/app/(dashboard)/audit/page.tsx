"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { Button } from "@/components/ui/Button";
import { ErrorState, MetricCard, Panel, PageHeader, Pill, Timeline, ds } from "@/components/ds";
import { describeAudit } from "@/lib/audit";
import { formatDate, formatDateTime } from "@/lib/formatters";
import type { AuditLogEntry } from "@/lib/types";
import Link from "next/link";
import { PageSkeleton } from "@/components/layout/ShellSkeleton";

function byDay(entries: AuditLogEntry[]): [string, AuditLogEntry[]][] {
  const out = new Map<string, AuditLogEntry[]>();
  for (const e of entries) {
    const d = formatDate(e.created_at);
    out.set(d, [...(out.get(d) ?? []), e]);
  }
  return [...out.entries()];
}

export default function AuditPage() {
  const params = useSearchParams();
  const [reportId, setReportId] = useState(params.get("reportId") ?? "");
  const reports = useApi(() => api.listReports());
  const log = useApi(() => (reportId ? api.getAuditLog(reportId) : api.tenantAudit(300)), [reportId]);
  const verify = useApi(() => api.verifyAudit());
  if (log.loading && !log.data) return <PageSkeleton label="Loading audit trail" />;
  if (log.error && !log.data) return <ErrorState title="The audit trail could not be loaded" message={log.error} onRetry={log.reload} />;
  const v = verify.data;
  return (
    <>
      <PageHeader eyebrow="Govern" title="Audit trail"
        description="Every action on your data, in order, with who did it. Entries are hash-chained: any later edit or deletion breaks the chain and is detected."
        actions={<>
          {v && (v.intact ? <Pill tone="good">Chain intact · {v.entries} entries</Pill> : <Pill tone="bad">Chain broken at #{v.first_bad_seq}</Pill>)}
          {reportId && <Button variant="secondary" onClick={() => window.open(api.exportAuditCsvUrl(reportId), "_blank")}>Export CSV</Button>}
        </>} />
      <div className={ds.stack}>
        <div className={ds.toolbar}>
          <label className={ds.muted} htmlFor="audit-report">Scope</label>
          <select id="audit-report" className={ds.select} value={reportId} onChange={(e) => setReportId(e.target.value)}>
            <option value="">All activity</option>
            {(reports.data ?? []).map((r) => <option key={r.id} value={r.id}>{r.file_name}</option>)}
          </select>
          <Button variant="ghost" size="sm" onClick={() => { log.reload(); verify.reload(); }}>Refresh</Button>
        </div>
        <div className={`${ds.grid} ${ds.cols3}`}>
          <MetricCard icon="shield" label="Chain integrity" tone={v ? (v.intact ? "good" : "bad") : "neutral"}
            value={v ? (v.intact ? "Intact" : "Broken") : "…"} caption={v ? `${v.entries.toLocaleString("en-GB")} entries verified` : "Verifying…"} />
          <MetricCard icon="lineage" label={reportId ? "Entries for this file" : "Entries shown"} value={(log.data ?? []).length.toLocaleString("en-GB")}
            caption={reportId ? "Every recorded step for the selected file" : "Most recent organisation activity"} />
          <MetricCard icon="user" label="People and systems" value={new Set((log.data ?? []).map((e) => e.actor)).size.toLocaleString("en-GB")}
            caption="Distinct actors in this view" />
        </div>
        <Panel title={reportId ? "Lineage timeline" : "Organisation activity"} icon="lineage">
          {byDay(log.data ?? []).map(([day, entries]) => (
            <div key={day} style={{ marginBottom: 12 }}>
              <p className={ds.muted} style={{ fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase", margin: "4px 0 10px" }}>{day}</p>
              <Timeline items={entries.map((e) => {
                const d = describeAudit(e);
                return { id: e.id, icon: d.icon, tone: d.tone === "info" ? "brand" : d.tone, title: d.title, body: d.detail,
                  meta: <>{formatDateTime(e.created_at)} · {e.actor} · <span className={ds.mono}>#{e.seq}</span>
                    {!reportId && e.report_id && <> · <Link href={`/reports/${e.report_id}`}>report</Link></>}</> };
              })} />
            </div>
          ))}
          {(log.data ?? []).length === 0 && <p className={ds.muted}>No activity recorded yet.</p>}
        </Panel>
      </div>
    </>
  );
}
