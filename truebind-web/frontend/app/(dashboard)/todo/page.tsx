"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { Alert, Obligation, Report } from "@/lib/types";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { formatDate, formatDateTime } from "@/lib/formatters";
import styles from "./page.module.css";

export default function TodoPage() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [overdue, setOverdue] = useState<Obligation[]>([]);
  const [pendingReports, setPendingReports] = useState<Report[]>([]);
  const [busy, setBusy] = useState(false);

  async function refresh() {
    const [alertList, obligationList, reports] = await Promise.all([
      api.listAlerts({ acknowledged: false }),
      api.listObligations({ status: "OVERDUE" }),
      api.listReports(),
    ]);
    setAlerts(alertList);
    setOverdue(obligationList);
    setPendingReports(reports.filter((r) => r.status !== "COMPLETE"));
  }

  useEffect(() => { refresh(); }, []);

  async function acknowledgeAll() {
    setBusy(true);
    try {
      await Promise.all(alerts.map((a) => api.acknowledgeAlert(a.id)));
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  const totalItems = alerts.length + overdue.length + pendingReports.length;

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1>Alerts &amp; To-do</h1>
        {alerts.length > 0 && (
          <Button variant="secondary" onClick={acknowledgeAll} disabled={busy}>
            {busy ? "Acknowledging…" : "Acknowledge all"}
          </Button>
        )}
      </div>

      {totalItems === 0 && <p className={styles.empty}>Nothing needs attention right now.</p>}

      {overdue.length > 0 && (
        <section className={styles.section}>
          <h2>Overdue obligations <Badge tone="error">{overdue.length}</Badge></h2>
          <ul className={styles.list}>
            {overdue.map((o) => (
              <li key={o.id}>
                <span>{o.owner ?? "unassigned"} — due {formatDate(o.deadline)}</span>
                {o.note && <span className={styles.note}>{o.note}</span>}
              </li>
            ))}
          </ul>
        </section>
      )}

      {alerts.length > 0 && (
        <section className={styles.section}>
          <h2>Unacknowledged alerts <Badge tone="warning">{alerts.length}</Badge></h2>
          <ul className={styles.list}>
            {alerts.map((a) => (
              <li key={a.id}>
                <Link href={`/reports/${a.report_id}`}>{a.message}</Link>
                <span className={styles.timestamp}>{formatDateTime(a.created_at)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {pendingReports.length > 0 && (
        <section className={styles.section}>
          <h2>Awaiting mapping confirmation <Badge tone="info">{pendingReports.length}</Badge></h2>
          <ul className={styles.list}>
            {pendingReports.map((r) => (
              <li key={r.id}>
                <Link href="/upload">{r.file_name}</Link>
                <span className={styles.timestamp}>{r.status}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
