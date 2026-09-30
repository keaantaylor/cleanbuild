"use client";

import Link from "next/link";
import { Suspense, useState } from "react";
import { CalendarBlank, CheckCircle, Copy, MagnifyingGlass, Pulse } from "@phosphor-icons/react";
import { api, ApiError } from "@/lib/api";
import type { DuplicatePair } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { useUi } from "@/lib/ui";
import { findingGuide } from "@/lib/findings";
import { formatDate, formatMoney, formatNumber } from "@/lib/formatters";
import { EmptyState, ErrorState, LoadingState, PageHeader, StatTile, StatusPill } from "@/components/nocturne/ui";
import { ReportPicker, useSelectedReport } from "@/components/nocturne/select-report";

type Row = Record<string, unknown>;
const FIELDS: { key: string; label: string; money?: boolean; date?: boolean }[] = [
  { key: "claim_reference", label: "claim_reference" },
  { key: "insured_name", label: "insured_name" },
  { key: "reporting_period", label: "reporting_period" },
  { key: "date_of_loss", label: "date_of_loss", date: true },
  { key: "currency", label: "currency" },
  { key: "paid_amount", label: "paid_to_date", money: true },
  { key: "reserve_amount", label: "reserve", money: true },
  { key: "incurred_amount", label: "total_incurred", money: true },
];
const REVIEW_LABEL: Record<string, string> = { not_duplicate: "Not a duplicate", flagged_for_sender: "Flagged for sender", confirmed_duplicate: "Confirmed duplicate" };
const norm = (v: unknown) => String(v ?? "").trim().toLowerCase();
function show(row: Row, f: (typeof FIELDS)[number]) {
  const v = row[f.key];
  if (v === null || v === undefined || v === "") return "";
  if (f.money) return formatMoney(v as number, (row.currency as string) ?? "");
  if (f.date) return formatDate(v as string);
  return String(v);
}

export default function DuplicatesPage() {
  return (
    <Suspense>
      <Duplicates />
    </Suspense>
  );
}

