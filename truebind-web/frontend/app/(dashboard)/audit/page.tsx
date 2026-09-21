"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { AuditLogEntry } from "@/lib/types";
import { ReportPicker } from "@/components/report/ReportPicker";
import { Table, type Column } from "@/components/ui/Table";
import { Button } from "@/components/ui/Button";
import { formatDateTime } from "@/lib/formatters";
import styles from "./page.module.css";

export default function AuditPage() {
  const [reportId, setReportId] = useState<string | null>(null);
  const [entries, setEntries] = useState<AuditLogEntry[]>([]);
  const [actionType, setActionType] = useState("");
  const [actor, setActor] = useState("");

  useEffect(() => {
    if (!reportId) return;
    api.getAuditLog(reportId, { actionType: actionType || undefined, actor: actor || undefined }).then(setEntries);
  }, [reportId, actionType, actor]);

  const actionTypes = Array.from(new Set(entries.map((e) => e.action_type))).sort();

  const columns: Column<AuditLogEntry>[] = [
    { key: "timestamp", header: "Timestamp", render: (e) => formatDateTime(e.created_at) },
    { key: "action", header: "Action", render: (e) => e.action_type.replace(/_/g, " ") },
    { key: "entity", header: "Entity", render: (e) => e.entity_type },
    { key: "actor", header: "Actor", render: (e) => e.actor },
    { key: "details", header: "Details", render: (e) => (
      <span className={styles.details}>
        {e.before_value && <span>before: {JSON.stringify(e.before_value)} </span>}
        {e.after_value && <span>after: {JSON.stringify(e.after_value)}</span>}
      </span>
    ) },
  ];

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <span className="eyebrow">Every mapping decision, logged</span>
          <h1>Compliance &amp; Audit</h1>
        </div>
        <ReportPicker value={reportId} onChange={setReportId} />
      </div>

      {reportId && (
        <>
          <div className={styles.filters}>
            <select value={actionType} onChange={(e) => setActionType(e.target.value)}>
              <option value="">All action types</option>
              {actionTypes.map((t) => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}
            </select>
            <input placeholder="Filter by actor…" value={actor} onChange={(e) => setActor(e.target.value)} />
            <Button variant="secondary" onClick={() => window.open(api.exportAuditCsvUrl(reportId), "_blank")}>
              Export audit trail (CSV)
            </Button>
          </div>

          <Table columns={columns} rows={entries} rowKey={(e) => e.id} />
        </>
      )}
    </div>
  );
}
