"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, Check, CheckCircle, FileCsv, FileXls, UploadSimple, Warning, X } from "@phosphor-icons/react";
import { api, ApiError, IN_PROGRESS } from "@/lib/api";
import type { MappingField, Report, Sheet, SheetMapping, SystemStatus } from "@/lib/types";
import { formatBytes, formatDuration, formatNumber } from "@/lib/formatters";
import { stageIndex, stagesFor } from "@/lib/stages";
import { ErrorState, LoadingState, StatusPill } from "./ui";

export const ACCEPT = ".xlsx,.xlsm,.xls,.csv";
const STEPS = ["Upload", "File checks", "Read workbook", "Map columns", "Confirm", "Validate", "Report"];

/** Where a file is in the seven-step intake, derived from its real status
 * and job stage -- the stepper never runs ahead of the backend. */
export function intakeStep(report: Report | null, uploading: boolean): number {
  if (!report) return uploading ? 1 : 0;
  const j = report.job;
  switch (report.status) {
    case "UPLOADED":
    case "QUEUED":
      return j?.kind === "PROCESS" ? 5 : 1;
    case "INGESTING":
      return j?.stage === "proposing_mapping" || j?.stage === "saving" ? 3 : 2;
    case "WAITING_FOR_REVIEW":
      return 3;
    case "PROCESSING":
      return 5;
    case "COMPLETE":
      return 6;
    default:
      return j?.kind === "PROCESS" ? 5 : 2;
  }
}

export function IntakeStepper({ current, failed, confirming }: { current: number; failed?: boolean; confirming?: boolean }) {
  const cur = confirming ? 4 : current;
  return (
    <ol className="m-0 flex list-none items-center gap-2 overflow-x-auto rounded-md px-4 py-3.5" style={{ background: "var(--surface)", boxShadow: "var(--shadow)" }} aria-label="Intake progress">
      {STEPS.map((s, i) => {
        const done = i < cur || (i === cur && cur === STEPS.length - 1);
        const on = i === cur && !done;
        const bad = on && failed;
        return (
          <li key={s} className="flex flex-none items-center gap-2 lg:flex-1" aria-current={on ? "step" : undefined}>
            <span className="flex items-center gap-2 whitespace-nowrap text-[13.5px]" style={{ color: on ? "var(--text)" : done ? "var(--muted)" : "var(--faint)", fontWeight: on ? 500 : 400 }}>
              <span
                className="tnum grid h-[26px] w-[26px] place-items-center rounded-full text-[12px]"
                style={{
                  boxShadow: done ? "none" : `inset 0 0 0 1.5px ${bad ? "var(--err)" : on ? "var(--accent)" : "var(--line2)"}`,
                  background: done ? "var(--ok)" : bad ? "var(--errT)" : on ? "var(--accentTint)" : "transparent",
                  color: done ? "#fff" : bad ? "var(--err)" : on ? "var(--accentText)" : "inherit",
                }}
              >
                {done ? <Check size={12} weight="bold" /> : bad ? <X size={12} weight="bold" /> : i + 1}
              </span>
              {s}
            </span>
            {i < STEPS.length - 1 && <span className="hidden h-px min-w-4 flex-1 lg:block" style={{ background: done ? "var(--ok)" : "var(--line2)" }} />}
          </li>
        );
      })}
    </ol>
  );
}