function Duplicates() {
  const { toast } = useUi();
  const { reportId, report, reports, loading: rl, error: rerr, reload: rreload, select } = useSelectedReport();
  const [tab, setTab] = useState("exact_duplicate");
  const [sel, setSel] = useState<string | null>(null);
  const pairs = useApi(() => (reportId ? api.listDuplicates(reportId) : Promise.resolve([] as DuplicatePair[])), [reportId]);
  const summary = useApi(() => (reportId ? api.getReportSummary(reportId) : Promise.resolve(null)), [reportId]);

  if (rl) return <div className="px-4 pt-8 sm:px-9"><LoadingState label="Loading duplicates" rows={8} /></div>;
  if (rerr) return <div className="px-4 pt-8 sm:px-9"><ErrorState title="Reports could not be loaded" message={rerr} onRetry={rreload} /></div>;
  if (!reportId)
    return (
      <div className="flex max-w-[1440px] flex-col gap-6 px-4 pb-12 pt-8 sm:px-9">
        <PageHeader kicker="Investigate" title="Duplicate intelligence" />
        <div className="tb-card"><EmptyState icon={<Copy />} title="No completed reports yet" body="Duplicates are found when a bordereau is processed." action={<Link href="/upload" className="tb-btn tb-btn-primary">Upload a bordereau</Link>} /></div>
      </div>
    );

  const all = pairs.data ?? [];
  const by = (t: string) => all.filter((p) => p.match_type === t);
  const open = (t: string) => by(t).filter((p) => !p.review_status);
  const reviewed = all.filter((p) => p.review_status === "confirmed_duplicate" || p.review_status === "flagged_for_sender");
  const dismissed = all.filter((p) => p.review_status === "not_duplicate");
  const s = summary.data;
  const current = tab === "reviewed" ? reviewed : tab === "dismissed" ? dismissed : tab === "development" ? [] : open(tab);
  const pair = current.find((p) => p.validation_result_id === sel) ?? current[0];

  async function review(status: string) {
    if (!pair || !reportId) return;
    try {
      await api.reviewDuplicate(reportId, pair.validation_result_id, status);
      toast(`${REVIEW_LABEL[status]} · recorded in the audit trail. Nothing is merged or removed.`, "ok");
      setSel(null);
      pairs.reload();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Could not record the decision.", "err");
    }
  }

  const TABS: [string, string, number][] = [
    ["exact_duplicate", "Exact", open("exact_duplicate").length],
    ["probable_duplicate", "Probable", open("probable_duplicate").length],
    ["repeat_period_unknown", "Needs period", open("repeat_period_unknown").length],
    ["development", "Development", s?.development_pairs ?? 0],
    ["reviewed", "Reviewed", reviewed.length],
    ["dismissed", "Dismissed", dismissed.length],
  ];

  return (
    <div className="flex max-w-[1440px] flex-col gap-6 px-4 pb-12 pt-8 sm:px-9">
      <PageHeader
        kicker="Investigate"
        title="Duplicate intelligence"
        sub="Exact resubmissions, probable duplicates and repeats TrueBind cannot classify — kept separate from normal claim development. Nothing is ever merged or removed automatically."
        actions={<ReportPicker report={report} reports={reports} onSelect={(id) => { select(id); setSel(null); }} />}
      />
      <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(200px,1fr))" }}>
        <StatTile label="Exact resubmissions" value={formatNumber(by("exact_duplicate").length)} color="var(--warn)" icon={<Copy size={15} />} active={tab === "exact_duplicate"} onClick={() => { setTab("exact_duplicate"); setSel(null); }} note={`${open("exact_duplicate").length} undecided`} />
        <StatTile label="Probable duplicates" value={formatNumber(by("probable_duplicate").length)} color="var(--accent)" icon={<MagnifyingGlass size={15} />} active={tab === "probable_duplicate"} onClick={() => { setTab("probable_duplicate"); setSel(null); }} note={s?.probable_duplicates === null ? "Check not run for this report" : `${open("probable_duplicate").length} undecided`} />
        <StatTile label="Need a reporting period" value={formatNumber(by("repeat_period_unknown").length)} color="var(--line2)" icon={<CalendarBlank size={15} />} active={tab === "repeat_period_unknown"} onClick={() => { setTab("repeat_period_unknown"); setSel(null); }} note="Can’t be classified yet" />
        <StatTile label="Claim development" value={formatNumber(s?.development_pairs ?? 0)} color="var(--ok)" icon={<Pulse size={15} />} active={tab === "development"} onClick={() => { setTab("development"); setSel(null); }} note="Movement — not duplicates" />
      </div>
      <div className="flex flex-wrap gap-0.5 self-start rounded-[9px] p-[3px]" style={{ boxShadow: "inset 0 0 0 1px var(--line2)" }} role="tablist">
        {TABS.map(([k, l, n]) => (
          <button key={k} type="button" role="tab" aria-selected={tab === k} onClick={() => { setTab(k); setSel(null); }} className="flex cursor-pointer items-center gap-1.5 rounded-[7px] px-3 py-1.5 text-[13px]" style={{ background: tab === k ? "var(--accentTint)" : "transparent", color: tab === k ? "var(--text)" : "var(--muted)" }}>
            {l}
            <span className="tnum text-[11.5px]" style={{ color: "var(--faint)" }}>{formatNumber(n)}</span>
          </button>
        ))}
      </div>

      {tab === "development" ? (
        <Development reportId={reportId} refs={s?.development_refs ?? []} />
      ) : pairs.error && !pairs.data ? (
        <ErrorState title="Duplicates could not be loaded" message={pairs.error} onRetry={pairs.reload} />
      ) : !pairs.data ? (
        <LoadingState label="Loading duplicate pairs" rows={6} />
      ) : current.length === 0 ? (
        <div className="tb-card">
          <EmptyState icon={<CheckCircle />} title={tab === "reviewed" || tab === "dismissed" ? "No decisions here yet" : "Nothing left to decide here"} body={tab === "reviewed" ? "Pairs you confirm or flag for the sender move here." : tab === "dismissed" ? "Pairs you mark as not a duplicate move here." : by(tab).length ? "Every pair in this category has a decision — see Reviewed and Dismissed." : "TrueBind found no pairs of this kind in the selected report."} />
        </div>
      ) : (
        <div className="grid grid-cols-[minmax(0,1fr)] min-h-[480px] overflow-hidden rounded-xl lg:grid-cols-[minmax(280px,360px)_minmax(0,1fr)]" style={{ background: "var(--surface)", boxShadow: "var(--shadow)" }}>
          <div className="flex max-h-[640px] flex-col overflow-y-auto" style={{ boxShadow: "1px 0 0 var(--line)" }}>
            {current.map((p) => {
              const on = p === pair;
              return (
                <button key={p.validation_result_id} type="button" onClick={() => setSel(p.validation_result_id)} className="flex cursor-pointer flex-col gap-1 px-4 py-3.5 text-left transition-colors hover:bg-[var(--accentTint)]" style={{ background: on ? "var(--accentTint)" : "transparent", boxShadow: on ? "inset 2px 0 0 var(--accent)" : "inset 0 -1px 0 var(--line)" }}>
                  <span className="flex items-center justify-between gap-2">
                    <span className="tnum text-[13px] font-medium">{String(p.row_a.claim_reference ?? "—")}</span>
                    <span className="tnum text-[12px]" style={{ color: "var(--faint)" }}>{formatMoney(p.row_a.incurred_amount as number, (p.row_a.currency as string) ?? "")}</span>
                  </span>
                  <span className="text-[12.5px]" style={{ color: "var(--muted)" }}>{String(p.row_a.insured_name ?? "")} · {String(p.row_a.sheet_name ?? "")} rows {String(p.row_a.source_row_number ?? "?")} & {String(p.row_b.source_row_number ?? "?")}</span>
                  <span className="mt-0.5">{p.review_status ? <StatusPill tone="med">{REVIEW_LABEL[p.review_status]}</StatusPill> : <StatusPill tone="warn">Unreviewed</StatusPill>}</span>
                </button>
              );
            })}
          </div>
          {pair && <Compare key={pair.validation_result_id} pair={pair} onReview={review} />}
        </div>
      )}
    </div>
  );
}

