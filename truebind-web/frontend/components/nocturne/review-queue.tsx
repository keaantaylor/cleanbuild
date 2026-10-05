"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowRight, CaretDown, CaretRight, CheckCircle } from "@phosphor-icons/react";
import { api, ApiError } from "@/lib/api";
import type { BulkAction, Issue, RootCause } from "@/lib/types";
import { formatMoney, formatNumber } from "@/lib/formatters";
import { ErrorState, LoadingState } from "@/components/nocturne/ui";

/* Guided review: one root cause per screen. Every issue that shares a cause is
   decided at once on the server; the browser sends only the cause key. */

const STATE = {
  FAIL: { label: "Requires reconciliation", fg: "var(--err)", bg: "var(--errT)" },
  REVIEW: { label: "Undetermined", fg: "var(--warn)", bg: "var(--warnT)" },
  NOT_EVALUABLE: { label: "Undetermined", fg: "var(--warn)", bg: "var(--warnT)" },
} as const;

const ACTION_DONE: Record<BulkAction, string> = {
  apply_safe_fix: "Safe fix applied",
  send_to_sender: "Sent to sender",
  override: "Accepted as reported",
  resolve: "Resolved",
};

function value(v: number | string | null | undefined): string {
  if (v === null || v === undefined || v === "") return "-";
  return typeof v === "number" ? v.toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : String(v);
}

function where(i: Pick<Issue, "sheet" | "cell" | "row">): string {
  if (i.cell && !i.cell.startsWith("row ")) return `${i.sheet ?? "Sheet"}!${i.cell}`;
  return `${i.sheet ?? "Sheet"} row ${i.row ?? "?"}`;
}

function amounts(g: RootCause): string {
  return g.amount_affected.map((a) => formatMoney(a.amount, a.currency)).join(" + ");
}

export function ReviewQueue({ reportId, canWrite = true, onShowCell }: { reportId: string; canWrite?: boolean; onShowCell?: (sheet: string | null, cell: string) => void }) {
  const [groups, setGroups] = useState<RootCause[] | null>(null);
  const [order, setOrder] = useState<string[]>([]); // the queue, fixed at load
  const [idx, setIdx] = useState(0);
  const [results, setResults] = useState<Record<string, string>>({});
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(
    () =>
      api.listIssues(reportId, { limit: 1 }).then(
        (r) => {
          setGroups(r.root_causes);
          setOrder((prev) => (prev.length ? prev : r.root_causes.filter((g) => g.open > 0).map((g) => g.root_cause)));
          setErr(null);
        },
        (e) => setErr(e instanceof ApiError ? e.message : "Could not load the issues."),
      ),
    [reportId],
  );

  useEffect(() => {
    let cancelled = false;
    api.listIssues(reportId, { limit: 1 }).then(
      (r) => {
        if (cancelled) return;
        setGroups(r.root_causes);
        setOrder(r.root_causes.filter((g) => g.open > 0).map((g) => g.root_cause));
      },
      (e) => { if (!cancelled) setErr(e instanceof ApiError ? e.message : "Could not load the issues."); },
    );
    return () => { cancelled = true; };
  }, [reportId]);

  if (err) return <ErrorState title="Could not load the review" message={err} onRetry={() => void load()} />;
  if (!groups) return <LoadingState label="Loading issues" rows={5} />;

  const byKey = Object.fromEntries(groups.map((g) => [g.root_cause, g]));
  const totalRows = groups.reduce((n, g) => n + g.count, 0);

  if (order.length === 0 || idx >= order.length) {
    const decided = Object.keys(results).length;
    return (
      <section className="tb-card flex flex-col gap-3 p-6" aria-live="polite">
        <span className="flex items-center gap-2 text-[17px] font-semibold" style={{ color: "var(--ok)" }}>
          <CheckCircle size={20} weight="fill" aria-hidden /> {order.length === 0 ? "Nothing to review" : "Review complete"}
        </span>
        <p className="m-0 text-[14px]" style={{ color: "var(--muted)" }}>
          {order.length === 0
            ? "Every finding is closed, or the file has none."
            : `${decided} decision${decided === 1 ? "" : "s"} covered ${formatNumber(totalRows)} findings.`}
        </p>
        {decided > 0 && (
          <ul className="m-0 flex list-none flex-col p-0 text-[13.5px]">
            {order.map((k) => (
              <li key={k} className="flex justify-between gap-4 py-1.5" style={{ boxShadow: "0 1px 0 var(--line)" }}>
                <span>{byKey[k]?.label ?? k}</span>
                <span style={{ color: "var(--muted)" }}>{results[k] ?? "Skipped"}</span>
              </li>
            ))}
          </ul>
        )}
        {order.length > 0 && (
          <button type="button" className="tb-btn self-start" onClick={() => setIdx(0)}>Go through again</button>
        )}
      </section>
    );
  }

  const key = order[idx];
  const g = byKey[key];
  return (
    <IssueScreen
      key={key}
      reportId={reportId}
      onShowCell={onShowCell}
      g={g}
      byKey={byKey}
      position={idx + 1}
      total={order.length}
      canWrite={canWrite}
      result={results[key]}
      onDecided={async (label) => {
        setResults((r) => ({ ...r, [key]: label }));
        await load();
        setIdx((i) => i + 1);
      }}
      onSkip={() => setIdx((i) => i + 1)}
      onBack={idx > 0 ? () => setIdx((i) => i - 1) : undefined}
    />
  );
}

