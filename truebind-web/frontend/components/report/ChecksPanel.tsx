"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { decimalMoney, findingWhere, moduleState } from "@/lib/findings";
import { formatDateTime } from "@/lib/formatters";
import type { ModuleFinding, ModuleRun, Report } from "@/lib/types";
import { EmptyState, ErrorState, EvidencePanel, Panel, Pill, SkeletonRows, SourceReference, severityTone, useToast } from "@/components/ds";
import { Button } from "@/components/ui/Button";
import styles from "./ChecksPanel.module.css";

function errorText(err: unknown): string {
  return err instanceof ApiError ? err.message : "Please try again.";
}

function FindingRow({ f, reportId, canWrite, onChange }: { f: ModuleFinding; reportId: string; canWrite: boolean; onChange: () => void }) {
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  async function decide(d: "CONFIRMED" | "DISMISSED" | "OPEN") {
    setBusy(true);
    try {
      await api.disposeFinding(reportId, f.id, d, note);
      setNote("");
      onChange();
    } catch (err) {
      toast({ tone: "bad", title: "Decision not saved", body: errorText(err) });
    } finally {
      setBusy(false);
    }
  }
  const noteId = `note-${f.id}`;
  return (
    <li className={styles.finding}>
      <button type="button" className={styles.findingHead} aria-expanded={open} onClick={() => setOpen(!open)}>
        <Pill tone={f.status === "FAIL" ? severityTone(f.severity) : "warn"}>{f.status === "FAIL" ? "Breach" : "Review"}</Pill>
        <span className={styles.findingTitle}>{f.title}</span>
        <span className={styles.where}>{findingWhere(f)}</span>
        {f.amount != null && <span className={styles.amount}>{decimalMoney(f.amount, f.currency)}</span>}
        {f.disposition !== "OPEN" && <Pill tone={f.disposition === "CONFIRMED" ? "bad" : "neutral"}>{f.disposition.toLowerCase()}</Pill>}
      </button>
      {open && (
        <div className={styles.detail}>
          <p className={styles.explanation}>{f.explanation}</p>
          <SourceReference sheet={f.sheet_name ?? undefined} row={f.row_number ?? undefined} column={f.source_column ?? undefined} />
          {f.evidence && Object.keys(f.evidence).length > 0 && (
            <EvidencePanel items={Object.entries(f.evidence).map(([k, v]) => ({ label: k.replace(/_/g, " "), value: Array.isArray(v) ? v.join(", ") : String(v) }))} />
          )}
          {f.disposition !== "OPEN" && (
            <p className={styles.small}>{f.disposition === "CONFIRMED" ? "Confirmed" : "Dismissed"} by {f.disposed_by} · {formatDateTime(f.disposed_at)}{f.disposition_note ? ` — “${f.disposition_note}”` : ""}</p>
          )}
          {canWrite && (
            <div className={styles.decide}>
              <label htmlFor={noteId} className={styles.label}>Note {f.disposition === "OPEN" ? "(required to dismiss)" : ""}</label>
              <input id={noteId} className={styles.input} value={note} maxLength={1000} onChange={(e) => setNote(e.target.value)} />
              <div className={styles.actions}>
                {f.disposition === "OPEN" ? <>
                  <Button size="sm" loading={busy} onClick={() => decide("CONFIRMED")}>Confirm</Button>
                  <Button size="sm" variant="ghost" loading={busy} disabled={!note.trim()} onClick={() => decide("DISMISSED")}>Dismiss</Button>
                </> : <Button size="sm" variant="ghost" loading={busy} onClick={() => decide("OPEN")}>Reopen</Button>}
              </div>
            </div>
          )}
        </div>
      )}
    </li>
  );
}

