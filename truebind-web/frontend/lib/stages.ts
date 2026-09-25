import type { Job } from "./types";

/** The real stages a job reports (backend job_handlers + engine on_stage).
 * The UI shows only these -- no synthetic steps, no invented percentages. */
export type StageDef = { key: string; label: string; short: string };

export const INGEST_STAGES: StageDef[] = [
  { key: "received", label: "Received · file checks passed", short: "Received" },
  { key: "queued", label: "Waiting for the processing engine", short: "Queued" },
  { key: "inspecting", label: "Inspecting the workbook", short: "Inspecting" },
  { key: "detecting_sheets", label: "Detecting sheets and header rows", short: "Detecting sheets" },
  { key: "proposing_mapping", label: "Mapping source columns to fields", short: "Mapping" },
  { key: "saving", label: "Saving the mapping proposal", short: "Saving" },
  { key: "done", label: "Ready for your review", short: "Ready" },
];

export const PROCESS_STAGES: StageDef[] = [
  { key: "received", label: "Mapping confirmed", short: "Confirmed" },
  { key: "queued", label: "Waiting for the processing engine", short: "Queued" },
  { key: "parsing", label: "Re-reading the workbook", short: "Reading" },
  { key: "mapping", label: "Applying the confirmed mapping", short: "Mapping" },
  { key: "validating", label: "Validating every row", short: "Validating" },
  { key: "checking_duplicates", label: "Checking duplicates and development", short: "Checking duplicates" },
  { key: "building_report", label: "Building the health report", short: "Building report" },
  { key: "saving", label: "Saving results and lineage", short: "Saving" },
  { key: "done", label: "Report complete", short: "Complete" },
];

// Jobs started before the stage names were refined.
const ALIASES: Record<string, string> = { "INGEST:parsing": "inspecting", "PROCESS:validating_legacy": "validating" };

export function stagesFor(job: Job | null | undefined): StageDef[] {
  return job?.kind === "PROCESS" ? PROCESS_STAGES : INGEST_STAGES;
}

/** Index of the job's current stage within its list. */
export function stageIndex(job: Job | null | undefined): number {
  const steps = stagesFor(job);
  if (!job || job.status === "QUEUED") return 1;
  if (job.status === "SUCCEEDED") return steps.length - 1;
  const key = ALIASES[`${job.kind}:${job.stage}`] ?? job.stage;
  const i = steps.findIndex((s) => s.key === key);
  return i < 0 ? 2 : i;
}

export function stageLabel(job: Job | null | undefined): string {
  if (!job) return "Queued";
  if (job.status === "QUEUED") return "Waiting for the engine";
  return stagesFor(job)[stageIndex(job)]?.short ?? "Working";
}