function IssueScreen({ reportId, g, byKey, position, total, canWrite, result, onDecided, onSkip, onBack, onShowCell }: {
  onShowCell?: (sheet: string | null, cell: string) => void;
  reportId: string; g: RootCause | undefined; byKey: Record<string, RootCause>; position: number; total: number; canWrite: boolean;
  result?: string; onDecided: (label: string) => Promise<void>; onSkip: () => void; onBack?: () => void;
}) {
  const [first, setFirst] = useState<Issue | null>(null);
  const [cells, setCells] = useState<Issue[] | null>(null);
  const [showCells, setShowCells] = useState(false);
  const [overriding, setOverriding] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState<BulkAction | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const issueId = g?.first_open_issue_id ?? g?.first_issue_id;
  useEffect(() => {
    if (!issueId) return;
    let cancelled = false;
    api.getIssue(reportId, issueId).then((i) => { if (!cancelled) setFirst(i); }).catch(() => undefined);
    return () => { cancelled = true; };
  }, [reportId, issueId]);

  useEffect(() => {
    if (!showCells || cells || !g) return;
    api.listIssues(reportId, { root_cause: g.root_cause, limit: 200 }).then((r) => setCells(r.items)).catch(() => setCells([]));
  }, [showCells, cells, g, reportId]);

  if (!g) return null;
  const st = STATE[g.outcome as keyof typeof STATE] ?? STATE.REVIEW;
  const cause = g.caused_by[0] ? byKey[g.caused_by[0].root_cause] : undefined;
  const closed = g.open === 0;

  async function decide(action: BulkAction, note?: string) {
    setBusy(action);
    setErr(null);
    try {
      const r = await api.decideRootCause(reportId, g!.root_cause, action, note);
      const rc = r.recheck;
      const verified = !rc ? "" : rc.status === "queued" ? " · re-check queued" : rc.status !== "ran" ? " · not re-checked" : ` · re-checked: ${rc.passed} fixed${rc.still_failing ? `, ${rc.still_failing} still failing` : ""}${rc.new_findings ? `, ${rc.new_findings} new` : ""}`;
      await onDecided(`${ACTION_DONE[action]} · ${formatNumber(r.changed)} finding${r.changed === 1 ? "" : "s"}${r.skipped ? ` (${r.skipped} unchanged)` : ""}${verified}`);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "That decision was not saved.");
      setBusy(null);
    }
  }

  return (
    <section className="tb-card flex flex-col" aria-labelledby="issue-title">
      {/* WORK */}
      <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-3 text-[13px]" style={{ boxShadow: "0 1px 0 var(--line)", color: "var(--muted)" }}>
        <span className="tnum font-medium" style={{ color: "var(--text)" }}>Issue {position} of {total}</span>
        <div className="h-1.5 min-w-[120px] flex-1 overflow-hidden rounded-full" style={{ background: "var(--line)" }} aria-hidden>
          <div className="h-full" style={{ width: `${((position - 1) / total) * 100}%`, background: "var(--accent)" }} />
        </div>
        {onBack && <button type="button" className="tb-btn" onClick={onBack}>Previous</button>}
      </div>

      {/* PROBLEM */}
      <div className="flex flex-col gap-2 px-6 pt-5">
        <span className="self-start rounded px-2 py-0.5 text-[12.5px] font-semibold" style={{ background: st.bg, color: st.fg }}>{st.label}</span>
        <h2 id="issue-title" className="m-0 text-[20px] font-semibold leading-tight">{g.label}</h2>
        <p className="tnum m-0 text-[14.5px]">
          {formatNumber(g.rows)} row{g.rows === 1 ? "" : "s"}
          {g.amount_affected.length > 0 && <> · <b className="font-semibold">{amounts(g)}</b> affected</>}
          {g.open < g.count && <span style={{ color: "var(--muted)" }}> · {formatNumber(g.count - g.open)} already closed</span>}
        </p>
        {g.kind === "symptom" && cause ? (
          <p className="m-0 rounded px-3 py-2 text-[13.5px]" style={{ background: "var(--surface2)", boxShadow: "inset 0 0 0 1px var(--line)" }}>
            Downstream symptom of <b className="font-semibold">{cause.label}</b>. Fixing that is expected to clear these on the next run.
          </p>
        ) : g.symptoms > 0 && cause ? (
          <p className="m-0 text-[13.5px]" style={{ color: "var(--muted)" }}>{formatNumber(g.symptoms)} of these follow from {cause.label}.</p>
        ) : null}
      </div>

      {/* EVIDENCE */}
      <div className="flex flex-col gap-3 px-6 py-5">
        {first ? (
          <>
            <dl className="m-0 grid grid-cols-[max-content_minmax(0,1fr)] gap-x-6 gap-y-1.5 text-[14px]">
              <dt style={{ color: "var(--muted)" }}>Cell</dt>
              <dd className="m-0 font-medium">
                {where(first)}{first.column ? ` · ${first.column}` : ""}{first.claim_reference ? ` · claim ${first.claim_reference}` : ""}
                {onShowCell && first.cell && !first.cell.startsWith("row ") && (
                  <button type="button" className="ml-2 cursor-pointer text-[13px] font-medium underline underline-offset-2" style={{ color: "var(--accentText)" }} onClick={() => onShowCell(first.sheet, first.cell!)}>Show in workbook</button>
                )}
              </dd>
              <dt style={{ color: "var(--muted)" }}>Rule</dt>
              <dd className="m-0 font-[family-name:var(--font-mono)] text-[13px]">{(first.rule ?? "").toUpperCase()} v{first.rule_version ?? "1.0"}</dd>
              {first.lineage?.original_value != null && (<><dt style={{ color: "var(--muted)" }}>In the file</dt><dd className="m-0">{first.lineage.original_value}</dd></>)}
            </dl>
            {(first.expected != null || first.actual != null) && (
              <table className="tnum w-full max-w-[520px] border-collapse text-[14px]">
                <thead>
                  <tr className="text-[12px]" style={{ color: "var(--muted)" }}>
                    <th className="py-1 text-right font-medium">Expected</th>
                    <th className="py-1 text-right font-medium">Actual</th>
                    <th className="py-1 text-right font-medium">Difference</th>
                  </tr>
                </thead>
                <tbody>
                  <tr style={{ boxShadow: "0 -1px 0 var(--line)" }}>
                    <td className="py-1.5 text-right">{value(first.expected)}</td>
                    <td className="py-1.5 text-right font-semibold">{value(first.actual)}</td>
                    <td className="py-1.5 text-right" style={{ color: first.difference ? "var(--err)" : undefined }}>{value(first.difference)}</td>
                  </tr>
                </tbody>
              </table>
            )}
            {(first.sentence || first.evidence) && <p className="m-0 text-[14px]">{first.sentence || first.evidence}</p>}
          </>
        ) : (
          <LoadingState label="Loading evidence" rows={2} />
        )}
        <button type="button" className="flex cursor-pointer items-center gap-1.5 self-start text-[13.5px] font-medium" style={{ color: "var(--accentText)" }} onClick={() => setShowCells((v) => !v)} aria-expanded={showCells}>
          {showCells ? <CaretDown size={14} /> : <CaretRight size={14} />} All {formatNumber(g.count)} affected cells
        </button>
        {showCells && (cells ? <CellTable cells={cells} more={g.count - cells.length} /> : <LoadingState label="Loading cells" rows={3} />)}
      </div>

      {/* ACTION */}
      <div className="flex flex-col gap-3 px-6 py-4" style={{ boxShadow: "0 -1px 0 var(--line)", background: "var(--surface2)" }}>
        {err && <ErrorState title="Not saved" message={err} />}
        {result && <p className="m-0 text-[13.5px]" style={{ color: "var(--ok)" }}>Decided: {result}</p>}
        <p className="m-0 text-[13.5px]" style={{ color: "var(--muted)" }}>{g.fix}</p>
        {overriding ? (
          <form className="flex flex-col gap-2" onSubmit={(e) => { e.preventDefault(); if (reason.trim()) void decide("override", reason.trim()); }}>
            <label className="text-[13.5px] font-medium" htmlFor="override-reason">Why are these values accepted as reported?</label>
            <textarea id="override-reason" className="tb-input min-h-[72px]" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={2000} required />
            <div className="flex flex-wrap gap-2">
              <button type="submit" className="tb-btn tb-btn-solid min-h-[40px] px-4 text-[14px]" disabled={!reason.trim() || !!busy}>{busy === "override" ? "Saving…" : `Accept ${formatNumber(g.open)} as reported`}</button>
              <button type="button" className="tb-btn min-h-[40px] px-4 text-[14px]" onClick={() => setOverriding(false)}>Cancel</button>
            </div>
          </form>
        ) : (
          <div className="flex flex-wrap items-center gap-2">
            {!closed && canWrite && g.auto_fix && (
              <button type="button" className="tb-btn tb-btn-solid min-h-[40px] px-4 text-[14px]" disabled={!!busy} onClick={() => void decide("apply_safe_fix")}>
                {busy === "apply_safe_fix" ? "Applying…" : `Apply safe fix to ${formatNumber(g.open)}`}
              </button>
            )}
            {!closed && canWrite && (
              <button type="button" className={`tb-btn min-h-[40px] px-4 text-[14px] ${g.auto_fix ? "" : "tb-btn-solid"}`} disabled={!!busy} onClick={() => void decide("send_to_sender")}>
                {busy === "send_to_sender" ? "Saving…" : "Send to sender"}
              </button>
            )}
            {!closed && canWrite && (
              <button type="button" className="tb-btn min-h-[40px] px-4 text-[14px]" disabled={!!busy} onClick={() => setOverriding(true)}>Override</button>
            )}
            <button type="button" className="tb-btn min-h-[40px] px-4 text-[14px]" disabled={!!busy} onClick={onSkip}>
              {closed ? "Next" : "Skip for now"} <ArrowRight size={14} />
            </button>
          </div>
        )}
      </div>
    </section>
  );
}