/** Drives one file through upload → mapping review → processing, polling the real report. */
export function useIntake(opts: { onComplete?: (r: Report) => void; onChange?: () => void } = {}) {
  const [report, setReport] = useState<Report | null>(null);
  const [sheets, setSheets] = useState<Sheet[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [upload, setUpload] = useState<{ name: string; sent: number; total: number } | null>(null);
  const polling = useRef<string | null>(null);
  const cb = useRef(opts);
  useEffect(() => {
    cb.current = opts;
  });

  // Each follow() call gets a generation number; only the newest poller keeps
  // running, and a call for the file already being followed is a no-op.
  const gen = useRef(0);
  const follow = useCallback(async (id: string) => {
    if (polling.current === id) return;
    polling.current = id;
    const mine = ++gen.current;
    try {
      for (;;) {
        const r = await api.getReport(id);
        if (gen.current !== mine) return;
        setReport(r);
        if (!IN_PROGRESS.has(r.status)) {
          polling.current = null;
          cb.current.onChange?.();
          if (r.status === "WAITING_FOR_REVIEW") setSheets(await api.listSheets(id));
          if (r.status === "COMPLETE") cb.current.onComplete?.(r);
          return;
        }
        await new Promise((res) => setTimeout(res, 600));
      }
    } catch (e) {
      if (gen.current === mine) {
        polling.current = null;
        setError(e instanceof ApiError ? e.message : "Lost contact with the server.");
      }
    }
  }, []);

  useEffect(
    () => () => {
      polling.current = null;
      gen.current++;
    },
    [],
  );

  const start = useCallback(
    async (file: File, meta: { sender?: string; programme?: string }) => {
      setError(null);
      if (!/\.(xlsx|xlsm|xls|csv)$/i.test(file.name)) {
        setError("That isn’t a spreadsheet TrueBind can read. Choose an .xlsx, .xlsm, .xls or .csv file.");
        return null;
      }
      setUpload({ name: file.name, sent: 0, total: file.size });
      try {
        const r = await api.uploadWithProgress(file, meta, (sent, total) => setUpload({ name: file.name, sent, total }));
        setUpload(null);
        setReport(r);
        cb.current.onChange?.();
        void follow(r.id);
        return r;
      } catch (e) {
        setUpload(null);
        setError(e instanceof ApiError ? e.message : "The upload failed.");
        return null;
      }
    },
    [follow],
  );

  const process = useCallback(async () => {
    if (!report) return;
    const r = await api.processReport(report.id);
    setReport(r);
    void follow(r.id);
  }, [report, follow]);

  const cancel = useCallback(async () => {
    if (!report) return;
    try {
      setReport(await api.cancelReport(report.id));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not cancel.");
    }
  }, [report]);

  const retry = useCallback(async () => {
    if (!report) return;
    try {
      const r = await api.retryReport(report.id);
      setReport(r);
      void follow(r.id);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not retry.");
    }
  }, [report, follow]);

  const reset = useCallback(() => {
    polling.current = null;
    gen.current++;
    setReport(null);
    setSheets([]);
    setError(null);
  }, []);

  return { report, sheets, setSheets, error, setError, upload, start, follow, process, cancel, retry, reset };
}

export function Dropzone({ upload, onFile, compact }: { upload: { name: string; sent: number; total: number } | null; onFile: (f: File) => void; compact?: boolean }) {
  const [drag, setDrag] = useState(false);
  const pct = upload && upload.total ? Math.round((100 * upload.sent) / upload.total) : 0;
  return (
    <label
      onDragOver={(e) => {
        e.preventDefault();
        setDrag(true);
      }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDrag(false);
        const f = e.dataTransfer.files?.[0];
        if (f && !upload) onFile(f);
      }}
      className={`flex cursor-pointer flex-col items-center justify-center gap-3 rounded-md px-6 text-center transition-colors ${compact ? "py-10" : "min-h-[280px] py-12"}`}
      style={{ boxShadow: `inset 0 0 0 1.5px ${drag ? "var(--accent)" : "var(--line2)"}`, background: drag ? "var(--accentTint)" : "var(--surface)" }}
    >
      <input
        type="file"
        accept={ACCEPT}
        className="sr-only"
        disabled={!!upload}
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onFile(f);
          e.target.value = "";
        }}
      />
      <span className="grid h-12 w-12 place-items-center rounded-full text-[22px]" style={{ background: "var(--accentTint)", color: "var(--accentText)" }}>
        <UploadSimple />
      </span>
      <span className="text-[16px] font-medium">{upload ? `Uploading ${upload.name}…` : "Drop a claims bordereau here"}</span>
      <span className="text-[13px]" style={{ color: "var(--muted)" }}>.xlsx · .xlsm · .xls · .csv - macros are never run; password-protected files are rejected</span>
      {upload ? (
        <span className="w-full max-w-[420px]" aria-live="polite">
          <span className="block h-1.5 overflow-hidden rounded-full" style={{ background: "var(--line)" }}>
            <span className="block h-full rounded-full transition-[width]" style={{ width: `${pct}%`, background: "var(--accent)" }} />
          </span>
          <span className="tnum mt-1.5 block text-[12px]" style={{ color: "var(--faint)" }}>
            {formatBytes(upload.sent)} of {formatBytes(upload.total)} sent
          </span>
        </span>
      ) : (
        <span className="tb-btn tb-btn-primary mt-1">Choose a file</span>
      )}
    </label>
  );
}

