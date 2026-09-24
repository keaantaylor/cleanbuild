"use client";

import { useEffect, useState } from "react";
import type { Report, SystemStatus } from "@/lib/types";
import { formatDuration, formatNumber } from "@/lib/formatters";
import { Button } from "@/components/ui/Button";
import { ErrorState, Panel, Pill, StageTimeline, type StageState } from "@/components/ds";
import styles from "./intake.module.css";

type Step = { key: string; label: string };
const INGEST: Step[] = [
  { key: "received", label: "Received & file checks passed" },
  { key: "queued", label: "Waiting for the processing service" },
  { key: "parsing", label: "Reading workbook: sheets and header rows" },
  { key: "proposing_mapping", label: "Building field mappings" },
  { key: "saving", label: "Saving mapping proposal" },
  { key: "done", label: "Ready for your review" },
];
const PROCESS: Step[] = [
  { key: "received", label: "Mapping confirmed" },
  { key: "queued", label: "Waiting for the processing service" },
  { key: "parsing", label: "Re-reading workbook" },
  { key: "validating", label: "Validating, checking duplicates, reconciling rows" },
  { key: "saving", label: "Building report" },
  { key: "done", label: "Report complete" },
];

function currentIndex(steps: Step[], r: Report): number {
  const j = r.job;
  if (!j || j.status === "QUEUED") return 1;
  if (j.status === "SUCCEEDED") return steps.length - 1;
  const i = steps.findIndex((s) => s.key === j.stage);
  return i < 0 ? 2 : i; // "starting" -> first working step
}

/** Shows exactly what the backend reports: the job's stage, the facts it
 * has established so far and the elapsed time. No invented percentages. */
export function ProcessingView({ report, system, onCancel, onRetry }: {
  report: Report; system: SystemStatus | null; onCancel?: () => void; onRetry?: () => void;
}) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 500); return () => clearInterval(t); }, []);
  const job = report.job;
  const steps = job?.kind === "PROCESS" ? PROCESS : INGEST;
  const failed = report.status === "FAILED" || job?.status === "FAILED";
  const idx = currentIndex(steps, report);
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
    if (key === "parsing" && progress.sheets_found !== undefined)
      return `${progress.sheets_found} sheet(s) found · ${progress.sheets_with_data ?? 0} with data · ${formatNumber(progress.rows_detected)} rows detected`;
    if (key === "proposing_mapping" && progress.ai_calls !== undefined) return `${progress.ai_calls} AI call(s)`;
    if (key === "validating" && progress.rows_detected !== undefined) return `${formatNumber(progress.rows_detected)} rows`;
    if (key === "queued" && job?.status === "QUEUED") return noWorker ? "No processing worker is running" : `Waiting ${formatDuration(queuedFor)}`;
    return undefined;
  };

  return (
    <div className={styles.processing}>
      <Panel title={job?.kind === "PROCESS" ? "Producing your health report" : "Reading your workbook"} icon="activity"
        actions={<><Pill tone="live" pulse>{formatDuration(elapsed)}</Pill>{onCancel && <Button size="sm" variant="ghost" onClick={onCancel}>Cancel</Button>}</>}>
        <StageTimeline stages={steps.map((s, i) => {
          const state: StageState = i < idx ? "done" : i === idx ? (s.key === "done" ? "done" : "active") : "pending";
          return { key: s.key, label: s.label, state, detail: i <= idx ? detail(s.key) : undefined };
        })} />
      </Panel>
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
