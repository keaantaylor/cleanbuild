"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowRight, CaretRight, CheckCircle, ShieldCheck, UploadSimple } from "@phosphor-icons/react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { formatDate, formatDuration, formatNumber, timeAgo } from "@/lib/formatters";
import type { Obligation, Report, WorkItem } from "@/lib/types";
import { EmptyState, ErrorState, LoadingState, StatusPill } from "@/components/nocturne/ui";
import { ActivityFeed } from "@/components/nocturne/ops";
import { SEV, reportStatus } from "@/components/nocturne/status";

const IN_FLIGHT = ["UPLOADED", "QUEUED", "INGESTING", "PROCESSING"];

/** Earliest open follow-up deadline per file: the only due dates the API records. */
function dueDates(obligations: Obligation[] | null): Map<string, { date: string; overdue: boolean }> {
  const out = new Map<string, { date: string; overdue: boolean }>();
  for (const o of obligations ?? []) {
    if (o.status === "RESOLVED" || !o.deadline) continue;
    const cur = out.get(o.report_id);
    if (!cur || o.deadline < cur.date) out.set(o.report_id, { date: o.deadline, overdue: o.status === "OVERDUE" || new Date(o.deadline) < new Date() });
  }
  return out;
}

export default function OverviewPage() {
  const { data: o, error, loading, reload } = useApi(() => api.overview(), [], (d) => (d && d.reports.in_flight > 0 ? 3_000 : 20_000));
  const queue = useApi(() => api.workQueue(), [], 20_000);
  const obligations = useApi(() => api.listObligations(), [], 60_000);
  const today = new Date().toLocaleDateString("en-IE", { weekday: "long", day: "numeric", month: "long" });

  if (loading && !o)
    return (
      <div className="px-4 pt-8 sm:px-6">
        <LoadingState label="Loading overview" rows={8} />
      </div>
    );
  if (error && !o)
    return (
      <div className="px-4 pt-8 sm:px-6">
        <ErrorState title="The overview could not be loaded" message={error} onRetry={reload} />
      </div>
    );
  if (!o) return null;

  const serious = (o.findings.open_by_severity?.CRITICAL ?? 0) + (o.findings.open_by_severity?.HIGH ?? 0);
  const empty = o.reports.total === 0;
  const inFlight = o.in_flight_reports ?? o.latest_reports.filter((r) => IN_FLIGHT.includes(r.status));
  const items = queue.data?.items ?? [];
  const waiting = queue.data?.total ?? items.length;
  const due = dueDates(obligations.data);

  return (
    <div className="flex max-w-[1440px] flex-col gap-5 px-4 pb-10 pt-6 sm:px-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-col gap-1">
          <span className="kicker">{today}</span>
          <h1 className="m-0 text-[28px] font-medium tracking-[-0.02em]">
            {empty ? "Welcome to TrueBind" : waiting ? `${formatNumber(waiting)} thing${waiting === 1 ? "" : "s"} need${waiting === 1 ? "s" : ""} you today` : "You’re up to date"}
          </h1>
        </div>
        {!empty && (
          <Link href="/upload" className="tb-btn">
            <UploadSimple />
            Upload a file
          </Link>
        )}
      </div>

      {empty ? (
        <div className="tb-card">
          <EmptyState
            icon={<UploadSimple />}
            title="Start by uploading a bordereau"
            body="Upload a claims bordereau (.xlsx, .xlsm, .xls or .csv). TrueBind reads every sheet, suggests how the columns map, checks every row and tells you exactly what needs attention."
            action={<Link href="/upload" className="tb-btn tb-btn-solid">Upload your first file</Link>}
          />
        </div>
      ) : (
        <>
          <NextStep item={items[0]} loading={!queue.data && !queue.error} />

          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Figure label="Waiting for you" value={waiting} note={waiting ? "decisions and fixes in your work queue" : "nothing to decide"} href="/todo" tone={waiting ? "warn" : "ok"} />
            <Figure label="Serious problems" value={serious} note={serious ? "critical or high findings still open" : "none open"} href="/exceptions" tone={serious ? "err" : "ok"} />
            <Figure label="Files this week" value={o.received.last_7d} note={`${formatNumber(o.received.last_24h)} since yesterday`} href="/inbox" />
            <Figure
              label="Being checked now"
              value={inFlight.length}
              note={o.processing.worker_available ? (inFlight.length ? "results appear automatically" : "checking engine ready") : "checking engine offline"}
              href="/inbox"
              tone={o.processing.worker_available ? undefined : "err"}
            />
          </div>

          <div className="grid grid-cols-[minmax(0,1fr)] gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(300px,360px)]">
            <section className="flex min-w-0 flex-col gap-2.5">
              <div className="flex items-baseline justify-between">
                <h2 className="m-0 text-[15px] font-medium">Your files</h2>
                <Link href="/inbox" className="text-[12.5px]" style={{ color: "var(--accentText)" }}>All files →</Link>
              </div>
              <FilesTable reports={o.latest_reports.slice(0, 6)} due={due} />
            </section>
            <aside className="flex flex-col gap-3">
              <AlsoWaiting items={items.slice(1, 4)} more={Math.max(0, waiting - 4)} />
              <Collapsible title="Processing">
                <dl className="tnum m-0 grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-1.5 text-[13px]">
                  <dt style={{ color: "var(--muted)" }}>Jobs in the last 24 hours</dt>
                  <dd className="m-0 text-right">{formatNumber(o.processing.jobs_24h)}</dd>
                  <dt style={{ color: "var(--muted)" }}>Failed in the last 24 hours</dt>
                  <dd className="m-0 text-right" style={{ color: o.processing.failed_24h ? "var(--err)" : undefined }}>{formatNumber(o.processing.failed_24h)}</dd>
                  <dt style={{ color: "var(--muted)" }}>Typical time per job</dt>
                  <dd className="m-0 text-right">{formatDuration(o.processing.median_job_s)}</dd>
                  <dt style={{ color: "var(--muted)" }}>Files with a check not assessed</dt>
                  <dd className="m-0 text-right">{formatNumber(o.findings.reports_with_checks_not_assessed ?? 0)}</dd>
                </dl>
              </Collapsible>
              <Collapsible title="Sender quality">
                <SenderQuality />
              </Collapsible>
              <Collapsible
                title="Recent activity"
                extra={
                  <Link href="/audit" className="flex items-center gap-1 text-[11.5px]" style={{ color: "var(--ok)" }}>
                    <ShieldCheck />
                    Audit trail
                  </Link>
                }
              >
                <ActivityFeed entries={o.activity.slice(0, 6)} />
              </Collapsible>
            </aside>
          </div>
        </>
      )}
    </div>
  );
}