function CellTable({ cells, more }: { cells: Issue[]; more: number }) {
  return (
    <div className="max-h-[320px] overflow-auto rounded" style={{ boxShadow: "inset 0 0 0 1px var(--line)" }}>
      <table className="tnum w-full border-collapse text-[13px]">
        <thead className="sticky top-0" style={{ background: "var(--surface)" }}>
          <tr className="text-[12px]" style={{ color: "var(--muted)" }}>
            <th className="px-3 py-1.5 text-left font-medium">Cell</th>
            <th className="px-3 py-1.5 text-left font-medium">Claim</th>
            <th className="px-3 py-1.5 text-right font-medium">Expected</th>
            <th className="px-3 py-1.5 text-right font-medium">Actual</th>
            <th className="px-3 py-1.5 text-right font-medium">Difference</th>
            <th className="px-3 py-1.5 text-left font-medium">Status</th>
          </tr>
        </thead>
        <tbody>
          {cells.map((c) => (
            <tr key={c.id} style={{ boxShadow: "0 -1px 0 var(--line)" }}>
              <td className="px-3 py-1 font-[family-name:var(--font-mono)] text-[12.5px]">{where(c)}</td>
              <td className="px-3 py-1">{c.claim_reference ?? "-"}</td>
              <td className="px-3 py-1 text-right">{value(c.expected)}</td>
              <td className="px-3 py-1 text-right">{value(c.actual)}</td>
              <td className="px-3 py-1 text-right">{value(c.difference)}</td>
              <td className="px-3 py-1" style={{ color: "var(--muted)" }}>{c.status.replaceAll("_", " ").toLowerCase()}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {more > 0 && <p className="m-0 px-3 py-2 text-[12.5px]" style={{ color: "var(--muted)" }}>{formatNumber(more)} more in the findings export.</p>}
    </div>
  );
}
