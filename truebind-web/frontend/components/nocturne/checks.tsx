"use client";

import Link from "next/link";
import { useState } from "react";
import { CaretDown, CaretRight, ShieldCheck } from "@phosphor-icons/react";
import { api, ApiError } from "@/lib/api";
import type { ModuleFinding, ModuleRun, Report } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { useUi } from "@/lib/ui";
import { hasPermission } from "@/lib/auth";
import { decimalMoney, findingWhere, moduleState } from "@/lib/findings";
import { formatDateTime, formatNumber } from "@/lib/formatters";
import { useMe } from "@/components/auth/AuthGate";
import { EmptyState, ErrorState, LoadingState, StatusPill } from "./ui";
import { SEV } from "./status";
import type { Severity } from "@/lib/types";

const TONE = { good: "ok", warn: "warn", bad: "err", neutral: "muted" } as const;

/** Binder compliance, leakage and sanctions modules for one report — all real
 * backend check runs. Each says what it assessed and what it could not. */
export function ChecksPanel({ report }: { report: Report }) {
  const me = useMe();
  const canWrite = hasPermission(me?.permissions ?? [], "data:write");
  const runs = useApi(() => api.listChecks(report.id), [report.id]);
  if (runs.error) return <ErrorState title="Checks could not be loaded" message={runs.error} onRetry={runs.reload} />;
  if (!runs.data) return <LoadingState label="Loading checks" rows={4} />;
  if (!runs.data.length) return <div className="tb-card"><EmptyState icon={<ShieldCheck />} title="No check modules" body="No check modules are enabled for this organisation’s plan." /></div>;
  return (
    <div className="flex flex-col gap-4">
      {runs.data.map((run) => (
        <ModuleCard key={run.module} run={run} report={report} canWrite={canWrite} onRan={runs.reload} extra={run.module === "binder" ? <BinderPicker report={report} canWrite={canWrite} onChanged={runs.reload} /> : undefined} />
      ))}
    </div>
  );
}

