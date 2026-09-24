"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { Button } from "@/components/ui/Button";
import { ErrorState, Panel, PageHeader, Pill, ds } from "@/components/ds";
import { PageSkeleton } from "@/components/layout/ShellSkeleton";
import { ActivityFeed } from "@/components/ops/ActivityFeed";

export default function AuditPage() {
  const [reportId, setReportId] = useState("");
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
        <Panel title={reportId ? "Report timeline" : "Organisation activity"} icon="audit">
          <ActivityFeed entries={log.data ?? []} showReportLinks={!reportId} />
        </Panel>
      </div>
    </>
  );
}