function Compare({ pair, onReview }: { pair: DuplicatePair; onReview: (s: string) => Promise<void> }) {
  const [busy, setBusy] = useState<string | null>(null);
  const g = findingGuide(pair.match_type);
  const same = FIELDS.filter((f) => pair.row_a[f.key] != null && pair.row_b[f.key] != null && norm(pair.row_a[f.key]) === norm(pair.row_b[f.key])).length;
  const act = async (s: string) => {
    setBusy(s);
    try {
      await onReview(s);
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="anim-fade flex min-w-0 flex-col gap-5 px-5 py-6 sm:px-7">
      <div className="flex flex-col gap-2">
        <StatusPill tone={pair.match_type === "exact_duplicate" ? "warn" : pair.match_type === "probable_duplicate" ? "med" : "muted"}>{g.title} · {same} of {FIELDS.length} fields identical</StatusPill>
        <h2 className="m-0 text-[22px] font-medium tracking-[-0.02em]">{String(pair.row_a.claim_reference ?? "—")} · {String(pair.row_a.insured_name ?? "")}</h2>
        <p className="m-0 max-w-[640px] text-[14px] leading-[1.6]" style={{ color: "var(--muted)" }}>{pair.detail} {g.why}</p>
      </div>
      <div className="overflow-x-auto rounded-lg" style={{ background: "#f7f8f6", color: "#2a2f36", boxShadow: "0 0 0 1px var(--line2)" }}>
        <table className="w-full min-w-[600px] border-collapse text-[12px]">
          <thead>
            <tr style={{ background: "oklch(0.96 0.02 150)" }}>
              {["Field", `A · ${String(pair.row_a.sheet_name ?? "")} row ${String(pair.row_a.source_row_number ?? "—")}`, `B · ${String(pair.row_b.sheet_name ?? "")} row ${String(pair.row_b.source_row_number ?? "—")}`].map((h) => (
                <th key={h} className="px-3 py-2 text-left text-[10.5px] font-semibold" style={{ borderBottom: "1px solid #d5d9d3", color: "#5e656d" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {FIELDS.map((f) => {
              const a = pair.row_a[f.key],
                b = pair.row_b[f.key];
              const diff = a != null && b != null && norm(a) !== norm(b);
              return (
                <tr key={f.key} style={{ borderBottom: "1px solid #e6e8e4" }}>
                  <td className="px-3 py-[7px] font-medium" style={{ color: "oklch(0.4 0.1 150)" }}>{f.label}</td>
                  <td className="tnum px-3 py-[7px]">{show(pair.row_a, f) || <i style={{ color: "#8a9098" }}>blank</i>}</td>
                  <td className="tnum px-3 py-[7px]" style={diff ? { background: "oklch(0.95 0.06 85)", color: "oklch(0.46 0.1 70)", fontWeight: 500 } : undefined}>{show(pair.row_b, f) || <i style={{ color: "#8a9098" }}>blank</i>}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {pair.review_status ? (
        <div className="flex items-center gap-2 rounded-lg px-3.5 py-2.5 text-[13px]" style={{ background: "var(--okT)", color: "var(--ok)" }}>
          <CheckCircle size={16} />
          <span className="flex-1">{REVIEW_LABEL[pair.review_status]}. Recorded in the audit trail. Change it with the buttons below.</span>
        </div>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <button type="button" className="tb-btn tb-btn-primary" disabled={!!busy} onClick={() => void act("confirmed_duplicate")}>{busy === "confirmed_duplicate" ? "Saving…" : "Confirm duplicate"}</button>
        <button type="button" className="tb-btn" disabled={!!busy} onClick={() => void act("flagged_for_sender")}>{busy === "flagged_for_sender" ? "Saving…" : "Flag for sender"}</button>
        <button type="button" className="tb-btn tb-btn-ghost" disabled={!!busy} onClick={() => void act("not_duplicate")}>{busy === "not_duplicate" ? "Saving…" : "Not a duplicate"}</button>
      </div>
      <span className="text-[12px]" style={{ color: "var(--faint)" }}>Decisions only record what you concluded. The source file is never edited.</span>
    </div>
  );
}

function Development({ reportId, refs }: { reportId: string; refs: string[] }) {
  const [ref, setRef] = useState(refs[0] ?? null);
  const rows = useApi(() => (ref ? api.listClaimsByRef(reportId, ref) : Promise.resolve([])), [reportId, ref]);
  if (!refs.length) return <div className="tb-card"><EmptyState icon={<Pulse />} title="No claim development in this report" body="When a claim is re-reported with a later period or changed amounts, it appears here as movement, not as a duplicate." /></div>;
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] min-h-[420px] overflow-hidden rounded-xl lg:grid-cols-[minmax(240px,300px)_minmax(0,1fr)]" style={{ background: "var(--surface)", boxShadow: "var(--shadow)" }}>
      <div className="flex max-h-[560px] flex-col overflow-y-auto" style={{ boxShadow: "1px 0 0 var(--line)" }}>
        {refs.map((r) => (
          <button key={r} type="button" onClick={() => setRef(r)} className="flex cursor-pointer items-center justify-between px-4 py-3 text-left transition-colors hover:bg-[var(--accentTint)]" style={{ background: r === ref ? "var(--accentTint)" : "transparent", boxShadow: r === ref ? "inset 2px 0 0 var(--accent)" : "inset 0 -1px 0 var(--line)" }}>
            <span className="tnum text-[13px] font-medium">{r}</span>
            <StatusPill tone="ok">Development</StatusPill>
          </button>
        ))}
      </div>
      <div className="flex min-w-0 flex-col gap-3 px-5 py-6 sm:px-7">
        <span className="text-[17px] font-medium">Movement for {ref}</span>
        <span className="text-[13px]" style={{ color: "var(--muted)" }}>Every row reported for this claim reference in the file, in source order. Movement between periods is normal and is never counted as duplication.</span>
        {rows.error ? (
          <ErrorState title="Rows could not be loaded" message={rows.error} onRetry={rows.reload} />
        ) : !rows.data ? (
          <LoadingState label="Loading rows" rows={4} />
        ) : (
          <div className="overflow-x-auto rounded-lg" style={{ background: "#f7f8f6", color: "#2a2f36", boxShadow: "0 0 0 1px var(--line2)" }}>
            <table className="w-full min-w-[560px] border-collapse text-[12px]">
              <thead>
                <tr style={{ background: "oklch(0.96 0.02 150)" }}>
                  {["Source", "Period", "Status", "Paid to date", "Reserve", "Total incurred"].map((h, i) => (
                    <th key={h} className="px-3 py-2 text-[10.5px] font-semibold" style={{ borderBottom: "1px solid #d5d9d3", color: "#5e656d", textAlign: i >= 3 ? "right" : "left" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.data.map((c) => (
                  <tr key={c.id} style={{ borderBottom: "1px solid #e6e8e4" }}>
                    <td className="tnum px-3 py-[7px]">row {c.source_row_number ?? "—"}</td>
                    <td className="px-3 py-[7px]">{c.reporting_period ?? "—"}</td>
                    <td className="px-3 py-[7px]">{c.claim_status ?? "—"}</td>
                    <td className="tnum px-3 py-[7px] text-right">{formatMoney(c.paid_amount, c.currency)}</td>
                    <td className="tnum px-3 py-[7px] text-right">{formatMoney(c.reserve_amount, c.currency)}</td>
                    <td className="tnum px-3 py-[7px] text-right">{formatMoney(c.incurred_amount, c.currency)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
