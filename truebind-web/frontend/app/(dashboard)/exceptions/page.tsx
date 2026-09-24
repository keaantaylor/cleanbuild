"use client";

import Link from "next/link";
import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import type { ExceptionRow } from "@/lib/types";
import { findingGuide } from "@/lib/findings";
import { formatMoney, formatNumber } from "@/lib/formatters";
import { Button, ButtonLink } from "@/components/ui/Button";
import { Drawer, EmptyState, ErrorState, EvidencePanel, Icon, MetricCard, Panel, PageHeader, Pill, SkeletonRows, SourceReference, ds, severityTone } from "@/components/ds";
import { PageSkeleton } from "@/components/layout/ShellSkeleton";
import { ReportSelect, useSelectedReport } from "@/components/ops/ReportSelect";
import { AiTriagePanel } from "@/components/exceptions/AiTriagePanel";
import styles from "./exceptions.module.css";

const PAGE = 50;
const REVIEW_LABEL: Record<string, string> = { open: "Open", in_review: "In review", resolved: "Resolved", accepted: "Accepted", false_positive: "False positive" };
const CHECKS = [["", "All checks"], ["MANDATORY_FIELD", "Missing required data"], ["ARITHMETIC", "Arithmetic"], ["DATE", "Dates"],
  ["CURRENCY", "Currency"], ["STATUS", "Status"], ["MAPPING_COMPLETENESS", "Mapping gaps"], ["OTHER", "Unreadable values"]];

