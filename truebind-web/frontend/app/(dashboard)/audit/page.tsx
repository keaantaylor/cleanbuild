"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { ArrowsClockwise, DownloadSimple, Robot, ShieldCheck, User } from "@phosphor-icons/react";
import { api } from "@/lib/api";
import type { AuditLogEntry } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { useUi } from "@/lib/ui";
import { describeAudit } from "@/lib/audit";
import { formatDate, formatDateTime } from "@/lib/formatters";
import { EmptyState, ErrorState, LoadingState, Modal, PageHeader, StatTile, StatusPill } from "@/components/nocturne/ui";
import { exportFile } from "@/lib/exports";

function byDay(entries: AuditLogEntry[]): [string, AuditLogEntry[]][] {
  const out = new Map<string, AuditLogEntry[]>();
  for (const e of entries) {
    const d = formatDate(e.created_at);
    out.set(d, [...(out.get(d) ?? []), e]);
  }
  return [...out.entries()];
}

export default function AuditPage() {
  return (
    <Suspense>
      <Audit />
    </Suspense>
  );
}

function Audit() {
  const params = useSearchParams();
  const { toast } = useUi();
  const [reportId, setReportId] = useState(params.get("reportId") ?? "");
  const [open, setOpen] = useState<AuditLogEntry | null>(null);
  const reports = useApi(() => api.listReports());
  const log = useApi(() => (reportId ? api.getAuditLog(reportId) : api.tenantAudit(300)), [reportId]);
  const verify = useApi(() => api.verifyAudit());
  const v = verify.data;
  const entries = log.data ?? [];
  const people = entries.filter((e) => e.actor !== "system").length;
  const rep = (reports.data ?? []).find((r) => r.id === reportId);

  return (
    <div className="flex max-w-[1440px] flex-col gap-6 px-4 pb-12 pt-8 sm:px-6">
      <PageHeader
        kicker="Govern"
        title="Audit trail"
        sub="Every action on your data, in order, with who did it. Entries are hash-chained: any later edit or deletion breaks the chain and is detected."
        actions={
          v ? (
            <button type="button" onClick={() => { verify.reload(); toast(v.intact ? `Verified ${v.entries} entries · chain intact` : `Chain broken at #${v.first_bad_seq}`, v.intact ? "ok" : "err"); }} className="tb-pill cursor-pointer !px-3 !py-1.5 !text-[13px]" style={{ color: v.intact ? "var(--ok)" : "var(--err)", background: v.intact ? "var(--okT)" : "var(--errT)" }}>
              {v.intact ? `Chain intact · ${v.entries.toLocaleString("en-GB")} entries` : `Chain broken at #${v.first_bad_seq}`}
            </button>
          ) : undefined
        }
      />
      <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(200px,1fr))" }}>
        <StatTile label="Chain integrity" value={v ? (v.intact ? "Intact" : "Broken") : "…"} color={v ? (v.intact ? "var(--ok)" : "var(--err)") : "var(--line2)"} icon={<ShieldCheck size={15} />} note={v ? `${v.entries.toLocaleString("en-GB")} entries verified` : "Verifying…"} />
        <StatTile label={reportId ? "Entries for this file" : "Entries shown"} value={entries.length.toLocaleString("en-GB")} color="var(--accent)" icon={<ArrowsClockwise size={15} />} note={reportId ? "Every recorded step for the selected file" : "Most recent organisation activity"} />
        <StatTile label="By people" value={people.toLocaleString("en-GB")} color="var(--accent)" icon={<User size={15} />} note="Decisions, confirmations, exports" />
        <StatTile label="By the system" value={(entries.length - people).toLocaleString("en-GB")} color="var(--med)" icon={<Robot size={15} />} note="Reads, validations, checks" />
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <label className="text-[13px]" style={{ color: "var(--muted)" }} htmlFor="audit-scope">Scope</label>
        <select id="audit-scope" className="tb-input !w-[320px] max-w-full" value={reportId} onChange={(e) => setReportId(e.target.value)}>
          <option value="">All activity</option>
          {(reports.data ?? []).map((r) => <option key={r.id} value={r.id}>{r.file_name}</option>)}
        </select>
        <button type="button" className="tb-btn tb-btn-ghost" onClick={() => { log.reload(); verify.reload(); }}><ArrowsClockwise />Refresh</button>
        <div className="flex-1" />
        {reportId && (
          <button type="button" className="tb-btn" onClick={() => void exportFile(api.exportAuditCsvUrl(reportId), `${rep?.file_name.replace(/\.\w+$/, "") ?? "report"}_audit`, toast)}>
            <DownloadSimple />
            Export
          </button>
        )}
      </div>
      <div className="tb-card overflow-hidden">
        {log.loading && !log.data ? (
          <div className="p-5"><LoadingState label="Loading audit trail" rows={8} /></div>
        ) : log.error && !log.data ? (
          <div className="p-5"><ErrorState title="The audit trail could not be loaded" message={log.error} onRetry={log.reload} /></div>
        ) : entries.length === 0 ? (
          <EmptyState icon={<ShieldCheck />} title="No activity recorded yet" body="Every upload, mapping, decision and export will appear here." />
        ) : (
          byDay(entries).map(([day, list]) => (
            <div key={day}>
              <div className="px-5 pb-1.5 pt-4 text-[11px] font-medium uppercase tracking-[.08em]" style={{ color: "var(--faint)" }}>{day}</div>
              {list.map((e) => {
                const d = describeAudit(e);
                const sys = e.actor === "system";
                return (
                  <button key={e.id} type="button" onClick={() => setOpen(e)} className="grid w-full cursor-pointer grid-cols-[64px_120px_minmax(0,1fr)_auto] items-center gap-4 px-5 py-2.5 text-left text-[13px] transition-colors hover:bg-[var(--accentTint)]" style={{ boxShadow: "0 1px 0 var(--line)" }}>
                    <span className="tnum font-medium">#{e.seq ?? "—"}</span>
                    <span className="flex items-center gap-1.5 truncate" style={{ color: sys ? "var(--med)" : "var(--accentText)" }}>
                      {sys ? <Robot size={14} /> : <User size={14} />}
                      {e.actor}
                    </span>
                    <span className="flex min-w-0 flex-col">
                      <span className="truncate">{d.title}</span>
                      {d.detail && <span className="truncate text-[12px]" style={{ color: "var(--muted)" }}>{d.detail}</span>}
                    </span>
                    <span className="tnum text-[12px]" style={{ color: "var(--faint)" }}>{new Date(e.created_at).toLocaleTimeString("en-IE", { hour: "2-digit", minute: "2-digit" })}</span>
                  </button>
                );
              })}
            </div>
          ))
        )}
      </div>
      <Modal open={!!open} onClose={() => setOpen(null)} kicker={`Audit entry #${open?.seq ?? ""}`} title={open ? describeAudit(open).title : ""} width={560} actions={<button className="tb-btn tb-btn-primary" onClick={() => setOpen(null)}>Close</button>}>
        {open && (
          <div className="tnum grid grid-cols-[minmax(84px,120px)_minmax(0,1fr)] [overflow-wrap:anywhere] gap-y-2 text-[13px]">
            <span>Time</span>
            <span style={{ color: "var(--text)" }}>{formatDateTime(open.created_at)}</span>
            <span>Actor</span>
            <span style={{ color: "var(--text)" }}>{open.actor}</span>
            <span>Action</span>
            <span style={{ color: "var(--text)" }}>{open.action_type}</span>
            <span>Object</span>
            <span style={{ color: "var(--text)" }}>{open.entity_type} · {open.entity_id}</span>
            {open.entry_hash && (
              <>
                <span>Entry hash</span>
                <span className="break-all" style={{ color: "var(--text)" }}>{open.entry_hash}</span>
              </>
            )}
            {open.report_id && (
              <>
                <span>Report</span>
                <Link href={`/reports/${open.report_id}`} style={{ color: "var(--accentText)" }}>Open report</Link>
              </>
            )}
            <span>Chain</span>
            <span>{v ? <StatusPill tone={v.intact ? "ok" : "err"}>{v.intact ? "Intact" : "Broken"}</StatusPill> : "…"}</span>
          </div>
        )}
      </Modal>
    </div>
  );
}
