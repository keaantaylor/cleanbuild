"use client";

import Link from "next/link";
import type { AuditLogEntry, Recommendation } from "@/lib/types";
import { describeAudit } from "@/lib/audit";
import { formatDateTime, timeAgo } from "@/lib/formatters";
import { StatusPill } from "./ui";
import { SEV } from "./status";

const TARGET_HREF: Record<string, (id: string) => string> = {
  MANDATORY_FIELD: (id) => `/exceptions?reportId=${id}&checkType=MANDATORY_FIELD`,
  ARITHMETIC: (id) => `/exceptions?reportId=${id}&checkType=ARITHMETIC`,
  DUPLICATE: (id) => `/duplicates?reportId=${id}`,
  MAPPING: (id) => `/reports/${id}#sheets`,
};

/** Recommended next actions — derived only from findings; each cites its evidence. */
export function Recommendations({ items, reportId, showFile }: { items: Recommendation[]; reportId?: string; showFile?: boolean }) {
  if (!items.length) return <p className="m-0 text-[13px]" style={{ color: "var(--muted)" }}>No actions recommended — nothing in the evidence needs attention.</p>;
  return (
    <ul className="m-0 flex list-none flex-col gap-3 p-0">
      {items.map((r) => {
        const rid = r.report_id ?? reportId;
        const href = r.target && rid ? TARGET_HREF[r.target]?.(rid) : undefined;
        return (
          <li key={`${rid}-${r.id}`} className="flex flex-col gap-1 rounded-md px-3.5 py-3" style={{ boxShadow: "inset 0 0 0 1px var(--line)" }}>
            <span className="flex flex-wrap items-center gap-2 text-[13.5px] font-medium">
              <StatusPill tone={SEV[r.severity]?.tone ?? "muted"}>{SEV[r.severity]?.label ?? r.severity}</StatusPill>
              {r.title}
              {href && (
                <Link href={href} className="ml-auto text-[12.5px] font-normal" style={{ color: "var(--accentText)" }}>
                  Review →
                </Link>
              )}
            </span>
            <span className="text-[12.5px]" style={{ color: "var(--muted)" }}>
              <b style={{ color: "var(--text)", fontWeight: 500 }}>Evidence:</b> {r.evidence}
            </span>
            <span className="text-[12.5px]" style={{ color: "var(--muted)" }}>
              <b style={{ color: "var(--text)", fontWeight: 500 }}>Next:</b> {r.action}
              {showFile && r.file_name ? ` · ${r.file_name}` : ""}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

const TONE_C: Record<string, string> = { good: "var(--ok)", warn: "var(--warn)", bad: "var(--err)", info: "var(--accentText)", neutral: "var(--faint)" };

export function ActivityFeed({ entries, showReportLinks = true }: { entries: AuditLogEntry[]; showReportLinks?: boolean }) {
  if (!entries.length) return <p className="m-0 text-[13px]" style={{ color: "var(--muted)" }}>No activity yet.</p>;
  return (
    <ol className="m-0 flex list-none flex-col gap-2.5 p-0">
      {entries.map((e) => {
        const d = describeAudit(e);
        return (
          <li key={e.id} className="grid grid-cols-[8px_1fr] gap-3 text-[12.5px] leading-[1.45]">
            <span className="mt-[6px] h-2 w-2 rounded-full" style={{ background: TONE_C[d.tone] ?? "var(--faint)" }} />
            <span className="flex min-w-0 flex-col">
              <span style={{ color: "var(--text)" }}>{d.title}</span>
              {d.detail && <span className="truncate" style={{ color: "var(--muted)" }}>{d.detail}</span>}
              <span className="tnum text-[11.5px]" style={{ color: "var(--faint)" }}>
                <time dateTime={e.created_at} title={formatDateTime(e.created_at)}>{timeAgo(e.created_at)}</time> · {e.actor}
                {showReportLinks && e.report_id && (
                  <>
                    {" · "}
                    <Link href={`/reports/${e.report_id}`} style={{ color: "var(--accentText)" }}>report</Link>
                  </>
                )}
                {e.seq !== undefined && ` · #${e.seq}`}
              </span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}