export function FileGlyph({ name, size = 22 }: { name: string; size?: number }) {
  return /\.csv$/i.test(name) ? <FileCsv size={size} style={{ color: "oklch(0.55 0.11 150)" }} /> : <FileXls size={size} style={{ color: "oklch(0.55 0.11 150)" }} />;
}

/** Shows exactly what the backend reports: the job's stage, facts established
 * so far and elapsed time. Stage times are when this page first observed each
 * stage -- real observations, never estimates. */
export function ProcessingPanel({ report, system, onCancel, onRetry }: { report: Report; system: SystemStatus | null; onCancel?: () => void; onRetry?: () => void }) {
  const job = report.job;
  const steps = stagesFor(job);
  const [now, setNow] = useState(() => Date.now());
  const [seen, setSeen] = useState<{ job?: string; at: Record<string, number> }>({ at: {} });
  const current = useRef<{ job?: string; key?: string }>({});
  useEffect(() => {
    current.current = { job: job?.id, key: stagesFor(job)[stageIndex(job)]?.key };
  });
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
  const cancelled = report.status === "CANCELLED";
  const idx = stageIndex(job);
  const progress = (job?.metrics?.progress ?? {}) as Record<string, number>;
  const started = job ? new Date(job.created_at).getTime() : now;
  const elapsed = Math.max(0, (now - started) / 1000);
  const queuedFor = job?.status === "QUEUED" ? elapsed : 0;
  const noWorker = system !== null && !system.worker_available;

  if (failed || cancelled)
    return (
      <div className="flex flex-col gap-3">
        <ErrorState
          title={cancelled ? "Processing was cancelled" : "We couldn’t finish processing this workbook"}
          message={cancelled ? "Nothing was validated. Retry to run it again." : `${report.processing_error || job?.error_message || "Processing stopped before completing."}${job?.error_code === "worker_lost" ? " The processing service stopped while working on it." : ""}${report.error_code ? ` (code: ${report.error_code})` : ""}`}
          onRetry={onRetry}
        />
      </div>
    );

  const detail = (key: string) => {
    if (key === "queued" && job?.status === "QUEUED") return noWorker ? "No processing engine is running" : `Waiting ${formatDuration(queuedFor)}`;
    if (key === "detecting_sheets" && progress.sheets_found !== undefined) return `${progress.sheets_found} sheet(s) · ${progress.sheets_with_data ?? 0} with data · ${formatNumber(progress.rows_detected)} rows`;
    if (key === "proposing_mapping" && progress.ai_calls !== undefined) return `${progress.ai_calls} AI call(s) · column headers only`;
    if (key === "mapping" && progress.rows_detected !== undefined) return `${formatNumber(progress.rows_detected)} rows read`;
    if (key === "validating" && progress.rows_mapped !== undefined) return `${formatNumber(progress.rows_mapped)} rows mapped`;
    if (key === "checking_duplicates" && progress.row_findings !== undefined) return `${formatNumber(progress.row_findings)} row finding(s) · ${formatNumber(progress.arithmetic_mismatches ?? 0)} arithmetic mismatch(es)`;
    if (key === "building_report" && progress.duplicate_pairs !== undefined) return `${formatNumber(progress.duplicate_pairs)} duplicate pair(s)`;
    return undefined;
  };
  const facts: [string, number | undefined][] = [
    ["Sheets", progress.sheets_with_data ?? progress.sheets_found],
    ["Rows", progress.rows_mapped ?? progress.rows_detected],
    ["Findings", progress.row_findings],
    ["Duplicate pairs", progress.duplicate_pairs],
  ];
  const busy = job?.status === "RUNNING";

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
      <section className="tb-card flex flex-col gap-5 p-4 sm:p-5" aria-live="polite">
        <div className="flex flex-wrap items-center gap-3">
          <FileGlyph name={report.file_name} />
          <div className="flex min-w-0 flex-1 flex-col">
            <span className="truncate text-[14px] font-medium">{report.file_name}</span>
            <span className="text-[12px]" style={{ color: "var(--faint)" }}>
              {(report.file_kind ?? "").toUpperCase()} · {formatBytes(report.file_size_bytes)}
              {report.sender ? ` · from ${report.sender}` : ""}
            </span>
          </div>
          <StatusPill tone={busy ? "med" : "muted"}>{formatDuration(elapsed)}</StatusPill>
          {onCancel && (
            <button type="button" className="tb-btn tb-btn-ghost !py-1.5" onClick={onCancel}>
              Cancel
            </button>
          )}
        </div>
        <div className="flex flex-col gap-1">
          <span className="kicker">{job?.kind === "PROCESS" ? "Producing your health report" : "Reading your workbook"}</span>
          <span className="text-[20px] font-medium tracking-[-0.015em]">{steps[idx]?.label}</span>
          <span className="text-[12.5px]" style={{ color: "var(--faint)" }}>
            Engine stage {Math.min(idx + 1, steps.length)} of {steps.length}
          </span>
        </div>
        <div className="relative h-1.5 overflow-hidden rounded-full" style={{ background: "var(--line)" }}>
          <div className="absolute inset-y-0 left-0 rounded-full transition-[width] duration-200" style={{ width: `${((idx + 1) / steps.length) * 100}%`, background: "var(--accent)" }} />
        </div>
        <dl className="tnum m-0 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {facts.map(([l, v]) => (
            <div key={l} className="flex flex-col gap-0.5">
              <dt className="text-[12px]" style={{ color: "var(--faint)" }}>{l}</dt>
              <dd className="m-0 text-[20px] font-medium" style={{ color: v === undefined ? "var(--faint)" : "var(--text)" }}>{v === undefined ? "-" : formatNumber(v)}</dd>
            </div>
          ))}
        </dl>
        {job?.status === "QUEUED" && noWorker && queuedFor > 4 && (
          <ErrorState
            title="Processing service unavailable"
            message="This file is safely stored and queued, but no processing worker is running, so it can’t start yet. It will be picked up automatically as soon as the service is running."
            onRetry={onRetry}
          />
        )}
        {job?.status === "QUEUED" && !noWorker && queuedFor > 20 && (
          <span className="text-[12.5px]" style={{ color: "var(--muted)" }}>
            Still queued after {formatDuration(queuedFor)}: {system?.running ?? 0} job(s) running ahead of this one for your organisation.
          </span>
        )}
      </section>
      <section className="tb-card flex flex-col p-4 sm:p-5" aria-label="Processing stages">
        <ol className="m-0 flex list-none flex-col gap-0 p-0">
          {steps.map((s, i) => {
            const state = i < idx || (i === idx && s.key === "done") ? "done" : i === idx ? "active" : "pending";
            const at = seen.job === job?.id ? seen.at[s.key] : undefined;
            const d = i <= idx ? detail(s.key) : undefined;
            return (
              <li key={s.key} className="grid grid-cols-[20px_1fr_auto] gap-3 py-2">
                <span className="mt-0.5 grid h-[18px] w-[18px] place-items-center rounded-full" style={{ background: state === "done" ? "var(--ok)" : state === "active" ? "var(--accentTint)" : "transparent", boxShadow: state === "pending" ? "inset 0 0 0 1.5px var(--line2)" : state === "active" ? "inset 0 0 0 1.5px var(--accent)" : "none" }}>
                  {state === "done" && <Check size={10} weight="bold" color="#fff" />}
                  {state === "active" && <span className="h-1.5 w-1.5 animate-pulse rounded-full" style={{ background: "var(--accent)" }} />}
                </span>
                <span className="flex min-w-0 flex-col">
                  <span className="text-[13.5px]" style={{ color: state === "pending" ? "var(--faint)" : "var(--text)", fontWeight: state === "active" ? 500 : 400 }}>{s.label}</span>
                  {d && <span className="text-[12px]" style={{ color: "var(--muted)" }}>{d}</span>}
                </span>
                <span className="tnum text-[11.5px]" style={{ color: "var(--faint)" }}>{at !== undefined && i <= idx ? `+${((at - started) / 1000).toFixed(1)}s` : ""}</span>
              </li>
            );
          })}
        </ol>
      </section>
    </div>
  );
}