function ModuleCard({ run, report, canWrite, onRan, extra }: { run: ModuleRun; report: Report; canWrite: boolean; onRan: () => void; extra?: React.ReactNode }) {
  const toast = useToast();
  const findings = useApi(() => api.listModuleFindings(report.id, { module: run.module, limit: 200 }), [report.id, run.module, run.ran_at]);
  const [busy, setBusy] = useState(false);
  const meta = moduleState(run.state);
  async function rerun() {
    setBusy(true);
    try { await api.runCheck(report.id, run.module); onRan(); }
    catch (err) { toast({ tone: "bad", title: "Check not run", body: errorText(err) }); }
    finally { setBusy(false); }
  }
  const list = findings.data?.items ?? [];
  return (
    <Panel title={run.label} icon="check" subtitle={run.coverage_statement}
      actions={<div className={styles.actions}><Pill tone={meta.tone}>{meta.label}</Pill>
        {canWrite && report.status === "COMPLETE" && <Button size="sm" variant="ghost" loading={busy} onClick={rerun}>Run again</Button>}</div>}>
      {extra}
      {run.rules.length > 0 && (
        <table className={styles.rules}>
          <caption className={styles.srOnly}>{run.label}: rows assessed per rule</caption>
          <thead><tr><th scope="col">Rule</th><th scope="col">Assessed</th><th scope="col">Not assessed</th></tr></thead>
          <tbody>{run.rules.map((r) => (
            <tr key={r.code}><td>{r.label}</td><td>{r.assessed.toLocaleString("en-GB")}</td>
              <td>{r.not_assessed ? <span title={r.reasons.join("; ")}>{r.not_assessed.toLocaleString("en-GB")} — {r.reasons.join("; ")}</span> : "0"}</td></tr>
          ))}</tbody>
        </table>
      )}
      {findings.error ? <ErrorState message={findings.error} onRetry={findings.reload} />
        : findings.loading && !findings.data ? <SkeletonRows rows={2} />
        : list.length === 0 ? <p className={styles.small}>{run.state === "ASSESSED" ? "No findings: every assessed row passed." : run.state === "PARTIAL" ? "No findings in the rows that could be assessed." : "No findings — nothing was assessed."}</p>
        : <ul className={styles.findings} aria-label={`${run.label} findings`}>
            {list.map((f) => <FindingRow key={f.id} f={f} reportId={report.id} canWrite={canWrite} onChange={findings.reload} />)}
          </ul>}
      {(findings.data?.total ?? 0) > list.length && <p className={styles.small}>Showing {list.length} of {findings.data?.total.toLocaleString("en-GB")} findings.</p>}
    </Panel>
  );
}

function BinderPicker({ report, canWrite, onChanged }: { report: Report; canWrite: boolean; onChanged: () => void }) {
  const toast = useToast();
  const binders = useApi(() => api.listBinders(), []);
  const [value, setValue] = useState(report.binder_id ?? "");
  if (binders.loading && !binders.data) return <SkeletonRows rows={1} />;
  const list = binders.data ?? [];
  if (!list.length) return <p className={styles.small}>No binders set up yet — add one under Settings → Binders to check this report against it.</p>;
  async function save(id: string) {
    setValue(id);
    try { await api.assignBinder(report.id, id || null); onChanged(); }
    catch (err) { toast({ tone: "bad", title: "Binder not assigned", body: errorText(err) }); }
  }
  return (
    <div className={styles.decide}>
      <label htmlFor="binder-pick" className={styles.label}>Binder this bordereau is reported under</label>
      <select id="binder-pick" className={styles.input} value={value} disabled={!canWrite} onChange={(e) => save(e.target.value)}>
        <option value="">No binder</option>
        {list.map((b) => <option key={b.id} value={b.id}>{b.name}{b.umr ? ` (${b.umr})` : ""} · {b.inception_date} to {b.expiry_date}</option>)}
      </select>
    </div>
  );
}

export function ChecksPanel({ report, canWrite }: { report: Report; canWrite: boolean }) {
  const runs = useApi(() => api.listChecks(report.id), [report.id]);
  if (runs.error) return <ErrorState title="Checks could not be loaded" message={runs.error} onRetry={runs.reload} />;
  if (!runs.data) return <Panel><SkeletonRows rows={3} /></Panel>;
  if (!runs.data.length) return <Panel><EmptyState icon="check" title="No check modules" body="No check modules are enabled for this organisation." /></Panel>;
  return (
    <div className={styles.stack}>
      {runs.data.map((run) => (
        <ModuleCard key={run.module} run={run} report={report} canWrite={canWrite} onRan={runs.reload}
          extra={run.module === "binder" ? <BinderPicker report={report} canWrite={canWrite} onChanged={runs.reload} /> : undefined} />
      ))}
    </div>
  );
}
