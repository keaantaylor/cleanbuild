"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import type { DuplicatePair } from "@/lib/types";
import { findingGuide } from "@/lib/findings";
import { formatDate, formatMoney, formatNumber } from "@/lib/formatters";
import { Button, ButtonLink } from "@/components/ui/Button";
import { Tabs } from "@/components/ui/Tabs";
import { EmptyState, ErrorState, MetricCard, Panel, PageHeader, Pill, SkeletonRows, ds } from "@/components/ds";
import { PageSkeleton } from "@/components/layout/ShellSkeleton";
import { ReportSelect, useSelectedReport } from "@/components/ops/ReportSelect";
import styles from "./duplicates.module.css";

type Row = Record<string, unknown>;
const FIELDS: { key: string; label: string; money?: boolean; date?: boolean }[] = [
  { key: "claim_reference", label: "Claim reference" }, { key: "insured_name", label: "Insured" },
  { key: "reporting_period", label: "Reporting period" }, { key: "date_of_loss", label: "Date of loss", date: true },
  { key: "currency", label: "Currency" }, { key: "paid_amount", label: "Paid to date", money: true },
  { key: "reserve_amount", label: "Reserve", money: true }, { key: "incurred_amount", label: "Total incurred", money: true },
];
const REVIEW_LABEL: Record<string, string> = { not_duplicate: "Not a duplicate", flagged_for_sender: "Flagged for sender", confirmed_duplicate: "Confirmed duplicate" };

function show(row: Row, f: (typeof FIELDS)[number]): string {
  const v = row[f.key];
  if (v === null || v === undefined || v === "") return "—";
  if (f.money) return formatMoney(v as number, (row.currency as string) ?? "");
  if (f.date) return formatDate(v as string);
  return String(v);
}
const norm = (v: unknown) => String(v ?? "").trim().toLowerCase();

