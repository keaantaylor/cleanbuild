"use client";

import { useEffect, useRef, useState } from "react";
import type { Report, SystemStatus } from "@/lib/types";
import { formatBytes, formatDuration, formatNumber } from "@/lib/formatters";
import { stageIndex, stagesFor } from "@/lib/stages";
import { Button } from "@/components/ui/Button";
import { ErrorState, FileCard, Pill, StageTimeline, type StageState } from "@/components/ds";
import { EngineVisual } from "./EngineVisual";
import styles from "./intake.module.css";

/** Shows exactly what the backend reports: the job's stage, the facts the
 * engine has established so far and elapsed time. Stage times are when this
 * page first observed each stage -- real observations, not estimates. */
export function ProcessingView({ report, system, onCancel, onRetry }: {
  report: Report; system: SystemStatus | null; onCancel?: () => void; onRetry?: () => void;
}) {
  const job = report.job;
  const steps = stagesFor(job);
  const [now, setNow] = useState(() => Date.now());
  // First time this page saw each stage, keyed by job id -- real observations.
  const [seen, setSeen] = useState<{ job?: string; at: Record<string, number> }>({ at: {} });
  const current = useRef<{ job?: string; key?: string }>({});
  useEffect(() => { current.current = { job: job?.id, key: stagesFor(job)[stageIndex(job)]?.key }; });
  useEffect(() => {
    const t = setInterval(() => {
      const ts = Date.now();
      setNow(ts);
      const { job: jid, key } = current.current;
      if (!key) return;
      setSeen((prev) => {
        const base = prev.job === jid ? prev : { job: jid, at: {} };
        return base.at[key] !== undefined ? base : { job: jid, at: { ...base.at, [key]: ts } };
      });
    }, 250);
    return () => clearInterval(t);
  }, []);
  const failed = report.status === "FAILED" || job?.status === "FAILED";
  const idx = stageIndex(job);
  const progress = (job?.metrics?.progress ?? {}) as Record<string, number>;
  const started = job ? new Date(job.created_at).getTime() : now;
  const elapsed = Math.max(0, (now - started) / 1000);
  const queuedFor = job?.status === "QUEUED" ? elapsed : 0;
  const noWorker = system !== null && !system.worker_available;

  if (failed) {
    return (
      <ErrorState title="We couldn't finish processing this workbook"
        message={<>{report.processing_error || job?.error_message || "Processing stopped before completing."}
          {job?.error_code === "worker_lost" && " The processing service stopped while working on it."}</>}
        details={report.error_code ? `code: ${report.error_code}` : undefined} onRetry={onRetry} />
    );
  }

  const detail = (key: string) => {
    if (key === "queued" && job?.status === "QUEUED") return noWorker ? "No processing engine is running" : `Waiting ${formatDuration(queuedFor)}`;
    if (key === "detecting_sheets" && progress.sheets_found !== undefined)
      return `${progress.sheets_found} sheet(s) · ${progress.sheets_with_data ?? 0} with data · ${formatNumber(progress.rows_detected)} rows`;
    if (key === "proposing_mapping" && progress.ai_calls !== undefined) return `${progress.ai_calls} AI call(s) · column headers only`;
    if (key === "mapping" && progress.rows_detected !== undefined) return `${formatNumber(progress.rows_detected)} rows read`;
    if (key === "validating" && progress.rows_mapped !== undefined) return `${formatNumber(progress.rows_mapped)} rows mapped`;
    if (key === "checking_duplicates" && progress.row_findings !== undefined)
      return `${formatNumber(progress.row_findings)} row finding(s) · ${formatNumber(progress.arithmetic_mismatches ?? 0)} arithmetic mismatch(es)`;
    if (key === "building_report" && progress.duplicate_pairs !== undefined) return `${formatNumber(progress.duplicate_pairs)} duplicate pair(s)`;
    return undefined;
  };
  const meta = (key: string, i: number) => {
    const at = seen.job === job?.id ? seen.at[key] : undefined;
    if (at === undefined || i > idx) return undefined;
    return `+${((at - started) / 1000).toFixed(1)}s`;
  };

  const facts: { label: string; value: number | undefined }[] = [
    { label: "Sheets", value: progress.sheets_with_data ?? progress.sheets_found },
    { label: "Rows", value: progress.rows_mapped ?? progress.rows_detected },
    { label: "Findings", value: progress.row_findings },
    { label: "Duplicate pairs", value: progress.duplicate_pairs },
  ];
  const busy = job?.status === "RUNNING";

  return (
    <div className={styles.processing}>
      <section className={styles.procCard} aria-live="polite">
        <div className={styles.procHead}>
          <FileCard name={report.file_name}
            meta={`${(report.file_kind ?? "").toUpperCase()} · ${formatBytes(report.file_size_bytes)}${report.sender ? ` · from ${report.sender}` : ""}`} />
          <div className={styles.procActions}>
            <Pill tone={busy ? "info" : "neutral"} pulse={busy}>{formatDuration(elapsed)}</Pill>
            {onCancel && <Button size="sm" variant="ghost" onClick={onCancel}>Cancel</Button>}
          </div>
        </div>
        <div className={styles.procStage}>
          <EngineVisual active={busy} />
          <div style={{ minWidth: 0 }}>
            <p className={styles.procEyebrow}>{job?.kind === "PROCESS" ? "Producing your health report" : "Reading your workbook"}</p>
            <p className={styles.procNow}>{steps[idx]?.label}</p>
            <p className={styles.procStep}>Engine stage {Math.min(idx + 1, steps.length)} of {steps.length}</p>
          </div>
        </div>
        <dl className={styles.facts}>
          {facts.map((f) => (
            <div key={f.label} className={styles.fact}>
              <dt>{f.label}</dt>
              <dd className={f.value === undefined ? styles.factPending : ""}>{f.value === undefined ? "—" : formatNumber(f.value)}</dd>
            </div>
          ))}
        </dl>
      </section>
      <section className={styles.procTimeline} aria-label="Processing stages">
        <StageTimeline stages={steps.map((s, i) => {
          const state: StageState = i < idx ? "done" : i === idx ? (s.key === "done" ? "done" : "active") : "pending";
          return { key: s.key, label: s.label, state, detail: i <= idx ? detail(s.key) : undefined, meta: meta(s.key, i) };
        })} />
      </section>
      {job?.status === "QUEUED" && noWorker && queuedFor > 4 && (
        <ErrorState title="Processing service unavailable"
          message="This file is safely stored and queued, but no processing worker is running, so it cannot start. It will be picked up automatically as soon as the service is running. Locally, start everything with ./dev.ps1 (Windows) or ./dev.sh."
          onRetry={onRetry} />
      )}
      {job?.status === "QUEUED" && !noWorker && queuedFor > 20 && (
        <p className={styles.note}>Still queued after {formatDuration(queuedFor)}: {system?.running ?? 0} job(s) running ahead of this one for your organisation.</p>
      )}
    </div>
  );
}
