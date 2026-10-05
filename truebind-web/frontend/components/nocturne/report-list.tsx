"use client";

import Link from "next/link";
import type { Report } from "@/lib/types";
import { formatNumber, timeAgo } from "@/lib/formatters";
import { StatusPill } from "./ui";
import { reportStatus } from "./status";

/** The shared files table: file, sender, rows, findings, status, received. */
export function ReportTable({ reports, detailed = false }: { reports: Report[]; detailed?: boolean }) {
  const cols = detailed ? "minmax(0,2.4fr) minmax(0,1.2fr) minmax(0,1fr) 72px 72px minmax(0,1.4fr) 96px" : "minmax(0,2.4fr) minmax(0,1.2fr) 72px minmax(0,1.4fr) 96px";
  return (
    <>
    {/* Phones: one stacked card per file, no sideways scrolling. */}
    <ul className={`m-0 list-none p-0 ${detailed ? "lg:hidden" : "md:hidden"}`}>
      {reports.map((r) => {
        const st = reportStatus(r);
        return (
          <li key={r.id} style={{ boxShadow: "0 1px 0 var(--line)" }}>
            <Link href={st.href} className="flex flex-col gap-1.5 px-4 py-3.5 active:bg-[var(--accentTint)]">
              <span className="flex items-start justify-between gap-3">
                <span className="min-w-0 break-words text-[14px] font-medium">{r.file_name}</span>
                <span className="tnum flex-none text-[12px]" style={{ color: "var(--faint)" }}>{timeAgo(r.created_at)}</span>
              </span>
              <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[12.5px]" style={{ color: "var(--muted)" }}>
                <StatusPill tone={st.tone}>{st.label}</StatusPill>
                <span>{r.sender || "No sender"}</span>
                {r.rows_total ? <span className="tnum">· {formatNumber(r.rows_total)} rows</span> : null}
                {detailed && r.status === "COMPLETE" && <span className="tnum" style={{ color: (r.issues_found ?? 0) > 0 ? "var(--warn)" : undefined }}>· {formatNumber(r.issues_found ?? 0)} findings</span>}
              </span>
            </Link>
          </li>
        );
      })}
    </ul>
    <div className={`hidden overflow-x-auto ${detailed ? "lg:block" : "md:block"}`}>
      <div style={{ minWidth: detailed ? 860 : 640 }}>
        <div className="grid gap-x-3.5 px-[18px] py-[11px] text-[11px] font-medium uppercase tracking-[.06em]" style={{ gridTemplateColumns: cols, color: "var(--faint)", boxShadow: "0 1px 0 var(--line)" }}>
          <span>File</span>
          <span>Sender</span>
          {detailed && <span>Programme</span>}
          <span className="text-right">Rows</span>
          {detailed && <span className="text-right">Findings</span>}
          <span>Status</span>
          <span className="text-right">Received</span>
        </div>
        {reports.map((r) => {
          const st = reportStatus(r);
          const ext = (r.file_kind || r.file_name.split(".").pop() || "").toUpperCase();
          return (
            <Link key={r.id} href={st.href} className="grid items-center gap-x-3.5 px-[18px] py-[13px] text-[13px] transition-colors hover:bg-[var(--accentTint)]" style={{ gridTemplateColumns: cols, boxShadow: "0 1px 0 var(--line)" }}>
              <span className="flex min-w-0 items-center gap-2.5">
                <span className="flex-none rounded px-1 py-[3px] text-[9px] font-semibold" style={{ color: "oklch(0.55 0.11 150)", boxShadow: "inset 0 0 0 1px var(--line2)" }}>{ext || "FILE"}</span>
                <span className="truncate font-medium">{r.file_name}</span>
              </span>
              <span className="truncate" style={{ color: "var(--muted)" }}>{r.sender || "-"}</span>
              {detailed && <span className="truncate" style={{ color: "var(--muted)" }}>{r.programme || "-"}</span>}
              <span className="tnum text-right">{r.rows_total ? formatNumber(r.rows_total) : "-"}</span>
              {detailed && <span className="tnum text-right" style={{ color: (r.issues_found ?? 0) > 0 ? "var(--warn)" : "var(--text)" }}>{r.status === "COMPLETE" ? formatNumber(r.issues_found ?? 0) : "-"}</span>}
              <span className="justify-self-start">
                <StatusPill tone={st.tone}>{st.label}</StatusPill>
              </span>
              <span className="tnum text-right" style={{ color: "var(--faint)" }}>{timeAgo(r.created_at)}</span>
            </Link>
          );
        })}
      </div>
    </div>
    </>
  );
}