export default function ExceptionsPage() {
  const params = useSearchParams();
  const { reportId, reports, loading: rl, select } = useSelectedReport();
  const [severity, setSeverity] = useState(params.get("severity") ?? "");
  const [checkType, setCheckType] = useState(params.get("checkType") ?? "");
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("severity");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<ExceptionRow | null>(null);

  const list = useApi(() => (reportId ? api.searchExceptions(reportId, { severity: severity || undefined, checkType: checkType || undefined,
    status: status || undefined, q: q || undefined, sort, limit: PAGE, offset }) : Promise.resolve(null)),
    [reportId, severity, checkType, status, q, sort, offset]);
  const counts = useApi(async () => {
    if (!reportId) return null;
    const sev = ["CRITICAL", "HIGH", "MEDIUM", "INFO"];
    const totals = await Promise.all(sev.map((s) => api.searchExceptions(reportId, { severity: s, limit: 1 }).then((p) => p.total)));
    return Object.fromEntries(sev.map((s, i) => [s, totals[i]]));
  }, [reportId]);

  if (rl) return <PageSkeleton label="Loading exceptions" />;
  if (!reportId) {
    return (<><PageHeader eyebrow="Investigate" title="Exceptions" />
      <Panel><EmptyState icon="exceptions" title="No completed reports yet" body="Exceptions appear once a bordereau has been processed."
        action={<ButtonLink href="/upload" variant="primary">Upload a bordereau</ButtonLink>} /></Panel></>);
  }
  const c = counts.data ?? {};
  const page = list.data;
  const setFilter = (fn: () => void) => { fn(); setOffset(0); setSelected(null); };

  return (
    <>
      <PageHeader eyebrow="Investigate · exception centre" title="Exceptions"
        description="Every finding, with what happened, why it matters, the evidence and the next step. Decisions are recorded in the audit trail; source data is never changed."
        actions={<><ReportSelect reportId={reportId} reports={reports} onSelect={(id) => { select(id); setOffset(0); setSelected(null); }} />
          <Button variant="secondary" onClick={() => window.open(api.exportExceptionsUrl(reportId), "_blank")}><Icon name="download" />Export</Button></>} />
      <div className={ds.stack}>
        <div className={`${ds.grid} ${ds.cols4}`}>
          {(["CRITICAL", "HIGH", "MEDIUM", "INFO"] as const).map((s) => (
            <button key={s} type="button" className={styles.tileBtn} aria-pressed={severity === s}
                    onClick={() => setFilter(() => setSeverity(severity === s ? "" : s))}>
              <MetricCard label={s.charAt(0) + s.slice(1).toLowerCase()} value={formatNumber(c[s] ?? 0)}
                icon={s === "CRITICAL" ? "alertCircle" : s === "HIGH" ? "exceptions" : s === "MEDIUM" ? "info" : "clock"}
                tone={s === "CRITICAL" ? "bad" : s === "HIGH" ? "warn" : s === "MEDIUM" ? "processing" : "neutral"}
                caption={severity === s ? "Filtering — click to clear" : "Click to filter"} />
            </button>
          ))}
        </div>

        <div className={ds.toolbar}>
          <div className={ds.searchWrap}><Icon name="search" />
            <input className={ds.input} placeholder="Search claim reference" value={q} onChange={(e) => setFilter(() => setQ(e.target.value))} aria-label="Search claim reference" /></div>
          <select className={ds.select} value={checkType} onChange={(e) => setFilter(() => setCheckType(e.target.value))} aria-label="Check">
            {CHECKS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <select className={ds.select} value={status} onChange={(e) => setFilter(() => setStatus(e.target.value))} aria-label="Outcome">
            <option value="">All outcomes</option><option value="FAIL">Failed checks</option><option value="NOT_EVALUABLE">Could not be checked</option><option value="REVIEW">Needs review</option>
          </select>
          <select className={ds.select} value={sort} onChange={(e) => setFilter(() => setSort(e.target.value))} aria-label="Sort">
            <option value="severity">Most severe first</option><option value="row">Source order</option>
          </select>
          <span className={ds.muted} style={{ marginLeft: "auto" }}>{page ? `${formatNumber(page.total)} finding(s)` : ""}</span>
        </div>

        <div>
          <Panel flush>
            {list.error ? <div style={{ padding: 20 }}><ErrorState message={list.error} onRetry={list.reload} /></div>
              : !page ? <div style={{ padding: 20 }}><SkeletonRows rows={10} /></div>
              : page.items.length === 0 ? <EmptyState icon="check" title="No findings match" body="Change the filters, or celebrate: this report has nothing here." /> : (
              <div className={styles.tableWrap}>
                <table className={styles.table}>
                  <thead><tr><th scope="col">Severity</th><th scope="col">Finding</th><th scope="col">Claim</th><th scope="col">Source</th><th scope="col" className={styles.num}>Amount</th><th scope="col">Review</th></tr></thead>
                  <tbody>
                    {page.items.map((e) => {
                      const g = findingGuide(e.rule, e.status);
                      const active = selected?.validation_result_id === e.validation_result_id;
                      return (
                        <tr key={e.validation_result_id} className={active ? styles.activeRow : undefined} onClick={() => setSelected(e)}
                            tabIndex={0} onKeyDown={(ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); setSelected(e); } }}
                            aria-selected={active}>
                          <td><Pill tone={severityTone(e.severity)}>{e.severity.toLowerCase()}</Pill></td>
                          <td><strong className={styles.title}>{g.title}</strong><div className={styles.msg}>{e.message}</div></td>
                          <td className={ds.mono}>{e.claim_reference ?? <span className={ds.muted}>none</span>}</td>
                          <td className={styles.sub}>{e.sheet_name}<br />row {e.source_row_number ?? "—"}</td>
                          <td className={styles.num}>{formatMoney(e.amount, e.currency ?? "")}</td>
                          <td>{e.review_status ? <Pill tone={e.review_status === "resolved" || e.review_status === "false_positive" ? "good" : "brand"}>{REVIEW_LABEL[e.review_status]}</Pill> : <span className={ds.muted}>—</span>}
                            {e.assignee && <div className={styles.sub}>{e.assignee}</div>}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
            {page && page.total > PAGE && (
              <div className={styles.pager}>
                <Button size="sm" variant="secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</Button>
                <span className={ds.muted}>{offset + 1}–{Math.min(offset + PAGE, page.total)} of {formatNumber(page.total)}</span>
                <Button size="sm" variant="secondary" disabled={offset + PAGE >= page.total} onClick={() => setOffset(offset + PAGE)}>Next</Button>
              </div>
            )}
          </Panel>
        </div>
        <Drawer open={!!selected} onClose={() => setSelected(null)} width={600}
          eyebrow={selected ? `${selected.severity.toLowerCase()} · ${selected.check_type.toLowerCase().replace(/_/g, " ")}` : undefined}
          title={selected ? findingGuide(selected.rule, selected.status).title : ""}>
          {selected && <FindingDetail key={selected.validation_result_id} reportId={reportId} finding={selected}
            onSaved={(patch) => { list.reload(); setSelected({ ...selected, ...patch }); }} />}
        </Drawer>

        <AiTriagePanel reportId={reportId} onFilterAction={(a) => setFilter(() => setCheckType(a.checkType ?? ""))} />
      </div>
    </>
  );
}

function FindingDetail({ reportId, finding, onSaved }: {
  reportId: string; finding: ExceptionRow; onSaved: (patch: Partial<ExceptionRow>) => void;
}) {
  const [review, setReview] = useState(finding?.review_status ?? "in_review");
  const [assignee, setAssignee] = useState(finding?.assignee ?? "");
  const [note, setNote] = useState("");
  const [deadline, setDeadline] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const g = findingGuide(finding.rule, finding.status);
  const certainty = g.certainty === "certain" ? "Deterministic check — the evidence is conclusive for this row."
    : g.certainty === "signal" ? "A signal, not proof — confirm before acting." : "Undetermined — TrueBind does not have enough evidence to decide.";

  async function save() {
    setBusy(true);
    setMsg(null);
    try {
      await api.reviewException(reportId, finding!.validation_result_id, { review_status: review, assignee: assignee || null, note: note || null });
      onSaved({ review_status: review, assignee: assignee || null });
      setMsg("Saved to the audit trail.");
    } catch (e) {
      setMsg(e instanceof ApiError ? e.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }
  async function followUp() {
    setBusy(true);
    try {
      await api.createObligation(reportId, { claim_row_id: finding!.claim_row_id, owner: assignee || null,
        deadline: deadline || null, note: `${g.title}: ${finding!.claim_reference ?? "row " + finding!.source_row_number}${note ? ` — ${note}` : ""}` });
      setMsg("Follow-up created in the work queue.");
    } catch (e) {
      setMsg(e instanceof ApiError ? e.message : "Could not create the follow-up.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.detail}>
      <SourceReference file={undefined} sheet={finding.sheet_name ?? undefined} row={finding.source_row_number ?? undefined}
        column={finding.claim_reference ? `claim ${finding.claim_reference}` : undefined} />
      <section><h3>What happened</h3><p>{finding.message}</p></section>
      <section><h3>Where it came from</h3>
        <p>Sheet <strong>{finding.sheet_name ?? "—"}</strong>, source row <strong>{finding.source_row_number ?? "—"}</strong>
          {finding.claim_reference ? <> — claim <span className={ds.mono}>{finding.claim_reference}</span></> : " — no claim reference on this row"}.</p>
        <p className={styles.sub}><Link href={`/reports/${reportId}#mapping`}>How this sheet was mapped</Link> · <Link href={`/audit?reportId=${reportId}`}>Audit trail</Link></p>
      </section>
      <EvidencePanel items={[
        { label: "Claim reference", value: finding.claim_reference ?? "—" },
        { label: "Amount", value: formatMoney(finding.amount, finding.currency ?? "") },
        { label: "Check", value: `${finding.check_type} · ${finding.rule ?? ""}` },
        { label: "Outcome", value: finding.status === "NOT_EVALUABLE" ? "could not be checked" : finding.status.toLowerCase(), emphasis: finding.status === "FAIL" },
      ]} />
      <section><h3>Why it matters</h3><p>{g.why}</p><p className={styles.certainty}>{certainty}</p></section>
      <section><h3>What to do next</h3><p>{g.next}</p></section>
      <section className={styles.form}>
        <h3>Your decision</h3>
        <label>Status<select className={ds.select} value={review} onChange={(e) => setReview(e.target.value)}>
          {Object.entries(REVIEW_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
        <label>Assignee<input className={ds.input} value={assignee} onChange={(e) => setAssignee(e.target.value)} maxLength={200} placeholder="Name" /></label>
        <label>Note<textarea className={ds.input} value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000} rows={2} style={{ paddingTop: 8 }} /></label>
        <div className={styles.actions}>
          <Button onClick={save} loading={busy}>Save decision</Button>
        </div>
        <label>Follow-up due<input className={ds.input} type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} /></label>
        <Button variant="secondary" onClick={followUp} disabled={busy}>Create follow-up</Button>
        {msg && <p role="status" className={styles.sub}>{msg}</p>}
      </section>
    </div>
  );
}
