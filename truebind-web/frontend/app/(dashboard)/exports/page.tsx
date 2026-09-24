"use client";

import Link from "next/link";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { formatBytes, formatDateTime, timeAgo } from "@/lib/formatters";
import { Button } from "@/components/ui/Button";
import { EmptyState, ErrorState, Panel, PageHeader, Pill, ds } from "@/components/ds";
import { PageSkeleton } from "@/components/layout/ShellSkeleton";
import styles from "@/components/ops/ops.module.css";

const KIND_LABEL: Record<string, string> = { claims_csv: "Claims (CSV)", exceptions_csv: "Exceptions (CSV)", audit_csv: "Audit trail (CSV)" };
const STATUS_TONE = { DELIVERED: "good", FAILED: "bad", NOT_CONFIGURED: "neutral" } as const;

export default function ExportsPage() {
  const deliveries = useApi(() => api.listDeliveries(), [], 15_000);
  const reports = useApi(() => api.listReports());
  const channels = useApi(() => api.channels());
  const [reportId, setReportId] = useState("");
  const [kind, setKind] = useState("claims_csv");
  const [recipient, setRecipient] = useState("");
  const [msg, setMsg] = useState<{ tone: "good" | "bad"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const complete = (reports.data ?? []).filter((r) => r.status === "COMPLETE");
  const email = channels.data?.outbound.find((c) => c.id === "email");
  const selected = reportId || complete[0]?.id || "";

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!selected) return;
    setBusy(true);
    setMsg(null);
    try {
      const d = await api.sendDelivery(selected, kind, recipient);
      setMsg(d.status === "DELIVERED" ? { tone: "good", text: `Sent to ${d.destination}.` } : { tone: "bad", text: d.error ?? "Not sent." });
      deliveries.reload();
    } catch (err) {
      setMsg({ tone: "bad", text: err instanceof ApiError ? err.message : "Could not send." });
    } finally {
      setBusy(false);
    }
  }

  if (deliveries.loading && !deliveries.data) return <PageSkeleton label="Loading exports" />;
  if (deliveries.error && !deliveries.data) return <ErrorState title="Exports could not be loaded" message={deliveries.error} onRetry={deliveries.reload} />;
  const rows = deliveries.data?.items ?? [];

  return (
    <>
      <PageHeader eyebrow="Deliver" title="Exports & deliveries"
        description="Every output TrueBind produced: what, for which report, where it went and whether it arrived." />
      <div className={`${ds.grid} ${ds.split}`}>
        <Panel title="Delivery history" icon="exports" flush>
          {rows.length === 0 ? <EmptyState icon="exports" title="Nothing exported yet" body="Downloads and e-mail deliveries from any report are recorded here." /> : (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead><tr><th scope="col">Output</th><th scope="col">Channel</th><th scope="col">Destination</th><th scope="col">When</th><th scope="col">Status</th></tr></thead>
                <tbody>
                  {rows.map((d) => (
                    <tr key={d.id}>
                      <td><Link href={`/reports/${d.report_id}`}>{KIND_LABEL[d.kind] ?? d.kind}</Link><div className={styles.sub}>{d.file_name}{d.size_bytes ? ` · ${formatBytes(d.size_bytes)}` : ""}</div></td>
                      <td className={styles.sub}>{d.channel === "download" ? "Download" : "E-mail"}</td>
                      <td className={styles.sub}>{d.destination ?? `by ${d.created_by ?? "—"}`}</td>
                      <td><time dateTime={d.created_at} title={formatDateTime(d.created_at)}>{timeAgo(d.created_at)}</time></td>
                      <td><Pill tone={STATUS_TONE[d.status]}>{d.status === "NOT_CONFIGURED" ? "Not configured" : d.status.toLowerCase()}</Pill>
                        {d.error && <div className={styles.sub} style={{ maxWidth: 280 }}>{d.error}</div>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
        <div className={ds.stack}>
          <Panel title="Send an output" icon="mail"
            subtitle={email?.status === "active" ? "Delivered by e-mail from this server." : "E-mail is not configured on this server; the attempt will be recorded, not sent."}>
            {complete.length === 0 ? <p className={styles.muted}>Outputs can be sent once a report is complete.</p> : (
              <form onSubmit={send} className={ds.stack} style={{ gap: 10 }}>
                <label className={styles.sub}>Report
                  <select className={ds.select} style={{ width: "100%", marginTop: 4 }} value={selected} onChange={(e) => setReportId(e.target.value)}>
                    {complete.map((r) => <option key={r.id} value={r.id}>{r.file_name}</option>)}
                  </select>
                </label>
                <label className={styles.sub}>Output
                  <select className={ds.select} style={{ width: "100%", marginTop: 4 }} value={kind} onChange={(e) => setKind(e.target.value)}>
                    {Object.entries(KIND_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                </label>
                <label className={styles.sub}>Recipient e-mail
                  <input className={ds.input} style={{ width: "100%", marginTop: 4 }} type="email" required value={recipient}
                         onChange={(e) => setRecipient(e.target.value)} placeholder="ops@cedant.example" />
                </label>
                <Button type="submit" loading={busy}>Send</Button>
                {msg && <p role="status" style={{ margin: 0, fontSize: 13, color: msg.tone === "good" ? "var(--color-success)" : "var(--color-error)" }}>{msg.text}</p>}
              </form>
            )}
          </Panel>
          <Panel title="Outbound channels" icon="link">
            <ul className={ds.stack} style={{ gap: 10, listStyle: "none", padding: 0, margin: 0 }}>
              {(channels.data?.outbound ?? []).map((c) => (
                <li key={c.id} className={styles.row} style={{ justifyContent: "space-between" }}>
                  <span><strong style={{ fontSize: 14 }}>{c.name}</strong><div className={styles.sub}>{c.detail}</div></span>
                  <Pill tone={c.status === "active" ? "live" : c.status === "planned" ? "neutral" : "warn"}>{c.status.replace("_", " ")}</Pill>
                </li>
              ))}
            </ul>
          </Panel>
        </div>
      </div>
    </>
  );
}