/** The single most urgent thing, with one clear button. */
function NextStep({ item, loading }: { item?: WorkItem; loading: boolean }) {
  if (loading) return <div className="tb-card p-5"><LoadingState label="Finding your next step" rows={2} /></div>;
  if (!item)
    return (
      <div className="tb-card flex flex-wrap items-center gap-4 p-5">
        <span className="grid h-10 w-10 flex-none place-items-center rounded-full text-[20px]" style={{ background: "var(--okT)", color: "var(--ok)" }}>
          <CheckCircle />
        </span>
        <div className="flex min-w-0 flex-1 flex-col">
          <span className="text-[15px] font-medium">Nothing needs a decision right now</span>
          <span className="text-[13px]" style={{ color: "var(--muted)" }}>New files are checked automatically. Upload one whenever a sender delivers.</span>
        </div>
        <Link href="/upload" className="tb-btn tb-btn-solid">Upload a file</Link>
      </div>
    );
  const sev = SEV[item.priority] ?? SEV.MEDIUM;
  return (
    <div className="tb-card relative flex flex-wrap items-center gap-4 overflow-hidden p-5" style={{ boxShadow: `var(--shadow), inset 3px 0 0 ${sev.c}` }}>
      <div className="flex min-w-0 flex-1 basis-[320px] flex-col gap-1">
        <span className="flex items-center gap-2 text-[12px] font-medium uppercase tracking-[.08em]" style={{ color: sev.c }}>
          Start here
          <StatusPill tone={sev.tone}>{sev.label}</StatusPill>
        </span>
        <span className="text-[17px] font-medium">{item.title}</span>
        <span className="text-[13px]" style={{ color: "var(--muted)" }}>
          {item.detail}
          {item.file_name && !item.title.includes(item.file_name) ? ` · ${item.file_name}` : ""}
        </span>
      </div>
      {item.href && (
        <Link href={item.href} className="tb-btn tb-btn-solid w-full sm:w-auto">
          Deal with it now
          <ArrowRight />
        </Link>
      )}
    </div>
  );
}

