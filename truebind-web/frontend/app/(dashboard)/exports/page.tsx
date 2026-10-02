"use client";

import Link from "next/link";
import { useState } from "react";
import { DownloadSimple, PaperPlaneTilt } from "@phosphor-icons/react";
import { api, ApiError } from "@/lib/api";
import type { Delivery } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { useUi } from "@/lib/ui";
import { formatBytes, formatDateTime, timeAgo } from "@/lib/formatters";
import { EmptyState, ErrorState, LoadingState, PageHeader, StatusPill } from "@/components/nocturne/ui";
import { exportFile } from "@/lib/exports";

const KIND_LABEL: Record<string, string> = { claims_csv: "Claims", exceptions_csv: "Exceptions", audit_csv: "Audit trail" };
const ST: Record<Delivery["status"], ["ok" | "err" | "muted", string]> = { DELIVERED: ["ok", "Delivered"], FAILED: ["err", "Failed"], NOT_CONFIGURED: ["muted", "Not configured"] };

export default function ExportsPage() {
  const { toast } = useUi();
  const deliveries = useApi(() => api.listDeliveries(), [], 15_000);
  const reports = useApi(() => api.listReports());
  const channels = useApi(() => api.channels());
  const [reportId, setReportId] = useState("");
  const [kind, setKind] = useState("claims_csv");
  const [recipient, setRecipient] = useState("");
  const [busy, setBusy] = useState(false);
  const [retrying, setRetrying] = useState<string | null>(null);
  const complete = (reports.data ?? []).filter((r) => r.status === "COMPLETE");
  const selected = reportId || complete[0]?.id || "";
  const sel = complete.find((r) => r.id === selected);
  const email = channels.data?.outbound.find((c) => c.id === "email");
  const emailLive = email?.status === "active";

  const send = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selected) return;
    setBusy(true);
    try {
      const d = await api.sendDelivery(selected, kind, recipient.trim());
      toast(d.status === "DELIVERED" ? `Sent to ${d.destination} · recorded in the audit trail` : d.error ?? "Recorded, not sent.", d.status === "DELIVERED" ? "ok" : "warn");
      deliveries.reload();
    } catch (err) {
      toast(err instanceof ApiError ? err.message : "Could not send.", "err");
    } finally {
      setBusy(false);
    }
  };
  const retry = async (d: Delivery) => {
    setRetrying(d.id);
    try {
      const r = await api.sendDelivery(d.report_id, d.kind, d.destination ?? "");
      toast(r.status === "DELIVERED" ? `Delivered to ${r.destination}` : r.error ?? "Still not sent.", r.status === "DELIVERED" ? "ok" : "warn");
      deliveries.reload();
    } catch (err) {
      toast(err instanceof ApiError ? err.message : "Retry failed.", "err");
    } finally {
      setRetrying(null);
    }
  };
  const rows = deliveries.data?.items ?? [];

  return (
    <div className="flex max-w-[1440px] flex-col gap-6 px-4 pb-12 pt-8 sm:px-6">
      <PageHeader kicker="Deliver" title="Exports & deliveries" sub="Every output TrueBind produced: what, for which report, where it went and whether it arrived." />
      <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-6 xl:grid-cols-[minmax(0,1.6fr)_minmax(320px,1fr)]">
        <section className="flex flex-col gap-3">
          <span className="text-[15px] font-medium">Delivery history</span>
          <div className="tb-card overflow-hidden">
            {deliveries.loading && !deliveries.data ? (
              <div className="p-5"><LoadingState label="Loading deliveries" rows={6} /></div>
            ) : deliveries.error && !deliveries.data ? (
              <div className="p-5"><ErrorState title="Deliveries could not be loaded" message={deliveries.error} onRetry={deliveries.reload} /></div>
            ) : rows.length === 0 ? (
              <EmptyState icon={<PaperPlaneTilt />} title="Nothing exported yet" body="Downloads and deliveries from any report are recorded here." />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[680px] border-collapse text-[13px]">
                  <thead>
                    <tr className="text-left text-[11px] uppercase tracking-[.06em]" style={{ color: "var(--faint)" }}>
                      {["Output", "Channel", "Destination", "When", "Status"].map((h) => <th key={h} className="px-4 py-2.5 font-medium">{h}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((d) => (
                      <tr key={d.id} style={{ boxShadow: "0 -1px 0 var(--line)" }}>
                        <td className="px-4 py-3">
                          <Link href={`/reports/${d.report_id}`} className="font-medium hover:underline">{KIND_LABEL[d.kind] ?? d.kind}</Link>
                          <div className="text-[12px]" style={{ color: "var(--faint)" }}>{d.file_name}{d.size_bytes ? ` · ${formatBytes(d.size_bytes)}` : ""}</div>
                        </td>
                        <td className="px-4 py-3" style={{ color: "var(--muted)" }}>{d.channel === "download" ? "Download" : d.channel === "email" ? "Email" : d.channel.toUpperCase()}</td>
                        <td className="max-w-[220px] truncate px-4 py-3" style={{ color: "var(--muted)" }}>{d.destination ?? `by ${d.created_by ?? "—"}`}</td>
                        <td className="tnum px-4 py-3"><time dateTime={d.created_at} title={formatDateTime(d.created_at)}>{timeAgo(d.created_at)}</time></td>
                        <td className="px-4 py-3">
                          <StatusPill tone={ST[d.status][0]}>{ST[d.status][1]}</StatusPill>
                          {d.error && <div className="mt-1 max-w-[260px] text-[12px]" style={{ color: "var(--muted)" }}>{d.error}</div>}
                          {d.channel === "email" && d.status !== "DELIVERED" && d.destination && (
                            <button type="button" className="tb-btn tb-btn-ghost mt-1 !px-2 !py-1 text-[12px]" disabled={retrying === d.id} onClick={() => void retry(d)}>{retrying === d.id ? "Retrying…" : "Retry"}</button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </section>
        <div className="flex flex-col gap-4">
          <section className="tb-card flex flex-col gap-3 p-4">
            <span className="text-[15px] font-medium">Send an output</span>
            <span className="text-[12.5px]" style={{ color: emailLive ? "var(--muted)" : "var(--warn)" }}>{!channels.data ? "Checking the email channel…" : emailLive ? "Delivered by email from this server." : "Email isn’t configured on this server — the attempt will be recorded, not sent. Downloads work now."}</span>
            {complete.length === 0 ? (
              <span className="text-[13px]" style={{ color: "var(--muted)" }}>Outputs can be sent once a report is complete.</span>
            ) : (
              <form onSubmit={send} className="flex flex-col gap-3">
                <div>
                  <label className="tb-label" htmlFor="ex-report">Report</label>
                  <select id="ex-report" className="tb-input" value={selected} onChange={(e) => setReportId(e.target.value)}>
                    {complete.map((r) => <option key={r.id} value={r.id}>{r.file_name}</option>)}
                  </select>
                </div>
                <div>
                  <label className="tb-label" htmlFor="ex-kind">Output</label>
                  <select id="ex-kind" className="tb-input" value={kind} onChange={(e) => setKind(e.target.value)}>
                    {Object.entries(KIND_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                </div>
                <div>
                  <label className="tb-label" htmlFor="ex-to">Recipient email</label>
                  <input id="ex-to" className="tb-input" type="email" required value={recipient} onChange={(e) => setRecipient(e.target.value)} placeholder="bordereaux@carrier.com" />
                </div>
                <div className="flex flex-wrap gap-2">
                  <button type="submit" className="tb-btn tb-btn-solid" disabled={busy}><PaperPlaneTilt />{busy ? "Sending…" : "Send"}</button>
                  {sel && (
                    <button
                      type="button"
                      className="tb-btn"
                      onClick={() => void exportFile(kind === "claims_csv" ? api.exportClaimsUrl(sel.id) : kind === "exceptions_csv" ? api.exportExceptionsUrl(sel.id) : api.exportAuditCsvUrl(sel.id), `${sel.file_name.replace(/\.\w+$/, "")}_${kind.replace("_csv", "")}`, toast).then(() => setTimeout(deliveries.reload, 800))}
                    >
                      <DownloadSimple />
                      Download instead
                    </button>
                  )}
                </div>
              </form>
            )}
          </section>
          <section className="tb-card flex flex-col px-5 pb-2 pt-4">
            <span className="text-[15px] font-medium">Outbound channels</span>
            <ul className="m-0 flex list-none flex-col p-0">
              {(channels.data?.outbound ?? []).map((c) => (
                <li key={c.id} className="flex items-start justify-between gap-3 py-3" style={{ boxShadow: "0 1px 0 var(--line)" }}>
                  <span className="flex min-w-0 flex-col">
                    <span className="text-[13.5px] font-medium">{c.name}</span>
                    <span className="text-[12.5px]" style={{ color: "var(--muted)" }}>{c.detail}</span>
                  </span>
                  <StatusPill tone={c.status === "active" ? "ok" : c.status === "planned" ? "muted" : "warn"}>{c.status === "active" ? "Live" : c.status === "not_set_up" ? "Ready to set up" : c.status === "planned" ? "Planned" : "Not configured"}</StatusPill>
                </li>
              ))}
            </ul>
            <Link href="/settings?tab=channels" className="py-3 text-[12.5px]" style={{ color: "var(--accentText)" }}>Manage channels →</Link>
          </section>
        </div>
      </div>
    </div>
  );
}
