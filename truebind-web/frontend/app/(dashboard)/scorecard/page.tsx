"use client";

import { useState } from "react";
import { ChartBar } from "@phosphor-icons/react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { decimalMoney } from "@/lib/findings";
import { formatDate } from "@/lib/formatters";
import { EmptyState, ErrorState, LoadingState, PageHeader, StatusPill } from "@/components/nocturne/ui";

const WINDOWS = [
  { value: "", label: "All time" },
  { value: "365", label: "Last 12 months" },
  { value: "90", label: "Last 90 days" },
];

function sinceDate(days: string): string | undefined {
  if (!days) return undefined;
  return new Date(Date.now() - Number(days) * 86_400_000).toISOString().slice(0, 10);
}

const NA = () => <span style={{ color: "var(--faint)" }}>not assessed</span>;

function Trend({ values, title }: { values: number[]; title: string }) {
  const max = Math.max(100, ...values);
  return (
    <span className="flex h-[22px] items-end gap-[2px]" role="img" aria-label={`${title}: ${values.join(", ")}`}>
      {values.slice(-12).map((v, i, a) => (
        <span key={i} className="w-[5px] rounded-sm" style={{ height: `${Math.max(8, (v / max) * 100)}%`, background: i === a.length - 1 ? "var(--accent)" : "var(--line2)" }} />
      ))}
    </span>
  );
}

const scoreTone = (s: number | null) => (s == null ? "muted" : s >= 85 ? "ok" : s >= 65 ? "warn" : "err");

export default function ScorecardPage() {
  const [win, setWin] = useState("");
  const card = useApi(() => api.getScorecard(sinceDate(win)), [win]);
  return (
    <div className="flex max-w-[1440px] flex-col gap-6 px-4 pb-12 pt-8 sm:px-9">
      <PageHeader
        kicker="Investigate"
        title="Sender scorecard"
        sub="How well each coverholder or TPA reports, from processed bordereaux only. Figures with nothing to compute from say so."
        actions={
          <label className="flex items-center gap-2 text-[13px]" htmlFor="sc-window" style={{ color: "var(--muted)" }}>
            Period
            <select id="sc-window" className="tb-input !min-h-[36px] !w-auto !py-1.5" value={win} onChange={(e) => setWin(e.target.value)}>
              {WINDOWS.map((w) => <option key={w.value} value={w.value}>{w.label}</option>)}
            </select>
          </label>
        }
      />
      {card.error ? (
        <ErrorState title="The scorecard could not be loaded" message={card.error} onRetry={card.reload} />
      ) : !card.data ? (
        <div className="tb-card p-4 sm:p-6"><LoadingState label="Loading scorecard" rows={6} /></div>
      ) : card.data.senders.length === 0 ? (
        <div className="tb-card"><EmptyState icon={<ChartBar />} title="No processed bordereaux yet" body="Scores appear once reports from a sender have been processed. Record the sender when uploading." /></div>
      ) : (
        <div className="tb-card overflow-x-auto">
          <table className="w-full min-w-[1100px] border-collapse text-[13px]">
            <caption className="sr-only">Senders, lowest latest health score first</caption>
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-[.06em]" style={{ color: "var(--faint)" }}>
                {["Sender", "Reports", "Latest score", "Trend", "Exceptions / 1,000 rows", "Resubmissions / 1,000 rows", "Binder breaches", "Open sanctions matches", "Leakage exposure", "Mapping right first time"].map((h) => (
                  <th key={h} scope="col" className="px-4 py-3 font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {card.data.senders.map((s) => (
                <tr key={s.sender} style={{ boxShadow: "0 -1px 0 var(--line)" }}>
                  <th scope="row" className="px-4 py-3 text-left font-normal">
                    <div className="font-medium">{s.sender}</div>
                    <div className="text-[12px]" style={{ color: "var(--faint)" }}>{s.rows.toLocaleString("en-GB")} rows · latest {formatDate(s.latest_report_at)}</div>
                  </th>
                  <td className="tnum px-4 py-3">{s.reports}</td>
                  <td className="px-4 py-3">{s.latest_score == null ? <NA /> : <StatusPill tone={scoreTone(s.latest_score)}>{s.latest_score}{s.latest_grade ? ` · ${s.latest_grade}` : ""}</StatusPill>}</td>
                  <td className="px-4 py-3">{s.score_trend.length > 1 ? <Trend values={s.score_trend} title={`${s.sender} health score trend`} /> : "—"}</td>
                  <td className="tnum px-4 py-3">{s.exceptions_per_1000_rows ?? <NA />}</td>
                  <td className="tnum px-4 py-3">{s.resubmissions_per_1000_rows ?? <NA />}</td>
                  <td className="tnum px-4 py-3" style={{ color: s.binder_breaches ? "var(--err)" : undefined }}>{s.binder_breaches}</td>
                  <td className="tnum px-4 py-3" style={{ color: s.sanctions_open_matches ? "var(--warn)" : undefined }}>{s.sanctions_open_matches}</td>
                  <td className="tnum px-4 py-3">{Object.keys(s.leakage_exposure).length ? Object.entries(s.leakage_exposure).map(([c, v]) => decimalMoney(v, c)).join(" · ") : "None found"}</td>
                  <td className="tnum px-4 py-3">{s.mapping_first_time_right_pct}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {card.data?.not_assessed.map((x) => (
        <p key={x} className="m-0 text-[12.5px]" style={{ color: "var(--faint)" }}>{x}</p>
      ))}
    </div>
  );
}