function Figure({ label, value, note, href, tone }: { label: string; value: number; note: string; href: string; tone?: "ok" | "warn" | "err" }) {
  const c = tone ? `var(--${tone})` : "var(--text)";
  return (
    <Link href={href} className="tb-card group flex flex-col gap-0.5 px-4 py-3.5 transition-colors hover:bg-[var(--accentTint)]">
      <span className="text-[12.5px]" style={{ color: "var(--muted)" }}>{label}</span>
      <span className="tnum text-[26px] font-medium leading-[1.2] tracking-[-0.02em]" style={{ color: value ? c : "var(--text)" }}>{formatNumber(value)}</span>
      <span className="text-[12px] leading-[1.35]" style={{ color: "var(--faint)" }}>{note}</span>
    </Link>
  );
}

/** File, sender, status, due date - nothing else. */
function FilesTable({ reports, due }: { reports: Report[]; due: Map<string, { date: string; overdue: boolean }> }) {
  if (!reports.length) return <div className="tb-card px-5 py-4 text-[13px]" style={{ color: "var(--muted)" }}>No files yet.</div>;
  const Due = ({ id }: { id: string }) => {
    const d = due.get(id);
    return d ? <span style={{ color: d.overdue ? "var(--err)" : "var(--text)" }}>{d.overdue ? "Overdue · " : ""}{formatDate(d.date)}</span> : <span style={{ color: "var(--faint)" }}>No deadline</span>;
  };
  return (
    <div className="tb-card overflow-hidden">
      <ul className="m-0 list-none p-0 md:hidden">
        {reports.slice(0, 4).map((r) => {
          const st = reportStatus(r);
          return (
            <li key={r.id} style={{ boxShadow: "0 1px 0 var(--line)" }}>
              <Link href={st.href} className="flex flex-col gap-1.5 px-4 py-3 active:bg-[var(--accentTint)]">
                <span className="break-words text-[14px] font-medium">{r.file_name}</span>
                <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[12.5px]" style={{ color: "var(--muted)" }}>
                  <StatusPill tone={st.tone}>{st.label}</StatusPill>
                  <span>{r.sender || "No sender"}</span>
                  <span>· Due <Due id={r.id} /></span>
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
      <table className="hidden w-full border-collapse text-[13px] md:table">
        <thead>
          <tr className="text-left text-[11px] uppercase tracking-[.06em]" style={{ color: "var(--faint)", boxShadow: "0 1px 0 var(--line)" }}>
            <th className="px-4 py-2.5 font-medium">File</th>
            <th className="px-4 py-2.5 font-medium">Sender</th>
            <th className="px-4 py-2.5 font-medium">Status</th>
            <th className="px-4 py-2.5 font-medium">Due</th>
          </tr>
        </thead>
        <tbody>
          {reports.map((r, i) => {
            const st = reportStatus(r);
            return (
              // Short screens (e.g. 1366×768) show four rows so the page still fits without scrolling.
              <tr key={r.id} className={`relative transition-colors hover:bg-[var(--accentTint)] ${i >= 4 ? "[@media(max-height:860px)]:hidden" : ""}`} style={{ boxShadow: "0 1px 0 var(--line)" }}>
                <td className="max-w-0 px-4 py-2.5">
                  <Link href={st.href} className="block truncate font-medium after:absolute after:inset-0">{r.file_name}</Link>
                  <span className="block text-[12px]" style={{ color: "var(--faint)" }}>received {timeAgo(r.created_at)}</span>
                </td>
                <td className="w-[22%] truncate px-4 py-2.5" style={{ color: "var(--muted)" }}>{r.sender || "-"}</td>
                <td className="w-[1%] whitespace-nowrap px-4 py-2.5"><StatusPill tone={st.tone}>{st.label}</StatusPill></td>
                <td className="tnum w-[1%] whitespace-nowrap px-4 py-2.5"><Due id={r.id} /></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function AlsoWaiting({ items, more }: { items: WorkItem[]; more: number }) {
  if (!items.length) return null;
  return (
    <section className="tb-card flex flex-col overflow-hidden">
      <span className="px-4 pb-1.5 pt-3 text-[13.5px] font-medium">Also waiting</span>
      {items.map((it, i) => {
        const body = (
          <>
            <span className="h-2 w-2 flex-none rounded-full" style={{ background: SEV[it.priority]?.c ?? "var(--muted)" }} />
            <span className="min-w-0 flex-1 truncate text-[13px]">{it.title}</span>
            <CaretRight size={13} style={{ color: "var(--faint)" }} />
          </>
        );
        const cls = "flex items-center gap-2.5 px-4 py-2.5 transition-colors hover:bg-[var(--accentTint)]";
        return it.href ? (
          <Link key={i} href={it.href} className={cls} style={{ boxShadow: "0 -1px 0 var(--line)" }}>{body}</Link>
        ) : (
          <div key={i} className={cls} style={{ boxShadow: "0 -1px 0 var(--line)" }}>{body}</div>
        );
      })}
      {more > 0 && (
        <Link href="/todo" className="px-4 py-2.5 text-[12.5px]" style={{ color: "var(--accentText)", boxShadow: "0 -1px 0 var(--line)" }}>
          {formatNumber(more)} more in the work queue →
        </Link>
      )}
    </section>
  );
}

function Collapsible({ title, extra, children }: { title: string; extra?: React.ReactNode; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <section className="tb-card overflow-hidden">
      <div className="flex items-center gap-2 px-4">
        <button type="button" className="flex flex-1 cursor-pointer items-center gap-2 py-3 text-left text-[13.5px] font-medium" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
          <CaretRight size={12} className="transition-transform" style={{ transform: open ? "rotate(90deg)" : "none", color: "var(--faint)" }} />
          {title}
        </button>
        {extra}
      </div>
      {open && <div className="anim-fade px-4 pb-4">{children}</div>}
    </section>
  );
}

/** Mounted only when opened, so the scorecard is fetched on demand. */
function SenderQuality() {
  const { data, error, reload } = useApi(() => api.getScorecard(), []);
  if (error) return <ErrorState title="Sender quality could not be loaded" message={error} onRetry={reload} />;
  if (!data) return <LoadingState label="Loading sender quality" rows={3} />;
  if (!data.senders.length) return <span className="text-[12.5px]" style={{ color: "var(--muted)" }}>Scores appear once files from a named sender have been checked.</span>;
  return (
    <div className="flex flex-col gap-2">
      {data.senders.slice(0, 5).map((s) => (
        <div key={s.sender} className="flex items-center justify-between gap-3 text-[13px]">
          <span className="min-w-0 truncate">{s.sender}</span>
          <span className="tnum flex-none" style={{ color: s.latest_score == null ? "var(--faint)" : s.latest_score >= 85 ? "var(--ok)" : s.latest_score >= 65 ? "var(--warn)" : "var(--err)" }}>
            {s.latest_score == null ? "not scored" : `${s.latest_score}/100`}
          </span>
        </div>
      ))}
      <Link href="/scorecard" className="text-[12.5px]" style={{ color: "var(--accentText)" }}>Full scorecard →</Link>
    </div>
  );
}