function Compare({ pair, onReview }: { pair: DuplicatePair; onReview: (s: string) => Promise<void> }) {
  const [busy, setBusy] = useState<string | null>(null);
  const g = findingGuide(pair.match_type);
  const matches = FIELDS.filter((f) => pair.row_a[f.key] != null && pair.row_b[f.key] != null && norm(pair.row_a[f.key]) === norm(pair.row_b[f.key])).length;
  async function act(s: string) { setBusy(s); try { await onReview(s); } finally { setBusy(null); } }
  return (
    <Panel title={g.title} icon="duplicates" subtitle={pair.detail}
      actions={pair.review_status ? <Pill tone="brand">{REVIEW_LABEL[pair.review_status]}</Pill> : <Pill tone="warn">Unreviewed</Pill>}>
      <p className={styles.why}>{g.why}</p>
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead><tr><th scope="col">Field</th>
            <th scope="col"><span className={styles.side}>A</span> <span className={styles.src}>{String(pair.row_a.sheet_name ?? "")} · row {String(pair.row_a.source_row_number ?? "—")}</span></th>
            <th scope="col"><span className={styles.side}>B</span> <span className={styles.src}>{String(pair.row_b.sheet_name ?? "")} · row {String(pair.row_b.source_row_number ?? "—")}</span></th>
            <th scope="col">Match</th></tr></thead>
          <tbody>
            {FIELDS.map((f) => {
              const a = pair.row_a[f.key], b = pair.row_b[f.key];
              const state = a == null || b == null ? "n/a" : norm(a) === norm(b) ? "same" : "differs";
              return (
                <tr key={f.key} className={state === "differs" ? styles.diff : undefined}>
                  <td className={styles.field}>{f.label}</td><td>{show(pair.row_a, f)}</td><td>{show(pair.row_b, f)}</td>
                  <td>{state === "same" ? <Pill tone="good" dot={false}>same</Pill> : state === "differs" ? <Pill tone="bad" dot={false}>differs</Pill> : <Pill tone="neutral" dot={false}>not comparable</Pill>}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className={styles.evidence}><strong>{matches} of {FIELDS.length}</strong> compared fields are identical. {g.next}</p>
      <div className={styles.actions}>
        <Button variant="primary" loading={busy === "confirmed_duplicate"} onClick={() => act("confirmed_duplicate")}>Confirm duplicate</Button>
        <Button variant="secondary" loading={busy === "flagged_for_sender"} onClick={() => act("flagged_for_sender")}>Flag for sender</Button>
        <Button variant="ghost" loading={busy === "not_duplicate"} onClick={() => act("not_duplicate")}>Not a duplicate</Button>
      </div>
    </Panel>
  );
}

function Development({ reportId, refs }: { reportId: string; refs: string[] }) {
  const [ref, setRef] = useState(refs[0] ?? null);
  const rows = useApi(() => (ref ? api.listClaimsByRef(reportId, ref) : Promise.resolve([])), [reportId, ref]);
  if (!refs.length) return <Panel><EmptyState icon="activity" title="No claim development in this report" body="When a claim is re-reported with a later period or changed amounts, it appears here as movement, not as a duplicate." /></Panel>;
  return (
    <div className={styles.split}>
      <Panel title="Developing claims" icon="activity" subtitle="Same reference, later period or moved amounts" flush>
        <ul className={styles.list}>
          {refs.map((r) => (
            <li key={r}><button type="button" className={`${styles.item} ${r === ref ? styles.itemActive : ""}`} onClick={() => setRef(r)}>
              <span className={ds.mono}>{r}</span><Pill tone="live" dot={false}>development</Pill></button></li>
          ))}
        </ul>
      </Panel>
      <Panel title={ref ? `Movement for ${ref}` : "Select a claim"} icon="layers"
        subtitle="Every row reported for this claim reference in the file, in source order. Movement between periods is normal and is never counted as duplication.">
        {rows.loading && !rows.data ? <SkeletonRows rows={4} /> : (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead><tr><th scope="col">Source</th><th scope="col">Period</th><th scope="col">Status</th><th scope="col" className={styles.num}>Paid to date</th><th scope="col" className={styles.num}>Reserve</th><th scope="col" className={styles.num}>Total incurred</th></tr></thead>
              <tbody>
                {(rows.data ?? []).map((c) => (
                  <tr key={c.id}><td className={styles.src}>row {c.source_row_number ?? "—"}</td><td>{c.reporting_period ?? "—"}</td><td>{c.claim_status ?? "—"}</td>
                    <td className={styles.num}>{formatMoney(c.paid_amount, c.currency)}</td><td className={styles.num}>{formatMoney(c.reserve_amount, c.currency)}</td>
                    <td className={styles.num}>{formatMoney(c.incurred_amount, c.currency)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}

export default function DuplicatesPage() {
  const { reportId, reports, loading: rl, select } = useSelectedReport();
  const [tab, setTab] = useState("exact_duplicate");
  const [idx, setIdx] = useState(0);
  const pairs = useApi(() => (reportId ? api.listDuplicates(reportId) : Promise.resolve([] as DuplicatePair[])), [reportId]);
  const summary = useApi(() => (reportId ? api.getReportSummary(reportId) : Promise.resolve(null)), [reportId]);
  const [err, setErr] = useState<string | null>(null);

  if (rl) return <PageSkeleton label="Loading duplicates" />;
  if (!reportId) return (<><PageHeader eyebrow="Investigate" title="Duplicate intelligence" />
    <Panel><EmptyState icon="duplicates" title="No completed reports yet" action={<ButtonLink href="/upload" variant="primary">Upload a bordereau</ButtonLink>} /></Panel></>);

  const all = pairs.data ?? [];
  const by = (t: string) => all.filter((p) => p.match_type === t);
  const open = (t: string) => by(t).filter((p) => !p.review_status);
  const reviewed = all.filter((p) => p.review_status === "confirmed_duplicate" || p.review_status === "flagged_for_sender");
  const dismissed = all.filter((p) => p.review_status === "not_duplicate");
  const s = summary.data;
  const current = tab === "reviewed" ? reviewed : tab === "dismissed" ? dismissed : open(tab);
  const pair = current[Math.min(idx, Math.max(current.length - 1, 0))];

  async function review(status: string) {
    if (!pair || !reportId) return;
    try {
      await api.reviewDuplicate(reportId, pair.validation_result_id, status);
      setErr(null);
      pairs.reload();
      // A decided pair leaves this queue, so the same index is the next pair.
      if (tab === "reviewed" || tab === "dismissed") setIdx(Math.min(idx + 1, current.length - 1));
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Could not record the decision.");
    }
  }

  return (
    <>
      <PageHeader eyebrow="Investigate" title="Duplicate intelligence"
        description="Exact resubmissions, probable duplicates and repeats TrueBind cannot classify — kept separate from normal claim development. Nothing is ever merged or removed automatically."
        actions={<ReportSelect reportId={reportId} reports={reports} onSelect={(id) => { select(id); setIdx(0); }} />} />
      <div className={ds.stack}>
        <div className={`${ds.grid} ${ds.cols4}`}>
          <MetricCard icon="duplicates" label="Exact resubmissions" value={formatNumber(by("exact_duplicate").length)} tone={by("exact_duplicate").length ? "warn" : "good"}
            caption={`same ref, period and amounts · ${open("exact_duplicate").length} undecided`} />
          <MetricCard icon="search" label="Probable duplicates" value={formatNumber(by("probable_duplicate").length)} tone="processing"
            caption={`similar insured, close loss dates · ${open("probable_duplicate").length} undecided`} />
          <MetricCard icon="calendar" label="Need a reporting period" value={formatNumber(by("repeat_period_unknown").length)} tone="neutral" caption="cannot be classified yet" />
          <MetricCard icon="activity" label="Claim development" value={formatNumber(s?.development_pairs ?? 0)} tone="good" caption="movement — not duplicates" />
        </div>
        <Tabs active={tab} onChange={(t) => { setTab(t); setIdx(0); }} options={[
          { value: "exact_duplicate", label: "Exact", count: open("exact_duplicate").length },
          { value: "probable_duplicate", label: "Probable", count: open("probable_duplicate").length },
          { value: "repeat_period_unknown", label: "Needs period", count: open("repeat_period_unknown").length },
          { value: "development", label: "Development", count: s?.development_pairs ?? 0 },
          { value: "reviewed", label: "Reviewed", count: reviewed.length },
          { value: "dismissed", label: "Dismissed", count: dismissed.length },
        ]} />
        {err && <ErrorState message={err} />}
        {tab === "development" ? <Development reportId={reportId} refs={s?.development_refs ?? []} />
          : pairs.loading && !pairs.data ? <Panel><SkeletonRows rows={6} /></Panel>
          : current.length === 0 ? <Panel><EmptyState icon="check" title={tab === "reviewed" || tab === "dismissed" ? "No decisions here yet" : "Nothing left to decide here"}
              body={tab === "reviewed" ? "Pairs you confirm or flag for the sender move here." : tab === "dismissed" ? "Pairs you mark as not a duplicate move here."
                : by(tab).length ? "Every pair in this category has a decision — see Reviewed and Dismissed." : "TrueBind found no pairs of this kind in the selected report."} /></Panel>
          : (
          <div className={styles.split}>
            <Panel title="Pairs" icon="duplicates" subtitle={`${current.filter((p) => !p.review_status).length} unreviewed`} flush>
              <ul className={styles.list}>
                {current.map((p, i) => (
                  <li key={p.validation_result_id}>
                    <button type="button" className={`${styles.item} ${p === pair ? styles.itemActive : ""}`} onClick={() => setIdx(i)}>
                      <span><span className={ds.mono}>{String(p.row_a.claim_reference ?? "—")}</span>
                        <span className={styles.src}>{String(p.row_a.sheet_name ?? "")} rows {String(p.row_a.source_row_number ?? "?")} & {String(p.row_b.source_row_number ?? "?")}</span></span>
                      {p.review_status ? <Pill tone="brand" dot={false}>{REVIEW_LABEL[p.review_status]?.split(" ")[0]}</Pill> : <Pill tone="warn" dot={false}>new</Pill>}
                    </button>
                  </li>
                ))}
              </ul>
            </Panel>
            {pair && <Compare key={pair.validation_result_id} pair={pair} onReview={review} />}
          </div>
        )}
      </div>
    </>
  );
}
