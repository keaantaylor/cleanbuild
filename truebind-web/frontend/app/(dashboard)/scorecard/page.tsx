"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { decimalMoney } from "@/lib/findings";
import { formatDate } from "@/lib/formatters";
import { EmptyState, ErrorState, PageHeader, Panel, Sparkbars, ds } from "@/components/ds";
import { PageSkeleton } from "@/components/layout/ShellSkeleton";
import styles from "./scorecard.module.css";

const WINDOWS = [
  { value: "", label: "All time" },
  { value: "365", label: "Last 12 months" },
  { value: "90", label: "Last 90 days" },
];

function sinceDate(days: string): string | undefined {
  if (!days) return undefined;
  const d = new Date(Date.now() - Number(days) * 86_400_000);
  return d.toISOString().slice(0, 10);
}

const na = <span className={styles.na}>not assessed</span>;

export default function ScorecardPage() {
  const [window, setWindow] = useState("");
  const card = useApi(() => api.getScorecard(sinceDate(window)), [window]);
  return (
    <>
      <PageHeader eyebrow="Investigate" title="Coverholder scorecard"
        description="How well each coverholder or TPA reports, from processed bordereaux only. Figures with nothing to compute from say so." />
      <div className={ds.stack}>
        <label className={styles.filter} htmlFor="sc-window">Period
          <select id="sc-window" className={styles.select} value={window} onChange={(e) => setWindow(e.target.value)}>
            {WINDOWS.map((w) => <option key={w.value} value={w.value}>{w.label}</option>)}
          </select>
        </label>
        {card.error ? <ErrorState message={card.error} onRetry={card.reload} />
          : !card.data ? <PageSkeleton label="Loading scorecard" />
          : card.data.senders.length === 0 ? <Panel><EmptyState icon="reports" title="No processed bordereaux yet" body="Scores appear once reports from a sender have been processed. Record the sender when uploading." /></Panel>
          : (
            <Panel flush>
              <div className={styles.tableWrap}>
                <table className={styles.table}>
                  <caption className={styles.caption}>Senders, lowest latest health score first</caption>
                  <thead><tr>
                    <th scope="col">Sender</th><th scope="col">Reports</th><th scope="col">Latest score</th><th scope="col">Trend</th>
                    <th scope="col">Exceptions / 1,000 rows</th><th scope="col">Resubmissions / 1,000 rows</th>
                    <th scope="col">Binder breaches</th><th scope="col">Open sanctions matches</th><th scope="col">Leakage exposure</th>
                    <th scope="col">Mapping first time right</th>
                  </tr></thead>
                  <tbody>{card.data.senders.map((s) => (
                    <tr key={s.sender}>
                      <th scope="row"><div className={styles.who}><strong>{s.sender}</strong><span>{s.rows.toLocaleString("en-GB")} rows · latest {formatDate(s.latest_report_at)}</span></div></th>
                      <td>{s.reports}</td>
                      <td>{s.latest_score ?? na}{s.latest_grade ? ` (grade ${s.latest_grade})` : ""}</td>
                      <td>{s.score_trend.length > 1 ? <Sparkbars values={s.score_trend} title={`${s.sender} health score trend`} /> : "—"}</td>
                      <td>{s.exceptions_per_1000_rows ?? na}</td>
                      <td>{s.resubmissions_per_1000_rows ?? na}</td>
                      <td>{s.binder_breaches}</td>
                      <td>{s.sanctions_open_matches}</td>
                      <td>{Object.keys(s.leakage_exposure).length ? Object.entries(s.leakage_exposure).map(([c, v]) => decimalMoney(v, c)).join(" · ") : "None found"}</td>
                      <td>{s.mapping_first_time_right_pct}%</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            </Panel>
          )}
        {card.data?.not_assessed.map((x) => <p key={x} className={styles.note}>{x}</p>)}
      </div>
    </>
  );
}