function ModuleCard({ run, report, canWrite, onRan, extra }: { run: ModuleRun; report: Report; canWrite: boolean; onRan: () => void; extra?: React.ReactNode }) {
  const { toast } = useUi();
  const findings = useApi(() => api.listModuleFindings(report.id, { module: run.module, limit: 200 }), [report.id, run.module, run.ran_at]);
  const [busy, setBusy] = useState(false);
  const meta = moduleState(run.state);
  const rerun = async () => {
    setBusy(true);
    try {
      await api.runCheck(report.id, run.module);
      toast(`${run.label} ran again · recorded in the audit trail`, "ok");
      onRan();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "The check could not be run.", "err");
    } finally {
      setBusy(false);
    }
  };
  const list = findings.data?.items ?? [];
  return (
    <section className="tb-card flex flex-col gap-4 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <span className="text-[15px] font-medium">{run.label}</span>
          <span className="max-w-[760px] text-[12.5px]" style={{ color: "var(--muted)" }}>{run.coverage_statement}</span>
        </div>
        <div className="flex items-center gap-2">
          <StatusPill tone={TONE[meta.tone]}>{meta.label}</StatusPill>
          {run.open_count > 0 && <StatusPill tone="warn">{formatNumber(run.open_count)} open</StatusPill>}
          {canWrite && (
            <button type="button" className="tb-btn tb-btn-ghost !py-1.5 text-[12.5px]" onClick={() => void rerun()} disabled={busy}>
              {busy ? "Running…" : "Run again"}
            </button>
          )}
        </div>
      </div>
      {extra}
      {run.reason && run.state !== "ASSESSED" && <span className="text-[12.5px]" style={{ color: "var(--warn)" }}>{run.reason}</span>}
      {(Object.keys(run.exposure ?? {}).length > 0 || run.unpriced_findings > 0) && (
        <span className="text-[13px]">
          <b className="font-medium">Open exposure:</b> {Object.entries(run.exposure).map(([c, a]) => decimalMoney(a, c)).join(" · ") || "none with a stated currency"}
          {run.unpriced_findings > 0 && <span style={{ color: "var(--muted)" }}> · {run.unpriced_findings} finding(s) without a stated currency, not totalled</span>}
        </span>
      )}
      {run.rules.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[520px] border-collapse text-[12.5px]">
            <caption className="sr-only">{run.label}: rows assessed per rule</caption>
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-[.06em]" style={{ color: "var(--faint)" }}>
                <th className="py-2 pr-3 font-medium">Rule</th>
                <th className="px-3 py-2 text-right font-medium">Assessed</th>
                <th className="py-2 pl-3 font-medium">Not assessed</th>
              </tr>
            </thead>
            <tbody>
              {run.rules.map((r) => (
                <tr key={r.code} style={{ boxShadow: "0 -1px 0 var(--line)" }}>
                  <td className="py-2 pr-3">{r.label}</td>
                  <td className="tnum px-3 py-2 text-right">{formatNumber(r.assessed)}</td>
                  <td className="py-2 pl-3" style={{ color: r.not_assessed ? "var(--warn)" : "var(--muted)" }}>{r.not_assessed ? `${formatNumber(r.not_assessed)} — ${r.reasons.join("; ")}` : "0"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {findings.error ? (
        <ErrorState title="Findings could not be loaded" message={findings.error} onRetry={findings.reload} />
      ) : !findings.data ? (
        <LoadingState label="Loading findings" rows={2} />
      ) : list.length === 0 ? (
        <span className="text-[13px]" style={{ color: "var(--muted)" }}>{run.state === "ASSESSED" ? "No findings: every assessed row passed." : run.state === "PARTIAL" ? "No findings in the rows that could be assessed." : "No findings — nothing was assessed yet."}</span>
      ) : (
        <ul className="m-0 flex list-none flex-col overflow-hidden rounded-md p-0" style={{ boxShadow: "inset 0 0 0 1px var(--line)" }} aria-label={`${run.label} findings`}>
          {list.map((f) => (
            <FindingRow key={f.id} f={f} reportId={report.id} canWrite={canWrite} onChange={findings.reload} />
          ))}
        </ul>
      )}
      {(findings.data?.total ?? 0) > list.length && <span className="text-[12px]" style={{ color: "var(--faint)" }}>Showing {list.length} of {formatNumber(findings.data?.total ?? 0)} findings.</span>}
    </section>
  );
}

function FindingRow({ f, reportId, canWrite, onChange }: { f: ModuleFinding; reportId: string; canWrite: boolean; onChange: () => void }) {
  const { toast } = useUi();
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const sev = SEV[(f.severity?.toUpperCase() as Severity) ?? "MEDIUM"] ?? SEV.MEDIUM;
  const decide = async (d: "CONFIRMED" | "DISMISSED" | "OPEN") => {
    setBusy(true);
    try {
      await api.disposeFinding(reportId, f.id, d, note);
      setNote("");
      toast(d === "OPEN" ? "Finding reopened" : `Finding ${d.toLowerCase()} · recorded in the audit trail`, "ok");
      onChange();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "The decision could not be saved.", "err");
    } finally {
      setBusy(false);
    }
  };
  return (
    <li style={{ boxShadow: "0 1px 0 var(--line)" }}>
      <button type="button" className="grid w-full cursor-pointer grid-cols-[16px_auto_minmax(0,1fr)_auto] items-center gap-3 px-4 py-3 text-left hover:bg-[var(--accentTint)]" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        {open ? <CaretDown size={13} /> : <CaretRight size={13} />}
        <StatusPill tone={f.status === "FAIL" ? sev.tone : "warn"}>{f.status === "FAIL" ? "Breach" : "Review"}</StatusPill>
        <span className="flex min-w-0 flex-col">
          <span className="truncate text-[13px] font-medium">{f.title}</span>
          <span className="truncate text-[12px]" style={{ color: "var(--faint)" }}>{findingWhere(f)}{f.claim_reference ? ` · ${f.claim_reference}` : ""}</span>
        </span>
        <span className="flex items-center gap-2">
          {f.amount != null && <span className="tnum text-[12.5px]">{decimalMoney(f.amount, f.currency)}</span>}
          {f.disposition !== "OPEN" && <StatusPill tone={f.disposition === "CONFIRMED" ? "err" : "muted"}>{f.disposition.toLowerCase()}</StatusPill>}
        </span>
      </button>
      {open && (
        <div className="flex flex-col gap-3 px-4 pb-4 pl-[44px]">
          <p className="m-0 text-[13px] leading-[1.55]">{f.explanation}</p>
          {f.evidence && Object.keys(f.evidence).length > 0 && (
            <dl className="tnum m-0 grid grid-cols-[minmax(84px,160px)_minmax(0,1fr)] [overflow-wrap:anywhere] gap-y-1 text-[12.5px]">
              {Object.entries(f.evidence).map(([k, v]) => (
                <div key={k} className="contents">
                  <dt style={{ color: "var(--faint)" }}>{k.replace(/_/g, " ")}</dt>
                  <dd className="m-0">{Array.isArray(v) ? v.join(", ") : String(v)}</dd>
                </div>
              ))}
            </dl>
          )}
          {f.disposition !== "OPEN" && (
            <span className="text-[12.5px]" style={{ color: "var(--muted)" }}>
              {f.disposition === "CONFIRMED" ? "Confirmed" : "Dismissed"} by {f.disposed_by} · {formatDateTime(f.disposed_at)}
              {f.disposition_note ? ` — “${f.disposition_note}”` : ""}
            </span>
          )}
          {canWrite && (
            <div className="flex flex-wrap items-end gap-2">
              <div className="min-w-[220px] flex-1">
                <label className="tb-label" htmlFor={`note-${f.id}`}>Note {f.disposition === "OPEN" ? "(required to dismiss)" : ""}</label>
                <input id={`note-${f.id}`} className="tb-input" value={note} maxLength={1000} onChange={(e) => setNote(e.target.value)} />
              </div>
              {f.disposition === "OPEN" ? (
                <>
                  <button type="button" className="tb-btn tb-btn-primary" disabled={busy} onClick={() => void decide("CONFIRMED")}>Confirm</button>
                  <button type="button" className="tb-btn" disabled={busy || !note.trim()} onClick={() => void decide("DISMISSED")}>Dismiss</button>
                </>
              ) : (
                <button type="button" className="tb-btn" disabled={busy} onClick={() => void decide("OPEN")}>Reopen</button>
              )}
            </div>
          )}
        </div>
      )}
    </li>
  );
}

function BinderPicker({ report, canWrite, onChanged }: { report: Report; canWrite: boolean; onChanged: () => void }) {
  const { toast } = useUi();
  const binders = useApi(() => api.listBinders(), []);
  const [value, setValue] = useState(report.binder_id ?? "");
  if (!binders.data) return binders.error ? <span className="text-[12.5px]" style={{ color: "var(--err)" }}>Binders could not be loaded.</span> : <LoadingState label="Loading binders" rows={1} />;
  if (!binders.data.length)
    return (
      <span className="text-[13px]" style={{ color: "var(--muted)" }}>
        No binders set up yet —{" "}
        <Link href="/settings?tab=binders" className="underline" style={{ color: "var(--accentText)" }}>add one under Settings → Binders</Link> to check this report against it.
      </span>
    );
  const save = async (id: string) => {
    setValue(id);
    try {
      await api.assignBinder(report.id, id || null);
      toast(id ? "Binder assigned · checks re-run" : "Binder removed", "ok");
      onChanged();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "The binder could not be assigned.", "err");
    }
  };
  return (
    <div className="max-w-[520px]">
      <label className="tb-label" htmlFor="binder-pick">Binder this bordereau is reported under</label>
      <select id="binder-pick" className="tb-input" value={value} disabled={!canWrite} onChange={(e) => void save(e.target.value)}>
        <option value="">No binder</option>
        {binders.data.map((b) => (
          <option key={b.id} value={b.id}>
            {b.name}
            {b.umr ? ` (${b.umr})` : ""} · {b.inception_date} to {b.expiry_date}
          </option>
        ))}
      </select>
    </div>
  );
}