const REVIEW: Record<string, { label: string; tone: "ok" | "warn" | "err" | "muted" | "med" }> = {
  HIGH_CONFIDENCE: { label: "High confidence", tone: "ok" },
  REVIEW: { label: "Needs review", tone: "warn" },
  AMBIGUOUS: { label: "Ambiguous", tone: "err" },
  UNMAPPED: { label: "Unmapped", tone: "muted" },
  CONFIRMED: { label: "Confirmed", tone: "med" },
};
const METHOD: Record<string, string> = { MAPPED_BY_ALIAS: "alias rule", MAPPED_BY_AI: "AI (headers only)", MAPPED_BY_MEMORY: "remembered", MANUAL: "manual", UNMAPPED: "" };

/** A field needs a person only when the match is uncertain or a required field has no column. */
function needsDecision(f: MappingField): boolean {
  return f.review_state === "REVIEW" || f.review_state === "AMBIGUOUS" || (!!f.required && !f.source_column);
}

/** Per-sheet mapping review: nothing is validated until each sheet is confirmed.
 * High-confidence matches sit behind one summary line; only decisions are shown. */
export function MappingReview({ report, sheets, onSheetsChange, onProcess, processLabel = "Produce health report" }: { report: Report; sheets: Sheet[]; onSheetsChange: (s: Sheet[]) => void; onProcess: () => Promise<void>; processLabel?: string }) {
  const firstOpen = sheets.find((s) => s.status === "PENDING_CONFIRMATION") ?? sheets.find((s) => s.status !== "SKIPPED");
  const [active, setActive] = useState<string | null>(firstOpen?.id ?? null);
  const [mapping, setMapping] = useState<SheetMapping | null>(null);
  const [choices, setChoices] = useState<Record<string, string | null>>({});
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [actionErr, setActionErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    api
      .getSheetMappingFull(report.id, active)
      .then((m) => {
        if (cancelled) return;
        setMapping(m);
        setChoices(Object.fromEntries(m.fields.map((f) => [f.field_code, f.source_column])));
        setLoadErr(null);
      })
      .catch((e) => {
        if (!cancelled) setLoadErr(e instanceof ApiError ? e.message : "Could not load this sheet’s mapping.");
      });
    return () => {
      cancelled = true;
    };
  }, [report.id, active]);

  const pending = sheets.filter((s) => s.status === "PENDING_CONFIRMATION");
  const allDone = sheets.length > 0 && pending.length === 0;
  const usedCols = useMemo(() => {
    const used: Record<string, string> = {};
    for (const [code, col] of Object.entries(choices)) if (col) used[col] = code;
    return used;
  }, [choices]);

  async function refreshSheets(after?: string) {
    const list = await api.listSheets(report.id);
    onSheetsChange(list);
    const next = list.find((s) => s.status === "PENDING_CONFIRMATION" && s.id !== after);
    setMapping(null);
    setActive(next?.id ?? null);
  }
  async function confirmActive() {
    if (!active) return;
    setBusy("confirm");
    setActionErr(null);
    try {
      await api.confirmSheetMapping(report.id, active, choices);
      await refreshSheets(active);
    } catch (e) {
      setActionErr(e instanceof ApiError ? e.message : "Could not confirm this sheet.");
    } finally {
      setBusy(null);
    }
  }
  async function confirmAll() {
    setBusy("all");
    setActionErr(null);
    try {
      for (const s of pending) {
        const m = s.id === active && mapping ? { fields: mapping.fields } : await api.getSheetMappingFull(report.id, s.id);
        const proposed = s.id === active ? choices : Object.fromEntries(m.fields.map((f: MappingField) => [f.field_code, f.source_column]));
        await api.confirmSheetMapping(report.id, s.id, proposed);
      }
      await refreshSheets();
    } catch (e) {
      setActionErr(e instanceof ApiError ? e.message : "Could not confirm every sheet.");
      await refreshSheets().catch(() => undefined);
    } finally {
      setBusy(null);
    }
  }
  async function setIncluded(sheetId: string, include: boolean) {
    setBusy(`inc-${sheetId}`);
    setActionErr(null);
    try {
      if (include) await api.includeSheet(report.id, sheetId);
      else await api.skipSheet(report.id, sheetId);
      const list = await api.listSheets(report.id);
      onSheetsChange(list);
      setMapping(null);
      setActive(include ? sheetId : (list.find((s) => s.status === "PENDING_CONFIRMATION")?.id ?? null));
    } catch (e) {
      setActionErr(e instanceof ApiError ? e.message : include ? "Could not include this sheet." : "Could not skip this sheet.");
    } finally {
      setBusy(null);
    }
  }
  async function process() {
    setBusy("process");
    setActionErr(null);
    try {
      await onProcess();
    } catch (e) {
      setActionErr(e instanceof ApiError ? e.message : "Could not start processing.");
      setBusy(null);
    }
  }

  const activeSheet = sheets.find((s) => s.id === active);
  // Fixed when the mapping loads, so a row does not vanish while it is being decided.
  const decide = useMemo(() => new Set((mapping?.fields ?? []).filter(needsDecision).map((f) => f.field_code)), [mapping]);
  const toCheck = decide.size;
  const autoMapped = mapping?.fields.filter((f) => f.source_column && !decide.has(f.field_code)).length ?? 0;
  const visible = (mapping?.fields ?? []).filter((f) => showAll || decide.has(f.field_code));
  const unmappedCols = mapping ? mapping.headers.filter((h) => !usedCols[h]) : [];

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-4 lg:grid-cols-[minmax(240px,300px)_minmax(0,1fr)]">
      <section className="tb-card flex flex-col overflow-hidden">
        <div className="flex items-baseline justify-between px-4 py-3" style={{ boxShadow: "0 1px 0 var(--line)" }}>
          <span className="text-[14px] font-medium">Sheets</span>
          <span className="tnum text-[12px]" style={{ color: "var(--faint)" }}>{sheets.length - pending.length} of {sheets.length} resolved</span>
        </div>
        {sheets.map((s) => {
          const on = s.id === active;
          const skipped = s.status === "SKIPPED";
          const tone = skipped ? "var(--faint)" : s.status === "CONFIRMED" ? "var(--ok)" : s.mapping_status === "unmapped" || s.mapping_status === "partial" ? "var(--warn)" : "var(--accentText)";
          const text = skipped ? s.skip_reason ?? "skipped" : s.status === "CONFIRMED" ? "confirmed" : `${s.fields_mapped}/${s.fields_total} fields${s.needs_review ? ` · ${s.needs_review} to check` : ""}`;
          const includable = skipped && s.mapping_status === "non_claim_summary";
          return (
            <div key={s.id} style={{ boxShadow: "inset 0 -1px 0 var(--line)" }}>
            <button
              type="button"
              disabled={skipped}
              onClick={() => setActive(s.id)}
              aria-current={on ? "true" : undefined}
              className="grid grid-cols-[18px_1fr] gap-2.5 px-4 py-3 text-left transition-colors enabled:cursor-pointer enabled:hover:bg-[var(--accentTint)] disabled:opacity-60"
              style={{ background: on ? "var(--accentTint)" : "transparent", boxShadow: on ? "inset 2px 0 0 var(--accent)" : undefined }}
            >
              <span className="mt-0.5" style={{ color: tone }}>{s.status === "CONFIRMED" ? <CheckCircle size={16} weight="fill" /> : skipped ? <X size={16} /> : <Warning size={16} />}</span>
              <span className="flex min-w-0 flex-col">
                <span className="truncate text-[13.5px] font-medium">{s.sheet_name}</span>
                <span className="tnum text-[12px]" style={{ color: "var(--faint)" }}>
                  {s.row_count ? `${formatNumber(s.row_count)} rows · ` : ""}
                  {text}
                </span>
              </span>
            </button>
            {includable && (
              <div className="px-4 pb-3 pl-[46px]">
                <button type="button" className="tb-btn text-[12px]" onClick={() => setIncluded(s.id, true)} disabled={!!busy}>
                  {busy === `inc-${s.id}` ? "Including…" : "Include anyway"}
                </button>
              </div>
            )}
            </div>
          );
        })}
        <div className="p-3">
          {allDone ? (
            <button type="button" className="tb-btn tb-btn-solid w-full" onClick={process} disabled={busy === "process"}>
              {busy === "process" ? "Starting…" : processLabel}
              <ArrowRight size={14} />
            </button>
          ) : (
            <button type="button" className="tb-btn w-full" onClick={confirmAll} disabled={!!busy} title="Accept TrueBind’s proposal for every remaining sheet">
              {busy === "all" ? "Confirming…" : `Confirm all as proposed (${pending.length})`}
            </button>
          )}
        </div>
      </section>

      <section className="tb-card flex min-w-0 flex-col overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4" style={{ boxShadow: "0 1px 0 var(--line)" }}>
          <div className="flex min-w-0 flex-col">
            <span className="text-[15px] font-medium">{activeSheet ? activeSheet.sheet_name : allDone ? "All sheets resolved" : "Select a sheet"}</span>
            {activeSheet && (
              <span className="text-[12.5px]" style={{ color: "var(--faint)" }}>
                Header row {(activeSheet.header_row_index ?? 0) + 1} · {activeSheet.source_column_count ?? mapping?.headers.length ?? 0} source columns
                {toCheck ? ` · ${toCheck} field(s) to check` : ""}
              </span>
            )}
          </div>
          {mapping && active && (
            <button type="button" className="tb-btn" onClick={() => setShowAll((v) => !v)} aria-pressed={showAll}>
              {showAll ? `Show only the ${toCheck} to decide` : `Show all ${mapping.fields.length} fields`}
            </button>
          )}
        </div>
        {actionErr && (
          <div className="px-5 pt-4">
            <ErrorState title="That didn’t work" message={actionErr} />
          </div>
        )}
        {!active ? (
          <p className="m-0 px-5 py-6 text-[14px]" style={{ color: "var(--muted)" }}>
            {allDone ? "Every sheet is mapped or skipped. Produce the health report to validate every row." : "Choose a sheet on the left."}
          </p>
        ) : loadErr ? (
          <div className="p-5">
            <ErrorState title="Could not load this sheet" message={loadErr} />
          </div>
        ) : !mapping ? (
          <div className="p-5">
            <LoadingState label="Loading mapping" rows={8} />
          </div>
        ) : (
          <>
            <div className="flex items-center gap-2 px-5 py-3 text-[14px]" style={{ boxShadow: "0 1px 0 var(--line)", background: "var(--okT)" }}>
              <CheckCircle size={16} weight="fill" style={{ color: "var(--ok)" }} aria-hidden />
              <span>
                <span className="tnum font-medium">{autoMapped}</span> columns mapped automatically
                {toCheck ? <> · <span className="tnum font-medium">{toCheck}</span> to decide</> : " · nothing to decide"}
              </span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] border-collapse text-[13px]">
                <thead>
                  <tr className="text-left text-[11px] font-medium uppercase tracking-[.06em]" style={{ color: "var(--faint)" }}>
                    <th className="px-5 py-2.5 font-medium">Lloyd’s CRS field</th>
                    <th className="px-3 py-2.5 font-medium">Your column</th>
                    <th className="px-3 py-2.5 font-medium">Match</th>
                    <th className="px-5 py-2.5 font-medium">Sample values</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.length === 0 && (
                    <tr>
                      <td colSpan={4} className="px-5 py-6 text-center" style={{ color: "var(--muted)" }}>Every field was matched with high confidence. Confirm the sheet to continue.</td>
                    </tr>
                  )}
                  {visible.map((f) => {
                    const r = REVIEW[f.review_state ?? "UNMAPPED"] ?? REVIEW.UNMAPPED;
                    const changed = (choices[f.field_code] ?? null) !== (f.source_column ?? null);
                    const conflict = choices[f.field_code] && usedCols[choices[f.field_code]!] !== f.field_code;
                    return (
                      <tr key={f.field_code} style={{ boxShadow: "0 -1px 0 var(--line)" }}>
                        <td className="px-5 py-2.5 align-top">
                          <div className="font-medium">
                            {f.field_name}
                            {f.required && <span style={{ color: "var(--err)" }} title="Required"> *</span>}
                          </div>
                          <div className="tnum text-[11.5px]" style={{ color: "var(--faint)" }}>{f.field_code}</div>
                        </td>
                        <td className="px-3 py-2.5 align-top">
                          <select
                            className="tb-input !min-h-[34px] !py-1.5 text-[13px]"
                            aria-label={`Source column for ${f.field_name}`}
                            value={choices[f.field_code] ?? ""}
                            onChange={(e) => setChoices((p) => ({ ...p, [f.field_code]: e.target.value || null }))}
                            style={changed ? { boxShadow: "inset 0 0 0 1.5px var(--accent)" } : undefined}
                          >
                            <option value="">- not mapped -</option>
                            {mapping.headers.map((h) => (
                              <option key={h} value={h}>
                                {h}
                                {usedCols[h] && usedCols[h] !== f.field_code ? " (in use)" : ""}
                              </option>
                            ))}
                          </select>
                          {conflict && <div className="mt-1 text-[11.5px]" style={{ color: "var(--err)" }}>Also used by another field</div>}
                        </td>
                        <td className="px-3 py-2.5 align-top">
                          {changed ? <StatusPill tone="med">Your change</StatusPill> : <StatusPill tone={r.tone}>{r.label}</StatusPill>}
                          {!changed && f.source_column && (
                            <div className="tnum mt-1 text-[11.5px]" style={{ color: "var(--faint)" }}>
                              {f.confidence_score != null ? `${Math.round(f.confidence_score * (f.confidence_score <= 1 ? 100 : 1))}%` : ""}
                              {METHOD[f.mapping_state] ? ` · ${METHOD[f.mapping_state]}` : ""}
                              {f.evidence ? ` · ${f.evidence}` : ""}
                            </div>
                          )}
                        </td>
                        <td className="tnum max-w-[260px] truncate px-5 py-2.5 align-top text-[12px]" style={{ color: "var(--muted)" }}>
                          {f.sample_values.join(" · ") || "-"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {unmappedCols.length > 0 && (
              <div className="px-5 py-3 text-[12.5px]" style={{ color: "var(--muted)", boxShadow: "0 -1px 0 var(--line)" }}>
                Not mapped, kept on every row: {unmappedCols.join(", ")}
              </div>
            )}
            <div className="sticky bottom-0 flex flex-wrap items-center gap-3 px-5 py-3" style={{ background: "var(--surface)", boxShadow: "0 -1px 0 var(--line)" }}>
              <span className="flex-1 text-[12.5px]" style={{ color: "var(--faint)" }}>Fields marked * are required. Unmapped source columns are kept on every row.</span>
              {activeSheet && activeSheet.status !== "SKIPPED" && (
                <button type="button" className="tb-btn" onClick={() => setIncluded(activeSheet.id, false)} disabled={!!busy} title="Leave this sheet out of the health report; you can include it again">
                  {busy === `inc-${activeSheet.id}` ? "Skipping…" : "Skip sheet"}
                </button>
              )}
              <button type="button" className="tb-btn tb-btn-solid" onClick={confirmActive} disabled={busy === "confirm" || activeSheet?.status === "SKIPPED"}>
                <Check size={14} />
                {busy === "confirm" ? "Saving…" : activeSheet?.status === "CONFIRMED" ? "Save changes" : "Confirm sheet"}
              </button>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
