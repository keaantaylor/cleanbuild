"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { AddressBook, ArrowLeft, MagnifyingGlass } from "@phosphor-icons/react";
import { useMe } from "@/components/auth/AuthGate";
import { EmptyState, ErrorState, LoadingState, PageHeader, StatusPill } from "@/components/nocturne/ui";
import { reportStatus } from "@/components/nocturne/status";
import { api, ApiError } from "@/lib/api";
import { formatNumber, timeAgo } from "@/lib/formatters";
import type { CounterpartyProfile, Report, RuleSuggestion } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { useUi } from "@/lib/ui";

export default function SendersPage() {
  return (
    <Suspense>
      <Senders />
    </Suspense>
  );
}

/** What TrueBind has learned about each sender: layouts, recurring errors,
 * known exceptions and approved corrections, plus reusable rules to approve. */
function Senders() {
  const sender = useSearchParams().get("sender");
  return (
    <div className="flex max-w-[1440px] flex-col gap-6 px-4 pb-12 pt-8 sm:px-6">
      {sender ? <Profile sender={sender} /> : <List />}
    </div>
  );
}

function List() {
  const router = useRouter();
  const { data, error, reload } = useApi(() => api.counterparties(), []);
  const [q, setQ] = useState("");
  const items = useMemo(() => (data?.items ?? []).filter((c) => c.sender.toLowerCase().includes(q.toLowerCase())), [data, q]);
  return (
    <>
      <PageHeader kicker="Investigate" title="Senders" sub="Every MGA, TPA or coverholder that has sent you a file. TrueBind remembers their layouts and recurring errors, and reuses confirmed mappings." />
      <RuleSuggestions />
      <div className="relative max-w-[360px]">
        <MagnifyingGlass className="absolute left-2.5 top-1/2 -translate-y-1/2" style={{ color: "var(--faint)" }} aria-hidden />
        <input className="tb-input !pl-8" placeholder="Search senders" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search senders" />
      </div>
      <div className="tb-card overflow-hidden">
        {error && !data ? (
          <div className="p-4"><ErrorState title="Senders could not be loaded" message={error} onRetry={reload} /></div>
        ) : !data ? (
          <div className="p-4"><LoadingState label="Loading senders" rows={5} /></div>
        ) : data.items.length === 0 ? (
          <EmptyState icon={<AddressBook />} title="No senders yet" body="Add a sender when you upload a file and it appears here, with everything TrueBind learns from it." />
        ) : items.length === 0 ? (
          <p className="m-0 px-4 py-6 text-center text-[13px]" style={{ color: "var(--faint)" }}>No sender matches “{q}”.</p>
        ) : (
          <table className="w-full border-collapse text-[13.5px]">
            <thead>
              <tr style={{ color: "var(--muted)" }}>
                <th className="px-4 py-2.5 text-left text-[12.5px] font-normal" style={{ boxShadow: "0 1px 0 var(--line)" }}>Sender</th>
                <th className="px-4 py-2.5 text-right text-[12.5px] font-normal" style={{ boxShadow: "0 1px 0 var(--line)" }}>Files</th>
                <th className="px-4 py-2.5 text-right text-[12.5px] font-normal" style={{ boxShadow: "0 1px 0 var(--line)" }}>Last file</th>
              </tr>
            </thead>
            <tbody>
              {items.map((c) => (
                <tr key={c.sender} className="cursor-pointer transition-colors hover:bg-[var(--accentTint)]" style={{ boxShadow: "0 1px 0 var(--line)" }} onClick={() => router.push(`/senders?sender=${encodeURIComponent(c.sender)}`)}>
                  <td className="px-4 py-3">
                    <Link href={`/senders?sender=${encodeURIComponent(c.sender)}`} className="font-medium">{c.sender}</Link>
                  </td>
                  <td className="tnum px-4 py-3 text-right">{formatNumber(c.submissions)}</td>
                  <td className="px-4 py-3 text-right" style={{ color: "var(--muted)" }}>{timeAgo(c.last_received_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}

/** Corrections a person has approved 3+ times, offered as reusable rules. Only a person creates one. */
function RuleSuggestions({ sender }: { sender?: string }) {
  const me = useMe();
  const { toast } = useUi();
  const { data, reload } = useApi(() => api.ruleSuggestions(), []);
  const [busy, setBusy] = useState<number | null>(null);
  const items = (data?.items ?? []).filter((s) => !sender || !s.sender || s.sender.toLowerCase() === sender.toLowerCase());
  if (!me?.can_write || items.length === 0) return null;
  const approve = async (s: RuleSuggestion, i: number) => {
    setBusy(i);
    try {
      await api.approveRule({ field_code: s.field_code, rule: s.rule, match_value: s.match_value, replace_value: s.replace_value });
      toast("Rule approved. It now applies under policy and is recorded in the audit trail.", "ok");
      reload();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "The rule could not be approved.", "err");
    } finally {
      setBusy(null);
    }
  };
  return (
    <section className="tb-card flex flex-col gap-3 p-4 sm:p-5">
      <h2 className="m-0 text-[15px] font-medium">Suggested reusable rules</h2>
      <ul className="m-0 flex list-none flex-col gap-2 p-0">
        {items.map((s, i) => (
          <li key={i} className="flex flex-wrap items-center justify-between gap-3 rounded-md p-3" style={{ boxShadow: "inset 0 0 0 1px var(--line)" }}>
            <span className="flex min-w-0 flex-col gap-0.5 text-[13.5px]">
              <span><span className="mono">{s.match_value ?? "(blank)"}</span> → <span className="mono">{s.replace_value ?? "(blank)"}</span>{s.field_code ? <span style={{ color: "var(--muted)" }}> in {s.field_code}</span> : null}</span>
              <span className="text-[12.5px]" style={{ color: "var(--muted)" }}>{s.prompt}</span>
            </span>
            <button type="button" className="tb-btn tb-btn-primary" disabled={busy === i} onClick={() => approve(s, i)}>Approve rule</button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Profile({ sender }: { sender: string }) {
  const { data, error, reload } = useApi(() => api.counterpartyProfile(sender), [sender]);
  const reports = useApi(() => api.listReports(), []);
  const byId = useMemo(() => new Map((reports.data ?? []).map((r) => [r.id, r] as [string, Report])), [reports.data]);
  return (
    <>
      <Link href="/senders" className="flex w-fit items-center gap-1.5 text-[13px]" style={{ color: "var(--muted)" }}>
        <ArrowLeft size={14} /> All senders
      </Link>
      <PageHeader kicker="Investigate" title={sender} sub="What TrueBind has learned from this sender's files. Reused automatically: confirmed mappings for the same layout and approved rules." />
      {error && !data ? (
        <ErrorState title="This sender could not be loaded" message={error} onRetry={reload} />
      ) : !data ? (
        <LoadingState label="Loading the sender profile" rows={8} />
      ) : (
        <ProfileBody p={data} byId={byId} sender={sender} />
      )}
    </>
  );
}

function Card({ title, empty, children, count }: { title: string; empty: string; count: number; children: React.ReactNode }) {
  return (
    <section className="tb-card flex flex-col gap-3 p-4 sm:p-5">
      <h2 className="m-0 flex items-baseline gap-2 text-[15px] font-medium">
        {title}
        <span className="tnum text-[12.5px] font-normal" style={{ color: "var(--faint)" }}>{formatNumber(count)}</span>
      </h2>
      {count === 0 ? <p className="m-0 text-[13px]" style={{ color: "var(--muted)" }}>{empty}</p> : children}
    </section>
  );
}

function ProfileBody({ p, byId, sender }: { p: CounterpartyProfile; byId: Map<string, Report>; sender: string }) {
  const row = "flex items-baseline justify-between gap-3 py-2 text-[13.5px]";
  const line = { boxShadow: "0 1px 0 var(--line)" };
  return (
    <div className="flex flex-col gap-4">
      <RuleSuggestions sender={sender} />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Files received" count={p.submissions.length} empty="No files yet.">
          <ul className="m-0 list-none p-0">
            {p.submissions.slice(0, 12).map((s) => {
              const r = byId.get(s.report_id);
              const st = r ? reportStatus(r) : null;
              return (
                <li key={s.report_id} className={row} style={line}>
                  <Link href={`/reports/${s.report_id}`} className="min-w-0 truncate font-medium">{s.file_name}</Link>
                  <span className="flex flex-none items-center gap-2 text-[12.5px]" style={{ color: "var(--muted)" }}>
                    {st && <StatusPill tone={st.tone}>{st.label}</StatusPill>}
                    {timeAgo(s.received_at)}
                  </span>
                </li>
              );
            })}
          </ul>
        </Card>
        <Card title="Recurring errors" count={p.recurring_errors.length} empty="Nothing has recurred across this sender's files.">
          <ul className="m-0 list-none p-0">
            {p.recurring_errors.map((e) => (
              <li key={e.rule} className={row} style={line}>
                <span className="mono">{e.rule}</span>
                <span className="tnum" style={{ color: "var(--muted)" }}>{formatNumber(e.findings)} {e.findings === 1 ? "finding" : "findings"}</span>
              </li>
            ))}
          </ul>
        </Card>
        <Card title="Layouts seen" count={p.structures.length} empty="No layouts recorded yet.">
          <ul className="m-0 list-none p-0">
            {p.structures.map((s, i) => (
              <li key={i} className="flex flex-col gap-1 py-2 text-[13px]" style={line}>
                <span className="font-medium">{s.sheet} <span className="tnum font-normal" style={{ color: "var(--muted)" }}>· seen {s.seen}×</span></span>
                <span className="mono break-words text-[12px]" style={{ color: "var(--muted)" }}>{s.headers.slice(0, 12).join(" · ")}{s.headers.length > 12 ? " …" : ""}</span>
              </li>
            ))}
          </ul>
        </Card>
        <Card title="Known exceptions" count={p.known_exceptions.length} empty="No values accepted as reported for this sender.">
          <ul className="m-0 list-none p-0">
            {p.known_exceptions.slice(0, 15).map((k, i) => (
              <li key={i} className={row} style={line}>
                <span><span className="mono">{k.rule}</span>{k.cell ? <span style={{ color: "var(--muted)" }}> · {k.cell}</span> : null}</span>
                <span className="truncate text-[12.5px]" style={{ color: "var(--muted)" }}>{k.reason}</span>
              </li>
            ))}
          </ul>
        </Card>
        <Card title="Approved corrections" count={p.approved_corrections.length} empty="No corrections approved for this sender yet.">
          <ul className="m-0 list-none p-0">
            {p.approved_corrections.slice(0, 15).map((c, i) => (
              <li key={i} className={row} style={line}>
                <span><span className="mono">{c.before ?? "(blank)"}</span> → <span className="mono">{c.after ?? "(blank)"}</span></span>
                <span className="tnum text-[12.5px]" style={{ color: "var(--muted)" }}>{c.times}×</span>
              </li>
            ))}
          </ul>
        </Card>
        <Card title="Reusable rules" count={p.approved_rules.length} empty="No reusable rules approved yet.">
          <ul className="m-0 list-none p-0">
            {p.approved_rules.map((r) => (
              <li key={r.id} className={row} style={line}>
                <span><span className="mono">{r.match_value ?? "(blank)"}</span> → <span className="mono">{r.replace_value ?? "(blank)"}</span>{r.field_code ? <span style={{ color: "var(--muted)" }}> in {r.field_code}</span> : null}</span>
                <span className="tnum text-[12.5px]" style={{ color: "var(--muted)" }}>applied {formatNumber(r.applied)}×</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
      {p.reporting_periods.length > 0 && (
        <p className="m-0 text-[13px]" style={{ color: "var(--muted)" }}>Reporting periods seen: {p.reporting_periods.join(", ")}</p>
      )}
    </div>
  );
}
