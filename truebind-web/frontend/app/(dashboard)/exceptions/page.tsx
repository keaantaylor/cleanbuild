"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowCounterClockwise, CheckCircle, DownloadSimple, LockSimple, MagnifyingGlass, ShieldCheck, ListChecks, Warning } from "@phosphor-icons/react";
import { api, ApiError } from "@/lib/api";
import type { ClaimRow, ExceptionRow, ExceptionSummary } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { useUi } from "@/lib/ui";
import { findingGuide } from "@/lib/findings";
import { formatDateTime, formatMoney, formatNumber, formatPct } from "@/lib/formatters";
import { EmptyState, ErrorState, LoadingState, Modal, PageHeader, StatusPill } from "@/components/nocturne/ui";
import { ReportPicker, useSelectedReport } from "@/components/nocturne/select-report";
import { SEV, SHEET } from "@/components/nocturne/status";
import { exportFile } from "@/lib/exports";
import { resultTone, TONE, type ResultTone } from "@/lib/severity";

const PAGE = 50; // findings per page inside an open issue group
const OUTCOME_DOT: Record<ResultTone, string> = { err: "var(--err)", warn: "var(--warn)", muted: "var(--muted)", ok: "var(--ok)" };
const REVIEW_LABEL: Record<string, string> = { open: "Open", in_review: "In review", resolved: "Resolved", accepted: "Accepted as reported", false_positive: "Dismissed · not an issue" };
const CHECKS = [
  ["", "All checks"],
  ["MANDATORY_FIELD", "Missing required data"],
  ["ARITHMETIC", "Arithmetic"],
  ["DATE", "Dates"],
  ["CURRENCY", "Currency"],
  ["STATUS", "Status"],
  ["POLICY", "Policy period, limit and number"],
  ["AMOUNT", "Amounts"],
  ["REFERENCE", "Claim reference format"],
  ["MAPPING_COMPLETENESS", "Mapping gaps"],
  ["OTHER", "Unreadable values"],
];
const SEVS = ["CRITICAL", "HIGH", "MEDIUM", "INFO"] as const;

export default function ExceptionsPage() {
  return (
    <Suspense>
      <Exceptions />
    </Suspense>
  );
}

function Exceptions() {
  const params = useSearchParams();
  const { toast } = useUi();
  const { reportId, report, reports, loading: rl, error: rerr, reload: rreload, select } = useSelectedReport();
  const [severity, setSeverity] = useState(params.get("severity") ?? "");
  const [checkType, setCheckType] = useState(params.get("checkType") ?? "");
  const [status, setStatus] = useState(params.get("status") ?? "");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("severity");
  const [sheetF, setSheetF] = useState("");
  const [columnF, setColumnF] = useState("");
  const [openRule, setOpenRule] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [selId, setSelId] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  // Phones and tablets stack the panes: bring the chosen finding's detail into view.
  const pick = (id: string) => {
    setSelId(id);
    if (window.matchMedia("(max-width: 1023px)").matches) {
      requestAnimationFrame(() => (listRef.current?.nextElementSibling as HTMLElement | null)?.scrollIntoView({ behavior: "smooth", block: "start" }));
    }
  };
  const [modal, setModal] = useState<null | "accept" | "followup">(null);

  const filters = { severity: severity || undefined, checkType: checkType || undefined, status: status || undefined, q: q || undefined, sheetId: sheetF || undefined, column: columnF || undefined };
  const groups = useApi(() => (reportId ? api.exceptionGroups(reportId, filters) : Promise.resolve(null)), [reportId, severity, checkType, status, q, sheetF, columnF]);
  const list = useApi(
    () => (reportId && openRule ? api.searchExceptions(reportId, { ...filters, rule: openRule, sort, limit: PAGE, offset }) : Promise.resolve(null)),
    [reportId, severity, checkType, status, q, sheetF, columnF, openRule, sort, offset],
  );
  const counts = useApi(async () => {
    if (!reportId) return null;
    const totals = await Promise.all(SEVS.map((s) => api.searchExceptions(reportId, { severity: s, limit: 1 }).then((p) => p.total)));
    const reviewed = await api.searchExceptions(reportId, { limit: 1 }).then((p) => p.total);
    return { ...Object.fromEntries(SEVS.map((s, i) => [s, totals[i]])), all: reviewed } as Record<string, number>;
  }, [reportId]);

  const items = useMemo(() => list.data?.items ?? [], [list.data]);
  const sel = items.find((e) => e.validation_result_id === selId) ?? items[0] ?? null;
  const setFilter = (fn: () => void) => {
    fn();
    setOffset(0);
    setSelId(null);
    setOpenRule(null);
  };
  const toggleGroup = (rule: string) => {
    setOpenRule((r) => (r === rule ? null : rule));
    setOffset(0);
    setSelId(null);
  };
  const move = useCallback(
    (d: number) => {
      if (!items.length) return;
      const i = Math.max(0, items.findIndex((e) => e.validation_result_id === sel?.validation_result_id));
      setSelId(items[(i + d + items.length) % items.length].validation_result_id);
    },
    [items, sel],
  );

  const decide = useCallback(
    async (review: string, note?: string, successText?: string, assignee?: string | null) => {
      if (!reportId || !sel) return;
      try {
        await api.reviewException(reportId, sel.validation_result_id, { review_status: review, assignee: assignee === undefined ? sel.assignee ?? null : assignee, note: note ?? null });
        toast(`${successText ?? REVIEW_LABEL[review]} · recorded in the audit trail`, "ok");
        list.reload();
        groups.reload();
        if (review !== "open") setTimeout(() => move(1), 350);
      } catch (e) {
        toast(e instanceof ApiError ? e.message : "The decision could not be saved.", "err");
      }
    },
    [reportId, sel, list, groups, move, toast],
  );

  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => {
      if (modal || (ev.target as HTMLElement)?.closest("input,textarea,select,[role=dialog]") || ev.metaKey || ev.ctrlKey || ev.altKey) return;
      const k = ev.key.toLowerCase();
      if (k === "j") move(1);
      else if (k === "k") move(-1);
      else if (k === "f" && sel) setModal("followup");
      else if (k === "a" && sel) setModal("accept");
      else if (k === "d" && sel) void decide("false_positive");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [move, modal, sel, decide]);

  if (rl)
    return (
      <div className="px-4 pt-8 sm:px-6">
        <LoadingState label="Loading exceptions" rows={8} />
      </div>
    );
  if (rerr)
    return (
      <div className="px-4 pt-8 sm:px-6">
        <ErrorState title="Reports could not be loaded" message={rerr} onRetry={rreload} />
      </div>
    );
  if (!reportId)
    return (
      <div className="flex max-w-[1520px] flex-col gap-5 px-4 pb-10 pt-5 sm:px-6">
        <PageHeader kicker="Investigate · Exception centre" title="Exceptions" />
        <div className="tb-card">
          <EmptyState icon={<Warning />} title="No completed reports yet" body="Exceptions appear once a bordereau has been processed." action={<Link href="/upload" className="tb-btn tb-btn-primary">Upload a bordereau</Link>} />
        </div>
      </div>
    );

  const c = counts.data ?? {};
  const page = list.data;
  const reviewedOnPage = items.filter((e) => e.review_status && e.review_status !== "open").length;

  return (
    <div className="flex max-w-[1520px] flex-col gap-5 px-4 pb-10 pt-5 sm:px-6">
      <PageHeader
        kicker="Investigate · Exception centre"
        title="Exceptions"
        sub="Every finding, with what happened, why it matters, the evidence and the next step. Decisions are recorded in the audit trail; source data is never changed."
        actions={
          <>
            <ReportPicker report={report} reports={reports} onSelect={(id) => { select(id); setOffset(0); setSelId(null); }} />
            <button type="button" className="tb-btn" onClick={() => void exportFile(api.exportExceptionsUrl(reportId), `${report?.file_name.replace(/\.\w+$/, "") ?? "report"}_exceptions`, toast)}>
              <DownloadSimple />
              Export
            </button>
            <Link href={`/reports/${reportId}`} className="tb-btn tb-btn-primary">Health Check report</Link>
          </>
        }
      />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-0.5 rounded-md p-[3px]" style={{ boxShadow: "inset 0 0 0 1px var(--line2)" }} role="tablist" aria-label="Severity">
          {(["", ...SEVS] as const).map((k) => (
            <button key={k || "all"} type="button" role="tab" aria-selected={severity === k} onClick={() => setFilter(() => setSeverity(k))} className="flex cursor-pointer items-center gap-[7px] rounded-[7px] px-3 py-1.5 text-[13px]" style={{ background: severity === k ? "var(--accentTint)" : "transparent", color: severity === k ? "var(--text)" : "var(--muted)" }}>
              <span className="h-1.5 w-1.5 rounded-full" style={{ background: k ? SEV[k].c : "transparent" }} />
              {k ? SEV[k].label : "All"}
              <span className="tnum text-[11.5px]" style={{ color: "var(--faint)" }}>{counts.data ? formatNumber(k ? c[k] ?? 0 : c.all ?? 0) : "…"}</span>
            </button>
          ))}
        </div>
        <div className="grid w-full grid-cols-2 items-center gap-2 sm:flex sm:w-auto sm:flex-wrap">
          <div className="col-span-2 flex items-center gap-2 rounded-md px-2.5 sm:col-span-1" style={{ boxShadow: "inset 0 0 0 1px var(--line2)", background: "var(--surface)" }}>
            <MagnifyingGlass size={14} style={{ color: "var(--faint)" }} />
            <input value={q} onChange={(e) => setFilter(() => setQ(e.target.value))} placeholder="Claim reference" aria-label="Search claim reference" className="h-[34px] min-w-0 flex-1 bg-transparent text-[13px] outline-none sm:w-[150px] sm:flex-none" />
          </div>
          <select className="tb-input !min-h-[34px] col-span-2 !py-1 text-[13px] sm:!w-auto" value={checkType} onChange={(e) => setFilter(() => setCheckType(e.target.value))} aria-label="Check">
            {CHECKS.map(([v, l]) => (
              <option key={v} value={v}>{l}</option>
            ))}
          </select>
          <select className="tb-input !min-h-[34px] !py-1 text-[13px] sm:!w-auto" value={status} onChange={(e) => setFilter(() => setStatus(e.target.value))} aria-label="Outcome">
            <option value="">Errors, warnings and couldn’t check</option>
            <option value="FAIL">Errors</option>
            <option value="REVIEW">Warnings</option>
            <option value="NOT_EVALUABLE">Couldn’t check</option>
          </select>
          <select className="tb-input !min-h-[34px] !py-1 text-[13px] sm:!w-auto" value={sheetF} onChange={(e) => setFilter(() => setSheetF(e.target.value))} aria-label="Sheet">
            <option value="">All sheets</option>
            {(groups.data?.sheets ?? []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          <select className="tb-input !min-h-[34px] !py-1 text-[13px] sm:!w-auto" value={columnF} onChange={(e) => setFilter(() => setColumnF(e.target.value))} aria-label="Column">
            <option value="">All columns</option>
            {(groups.data?.columns ?? []).map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <select className="tb-input !min-h-[34px] !py-1 text-[13px] sm:!w-auto" value={sort} onChange={(e) => setFilter(() => setSort(e.target.value))} aria-label="Sort">
            <option value="severity">Most severe first</option>
            <option value="row">Source order</option>
          </select>
          <span className="hidden whitespace-nowrap text-[12.5px] xl:inline" style={{ color: "var(--faint)" }}>
            {page ? `${reviewedOnPage} of ${items.length} on this page reviewed · J / K to move` : ""}
          </span>
        </div>
      </div>

      <div className="flex min-h-[620px] flex-wrap overflow-hidden rounded-md" style={{ background: "var(--surface)", boxShadow: "var(--shadow)" }}>
        <div ref={listRef} className="flex max-h-[420px] min-w-[240px] flex-[1_1_260px] flex-col overflow-y-auto overflow-x-hidden lg:max-h-[760px]" style={{ boxShadow: "1px 0 0 var(--line)" }}>
          {groups.error ? (
            <div className="p-4"><ErrorState title="Findings could not be loaded" message={groups.error} onRetry={groups.reload} /></div>
          ) : !groups.data ? (
            <div className="p-4"><LoadingState label="Loading findings" rows={8} /></div>
          ) : groups.data.groups.length === 0 ? (
            <EmptyState icon={<CheckCircle />} title="No findings match" body="Change the filters - or this report has nothing here." />
          ) : (
            <ul className="m-0 list-none p-0" aria-label="Findings by issue type">
              {groups.data.groups.map((g) => {
                const open = openRule === g.rule;
                const tone = resultTone(g.status);
                return (
                  <li key={`${g.rule}-${g.status}`} style={{ boxShadow: "inset 0 -1px 0 var(--line)" }}>
                    <button type="button" aria-expanded={open} onClick={() => toggleGroup(g.rule)} className="flex w-full cursor-pointer items-center gap-2.5 px-4 py-3 text-left hover:bg-[var(--accentTint)]">
                      <span className="h-2 w-2 flex-none rounded-full" style={{ background: OUTCOME_DOT[tone] }} title={TONE[tone].label} />
                      <span className="min-w-0 flex-1 truncate text-[13.5px] font-medium">{g.label}</span>
                      <span className="tnum rounded px-1.5 py-0.5 text-[12px] font-medium" style={{ background: "var(--line)", color: "var(--text)" }}>{formatNumber(g.count)}</span>
                      <span className="text-[12px]" style={{ color: "var(--faint)" }}>{open ? "−" : "+"}</span>
                    </button>
                    {open && (
                      <div className="pb-1">
                        {list.error ? (
                          <div className="px-4 py-2 text-[12.5px]" style={{ color: "var(--err)" }}>{list.error}</div>
                        ) : !page ? (
                          <div className="px-4 py-2 text-[12.5px]" style={{ color: "var(--faint)" }}>Loading…</div>
                        ) : (
                          items.map((x) => {
                            const on = x.validation_result_id === sel?.validation_result_id;
                            const reviewed = x.review_status && x.review_status !== "open";
                            const where = x.cell && !x.cell.startsWith("row ") ? `${x.sheet_name}!${x.cell}` : `${x.sheet_name} row ${x.source_row_number ?? "-"}`;
                            return (
                              <button key={x.validation_result_id} type="button" onClick={() => pick(x.validation_result_id)} className="flex w-full cursor-pointer flex-col gap-0.5 py-2 pl-[34px] pr-4 text-left hover:bg-[var(--accentTint)]" style={{ background: on ? "var(--accentTint)" : "transparent", boxShadow: on ? "inset 2px 0 0 var(--accent)" : "none" }}>
                                <span className="tnum text-[12.5px] font-medium">{where} · {x.claim_reference ?? "no claim ref"}</span>
                                {on && (
                                  <span className="flex flex-col gap-0.5 text-[12.5px]">
                                    <span>{x.sentence ?? x.message}</span>
                                    <span className="tnum" style={{ color: "var(--muted)" }}>Source row {x.source_row_number ?? "-"}{x.source_column ? ` · column “${x.source_column}”` : ""}{x.amount != null ? ` · amount ${formatMoney(x.amount, x.currency ?? "")}` : ""}</span>
                                  </span>
                                )}
                                <span className="text-[11.5px]" style={{ color: reviewed ? "var(--ok)" : "var(--faint)" }}>{x.review_status ? REVIEW_LABEL[x.review_status] : "Open"}{x.assignee ? ` · ${x.assignee}` : ""}</span>
                              </button>
                            );
                          })
                        )}
                        {page && page.total > PAGE && (
                          <div className="flex items-center justify-between gap-2 py-2 pl-[34px] pr-3 text-[12px]" style={{ color: "var(--faint)" }}>
                            <button type="button" className="tb-btn !px-2 !py-1 text-[12px]" disabled={offset === 0} onClick={() => { setOffset(Math.max(0, offset - PAGE)); setSelId(null); }}>Previous</button>
                            <span className="tnum">{offset + 1}–{Math.min(offset + PAGE, page.total)} of {formatNumber(page.total)}</span>
                            <button type="button" className="tb-btn !px-2 !py-1 text-[12px]" disabled={offset + PAGE >= page.total} onClick={() => { setOffset(offset + PAGE); setSelId(null); }}>Next</button>
                          </div>
                        )}
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
        {sel && reportId ? (
          <FindingPanels key={sel.validation_result_id} reportId={reportId} fileName={report?.file_name ?? ""} f={sel} onAccept={() => setModal("accept")} onFollowup={() => setModal("followup")} onDismiss={() => void decide("false_positive")} onReopen={() => void decide("open", undefined, "Finding reopened")} onResolve={() => void decide("resolved")} onRecord={(review, assignee, note) => void decide(review, note, undefined, assignee)} prev={() => move(-1)} next={() => move(1)} />
        ) : (
          <div className="flex flex-[5_1_560px] items-center justify-center p-10 text-[13.5px]" style={{ color: "var(--faint)" }}>{page && !items.length ? "" : "Select a finding."}</div>
        )}
      </div>

      {reportId && <AiTriage reportId={reportId} onFilter={(ct) => setFilter(() => setCheckType(ct ?? ""))} />}

      {sel && reportId && (
        <>
          <AcceptModal open={modal === "accept"} onClose={() => setModal(null)} onSave={(note) => { setModal(null); void decide("accepted", note); }} />
          <FollowupModal open={modal === "followup"} onClose={() => setModal(null)} reportId={reportId} f={sel} onDone={() => { setModal(null); list.reload(); }} />
        </>
      )}
    </div>
  );
}

const FIELD_FOR_CHECK: Record<string, keyof ClaimRow> = { ARITHMETIC: "incurred_amount", DATE: "date_of_loss", CURRENCY: "currency", STATUS: "claim_status" };
const COLS: [keyof ClaimRow, string, string][] = [
  ["claim_reference", "claim_reference", "Claim ref"],
  ["reporting_period", "reporting_period", "Period"],
  ["insured_name", "insured_name", "Insured"],
  ["date_of_loss", "date_of_loss", "DOL"],
  ["claim_status", "claim_status", "Status"],
  ["paid_amount", "paid_to_date", "Paid TD"],
  ["reserve_amount", "reserve", "Reserve"],
  ["fees_paid_to_date", "fees", "Fees"],
  ["incurred_amount", "total_incurred", "Total inc."],
];

function FindingPanels({ reportId, fileName, f, onAccept, onFollowup, onDismiss, onReopen, onResolve, onRecord, prev, next }: { reportId: string; fileName: string; f: ExceptionRow; onAccept: () => void; onFollowup: () => void; onDismiss: () => void; onReopen: () => void; onResolve: () => void; onRecord: (review: string, assignee: string | null, note: string) => void; prev: () => void; next: () => void }) {
  const g = findingGuide(f.rule, f.status);
  const sv = SEV[f.severity];
  const sheet = SHEET[f.severity];
  const rows = useApi(() => (f.claim_reference ? api.listClaimsByRef(reportId, f.claim_reference) : Promise.resolve([] as ClaimRow[])), [reportId, f.claim_reference]);
  const hitField = FIELD_FOR_CHECK[f.check_type] ?? (f.check_type === "MANDATORY_FIELD" ? COLS.find(([k]) => /insured/.test(f.message.toLowerCase()) && k === "insured_name")?.[0] : undefined);
  const certainty = g.certainty === "certain" ? "Deterministic check - the evidence is conclusive for this row." : g.certainty === "signal" ? "A signal, not proof - confirm before acting." : "Undetermined - TrueBind doesn’t have enough evidence to decide.";
  const fmt = (v: unknown, k: keyof ClaimRow, ccy?: string | null) => (v == null || v === "" ? "" : typeof v === "number" && /amount|fees/.test(String(k)) ? formatMoney(v, ccy ?? "").replace(/^[^\d-]+/, "") : String(v));
  const decided = f.review_status && f.review_status !== "open";

  return (
    <>
      <div className="anim-fade flex min-w-0 flex-[4_1_420px] flex-col gap-5 px-5 py-6 sm:px-7">
        <div className="flex flex-col gap-2">
          <div className="tnum flex flex-wrap items-center gap-2.5 text-[12px]" style={{ color: "var(--faint)" }}>
            <span className="rounded-full px-[9px] py-[3px] text-[12px] font-medium" style={{ background: sv.bg, color: sv.c }}>{sv.label}</span>
            <span>{f.check_type.toLowerCase().replace(/_/g, " ")}</span>
            {f.rule && <><span>·</span><span>{f.rule}</span></>}
          </div>
          <h2 className="m-0 text-[24px] font-medium tracking-[-0.02em] [text-wrap:balance]">{g.title}</h2>
          <p className="m-0 max-w-[640px] text-[14px] leading-[1.6]" style={{ color: "var(--text)" }}>{f.sentence ?? f.message}</p>
          {f.cell && (
            <p className="tnum m-0 text-[13px]" style={{ color: "var(--muted)" }}>
              {f.cell.startsWith("row ") ? `Sheet ${f.sheet_name}, ${f.cell}` : `Cell ${f.sheet_name}!${f.cell}`}{f.source_column ? ` · column “${f.source_column}”` : ""}{f.owner ? ` · ${f.owner === "sender" ? "the sender must fix this" : "we can fix this"}` : ""}
            </p>
          )}
          <p className="m-0 max-w-[640px] text-[13.5px] leading-[1.6] [text-wrap:pretty]" style={{ color: "var(--muted)" }}>{g.why}</p>
        </div>
        <div className="overflow-hidden rounded-md" style={{ background: "#f7f8f6", color: "#2a2f36", boxShadow: "0 0 0 1px var(--line2)" }}>
          <div className="flex h-[30px] items-center justify-between px-3 text-[11px]" style={{ background: "#edf0ec", borderBottom: "1px solid #dde1db", color: "#5e656d" }}>
            <span className="truncate">{fileName} › {f.sheet_name}</span>
            <span className="flex flex-none items-center gap-[5px]"><LockSimple />source · read-only</span>
          </div>
          <div className="overflow-x-auto">
            {!f.claim_reference ? (
              <p className="m-0 px-4 py-4 text-[12.5px]" style={{ color: "#5e656d" }}>This row has no claim reference, so its other periods can’t be shown. Source row {f.source_row_number ?? "-"} on sheet {f.sheet_name}.</p>
            ) : rows.error ? (
              <p className="m-0 px-4 py-4 text-[12.5px]" style={{ color: "#5e656d" }}>The source rows could not be loaded.</p>
            ) : !rows.data ? (
              <p className="m-0 px-4 py-4 text-[12.5px]" style={{ color: "#5e656d" }}>Loading the source rows…</p>
            ) : (
              <table className="w-full min-w-[720px] border-collapse text-[11px]">
                <thead>
                  <tr style={{ background: "oklch(0.96 0.02 150)" }}>
                    <th className="w-10" style={{ borderRight: "1px solid #e1e4df", borderBottom: "1px solid #d5d9d3" }} />
                    {COLS.map(([k, m, s]) => (
                      <th key={k} className="px-2 py-1.5 text-left font-normal" style={{ borderRight: "1px solid #e1e4df", borderBottom: "1px solid #d5d9d3", background: k === hitField ? sheet.bg : "transparent" }}>
                        <span className="block truncate text-[10.5px] font-semibold" style={{ color: "oklch(0.4 0.1 150)" }}>{m}</span>
                        <span className="block whitespace-nowrap text-[9.5px]" style={{ color: "#7e858d" }}>{s}</span>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.data.map((r) => {
                    const target = r.id === f.claim_row_id;
                    return (
                      <tr key={r.id} style={{ borderBottom: "1px solid #e6e8e4", background: target ? "#fff" : "transparent" }}>
                        <td className="tnum px-1 text-center text-[10.5px]" style={{ borderRight: "1px solid #e1e4df", background: "#eff1ee", color: target ? "#1c1e2a" : "#8a9098", fontWeight: target ? 600 : 400 }}>{r.source_row_number ?? "-"}</td>
                        {COLS.map(([k]) => {
                          const hit = target && k === hitField;
                          const v = fmt(r[k], k, r.currency);
                          return (
                            <td key={k} className="tnum h-[30px] overflow-hidden whitespace-nowrap px-2" style={{ textAlign: /amount|fees/.test(String(k)) ? "right" : "left", borderRight: "1px solid #e6e8e4", color: hit ? sheet.fg : "#2a2f36", background: hit ? sheet.bg : "transparent", boxShadow: hit ? sheet.ring : "none", fontStyle: v ? "normal" : "italic" }}>
                              {v || (target && f.check_type === "MANDATORY_FIELD" ? "blank" : "")}
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        </div>
        <div className="grid grid-cols-1 gap-px overflow-hidden rounded-md sm:grid-cols-3" style={{ background: "var(--line)", boxShadow: "0 0 0 1px var(--line)" }}>
          {[
            ["Outcome", f.status === "NOT_EVALUABLE" ? "Could not be checked" : f.status === "FAIL" ? "Failed the check" : "Needs review", sv.c],
            ["Amount at stake", formatMoney(f.amount, f.currency ?? ""), "var(--text)"],
            ["What to do next", g.next, "var(--text)"],
          ].map(([l, v, c]) => (
            <div key={l} className="flex flex-col gap-[5px] px-4 py-3.5" style={{ background: "var(--surface)" }}>
              <span className="text-[11.5px]" style={{ color: "var(--faint)" }}>{l}</span>
              <span className={`tnum font-medium ${l === "What to do next" ? "text-[13px] leading-[1.45]" : "text-[16px]"}`} style={{ color: c }}>{v}</span>
            </div>
          ))}
        </div>
        <span className="text-[12.5px]" style={{ color: "var(--faint)" }}>{certainty}</span>
      </div>

      <div className="flex min-w-0 flex-[1_1_300px] flex-col gap-5 px-[22px] py-6" style={{ boxShadow: "-1px 0 0 var(--line), 0 -1px 0 var(--line)", background: "var(--bg2)" }}>
        <div className="grid grid-cols-[84px_1fr] gap-y-[9px] text-[13px]">
          <span style={{ color: "var(--faint)" }}>Claim</span>
          <span className="tnum font-medium">{f.claim_reference ?? "-"}</span>
          <span style={{ color: "var(--faint)" }}>Worksheet</span>
          <span className="truncate">{f.sheet_name ?? "-"}</span>
          <span style={{ color: "var(--faint)" }}>Row</span>
          <span className="tnum">{f.source_row_number ?? "-"}</span>
          <span style={{ color: "var(--faint)" }}>Check</span>
          <span>{f.check_type.toLowerCase().replace(/_/g, " ")}</span>
          <span style={{ color: "var(--faint)" }}>Status</span>
          <span style={{ color: decided ? "var(--ok)" : "var(--muted)" }}>{f.review_status ? REVIEW_LABEL[f.review_status] : "Open"}</span>
          {f.assignee && (
            <>
              <span style={{ color: "var(--faint)" }}>Assignee</span>
              <span>{f.assignee}</span>
            </>
          )}
        </div>
        <div className="flex flex-col gap-2 rounded-md px-3.5 py-3 text-[12.5px]" style={{ boxShadow: "inset 0 0 0 1px var(--line2)" }}>
          <span className="flex items-center gap-1.5 text-[12px]" style={{ color: "var(--muted)" }}>
            <ShieldCheck style={{ color: "var(--ok)" }} />
            Evidence
          </span>
          <Link href={`/reports/${reportId}#sheets`} style={{ color: "var(--accentText)" }}>How this sheet was mapped</Link>
          <Link href={`/audit?reportId=${reportId}`} style={{ color: "var(--accentText)" }}>Audit trail for this report</Link>
        </div>
        {decided && (
          <div className="anim-rise flex items-start gap-2 rounded-md px-3 py-2.5 text-[12.5px] leading-[1.45]" style={{ background: "var(--okT)", color: "var(--ok)" }}>
            <CheckCircle size={15} className="mt-px flex-none" />
            <span className="flex-1">{REVIEW_LABEL[f.review_status!]}{f.note ? ` - “${f.note}”` : ""}. Recorded in the audit trail. Source value unchanged.</span>
            <button type="button" title="Reopen" aria-label="Reopen this finding" className="tb-hit cursor-pointer" onClick={onReopen}>
              <ArrowCounterClockwise size={14} />
            </button>
          </div>
        )}
        <div className="mt-auto flex flex-col gap-2">
          <button type="button" onClick={onFollowup} className="tb-btn tb-btn-primary !justify-between !whitespace-normal !px-[13px] !py-[11px] text-left">
            Create follow-up with sender<span className="hidden text-[11px] opacity-60 md:inline">F</span>
          </button>
          <button type="button" onClick={onAccept} className="tb-btn !justify-between !whitespace-normal !px-[13px] !py-[11px] text-left">
            Accept as reported · note required<span className="hidden text-[11px] opacity-60 md:inline">A</span>
          </button>
          <button type="button" onClick={onDismiss} className="tb-btn !justify-between !whitespace-normal !px-[13px] !py-[11px] text-left">
            Dismiss as not an issue<span className="hidden text-[11px] opacity-60 md:inline">D</span>
          </button>
          <button type="button" onClick={onResolve} className="tb-btn tb-btn-ghost !justify-start !px-[13px] !py-2 text-[13px]">
            Mark resolved
          </button>
          <RecordDecision key={f.validation_result_id} f={f} onRecord={onRecord} />
          <div className="flex justify-between pt-2 text-[12px]" style={{ color: "var(--faint)" }}>
            <button type="button" className="tb-hit cursor-pointer py-1 hover:text-[var(--text)]" onClick={prev}>← Previous<span className="hidden md:inline"> · K</span></button>
            <button type="button" className="tb-hit cursor-pointer py-1 hover:text-[var(--text)]" onClick={next}>Next<span className="hidden md:inline"> · J</span> →</button>
          </div>
        </div>
      </div>
    </>
  );
}

/** Any status, an assignee and a note in one step (the quick buttons above cover the common cases). */
function RecordDecision({ f, onRecord }: { f: ExceptionRow; onRecord: (review: string, assignee: string | null, note: string) => void }) {
  const [open, setOpen] = useState(false);
  const [review, setReview] = useState(f.review_status ?? "open");
  const [assignee, setAssignee] = useState(f.assignee ?? "");
  const [note, setNote] = useState("");
  return (
    <div className="flex flex-col gap-2 pt-1">
      <button type="button" className="tb-hit cursor-pointer self-start text-[12.5px]" style={{ color: "var(--accentText)" }} aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        {open ? "Hide decision form" : "Assign or record a decision with a note"}
      </button>
      {open && (
        <form
          className="anim-fade flex flex-col gap-2.5 rounded-md p-3"
          style={{ boxShadow: "inset 0 0 0 1px var(--line)" }}
          onSubmit={(e) => {
            e.preventDefault();
            onRecord(review, assignee.trim() || null, note.trim());
            setNote("");
          }}
        >
          <div>
            <label className="tb-label" htmlFor="rd-status">Status</label>
            <select id="rd-status" className="tb-input" value={review} onChange={(e) => setReview(e.target.value)}>
              {Object.entries(REVIEW_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </div>
          <div>
            <label className="tb-label" htmlFor="rd-assignee">Assignee</label>
            <input id="rd-assignee" className="tb-input" value={assignee} maxLength={200} placeholder="Name" onChange={(e) => setAssignee(e.target.value)} />
          </div>
          <div>
            <label className="tb-label" htmlFor="rd-note">Note</label>
            <textarea id="rd-note" className="tb-input min-h-[64px]" value={note} maxLength={2000} onChange={(e) => setNote(e.target.value)} />
          </div>
          <button type="submit" className="tb-btn tb-btn-primary self-start">Save decision</button>
        </form>
      )}
    </div>
  );
}

function AcceptModal({ open, onClose, onSave }: { open: boolean; onClose: () => void; onSave: (note: string) => void }) {
  const [note, setNote] = useState("");
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Accept as reported"
      actions={
        <>
          <button className="tb-btn" onClick={onClose}>Cancel</button>
          <button className="tb-btn tb-btn-solid" disabled={note.trim().length < 5} onClick={() => { onSave(note.trim()); setNote(""); }}>Accept with note</button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        The value stays as the sender reported it and the finding is closed. Your note is kept with the decision in the audit trail.
        <textarea className="tb-input min-h-[96px]" value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000} placeholder="e.g. Confirmed with the sender - fee posted after the total was run." aria-label="Note" />
        <span className="text-[12px]" style={{ color: "var(--faint)" }}>At least 5 characters.</span>
      </div>
    </Modal>
  );
}

function FollowupModal({ open, onClose, reportId, f, onDone }: { open: boolean; onClose: () => void; reportId: string; f: ExceptionRow; onDone: () => void }) {
  const { toast } = useUi();
  const g = findingGuide(f.rule, f.status);
  const [owner, setOwner] = useState(f.assignee ?? "");
  const [deadline, setDeadline] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const draft = `${g.title} - claim ${f.claim_reference ?? "(none)"}, sheet ${f.sheet_name}, row ${f.source_row_number ?? "-"}.\n\n${f.message}\n\nCould you confirm the correct value or send a corrected file?`;
  const save = async () => {
    setBusy(true);
    try {
      await api.createObligation(reportId, { claim_row_id: f.claim_row_id, owner: owner.trim() || null, deadline: deadline || null, note: `${g.title}: ${f.claim_reference ?? `row ${f.source_row_number}`}${note ? ` - ${note}` : ""}` });
      await api.reviewException(reportId, f.validation_result_id, { review_status: "in_review", assignee: owner.trim() || f.assignee || null, note: note || null });
      toast("Follow-up created in the work queue · recorded in the audit trail", "ok");
      onDone();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "The follow-up could not be created.", "err");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      open={open}
      onClose={onClose}
      kicker="Follow-up with sender"
      title={g.title}
      width={560}
      actions={
        <>
          <button className="tb-btn" onClick={onClose}>Cancel</button>
          <button className="tb-btn" onClick={() => { void navigator.clipboard?.writeText(draft); toast("Message copied - paste it into your email to the sender", "info"); }}>Copy message</button>
          <button className="tb-btn tb-btn-solid" onClick={() => void save()} disabled={busy}>{busy ? "Saving…" : "Create follow-up"}</button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <span>Creates a tracked follow-up in the Work queue and marks the finding “In review”. TrueBind doesn’t email the sender for you - copy the message below into your own email.</span>
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className="tb-label" htmlFor="fu-owner">Owner</label>
            <input id="fu-owner" className="tb-input" value={owner} onChange={(e) => setOwner(e.target.value)} maxLength={200} placeholder="Name" />
          </div>
          <div>
            <label className="tb-label" htmlFor="fu-due">Due</label>
            <input id="fu-due" type="date" className="tb-input" value={deadline} onChange={(e) => setDeadline(e.target.value)} />
          </div>
        </div>
        <div>
          <label className="tb-label" htmlFor="fu-note">Note (optional)</label>
          <input id="fu-note" className="tb-input" value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000} />
        </div>
        <pre className="m-0 whitespace-pre-wrap rounded-md px-3 py-2.5 text-[12.5px]" style={{ background: "var(--bg2)", color: "var(--muted)", fontFamily: "inherit" }}>{draft}</pre>
      </div>
    </Modal>
  );
}

const CAT_LABEL: Record<string, string> = { ingestion: "Ingestion / mapping", data_quality: "Data quality", duplicate: "Duplicate", other: "Other" };

function AiTriage({ reportId, onFilter }: { reportId: string; onFilter: (checkType: string | null) => void }) {
  const [s, setS] = useState<ExceptionSummary | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(true);
  const [open, setOpen] = useState(true);
  // Bumped by "Regenerate": asks the API for a fresh summary instead of the stored one.
  const [regen, setRegen] = useState(0);
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async (initial: ExceptionSummary) => {
      if (!alive) return;
      setS(initial);
      if (initial.narrative_status !== "GENERATING") return;
      timer = setTimeout(async () => {
        try {
          const latest = await api.getExceptionSummary(reportId);
          if (latest) void poll(latest);
        } catch {
          if (alive) timer = setTimeout(() => void poll(initial), 2000);
        }
      }, 2000);
    };
    (async () => {
      try {
        const existing = regen ? null : await api.getExceptionSummary(reportId);
        const first = existing ?? (await api.generateExceptionSummary(reportId));
        await poll(first);
      } catch (e) {
        if (alive) setErr(e instanceof ApiError ? e.message : "Could not load the AI summary.");
      } finally {
        if (alive) setBusy(false);
      }
    })();
    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
    };
  }, [reportId, regen]);
  const regenerate = () => {
    setErr(null);
    setBusy(true);
    setRegen((n) => n + 1);
  };
  const a = s?.aggregate;
  const n = s?.narrative;
  const st = s?.narrative_status;
  return (
    <section className="tb-card flex flex-col" aria-labelledby="ai-triage">
      <button type="button" onClick={() => setOpen((v) => !v)} className="flex cursor-pointer items-center gap-3 px-5 py-4 text-left" aria-expanded={open}>
        <ListChecks size={18} style={{ color: "var(--muted)" }} />
        <span id="ai-triage" className="flex-1 text-[15px] font-medium">Exception triage</span>
        <StatusPill tone={st === "COMPLETE" ? "med" : st === "FAILED" ? "err" : "muted"}>{busy || st === "GENERATING" ? "Generating…" : st === "COMPLETE" ? "Drafted summary" : st === "UNAVAILABLE" ? "AI not configured" : st === "FAILED" ? "AI summary failed" : "Summary"}</StatusPill>
      </button>
      {open && (
        <div className="flex flex-col gap-4 px-5 pb-5">
          <div className="flex flex-wrap items-center gap-3 text-[12.5px]" style={{ color: "var(--faint)" }}>
            {s?.completed_at && st !== "GENERATING" && <span>Generated {formatDateTime(s.completed_at)}</span>}
            {(busy || st === "GENERATING") && <span>The report is already complete; this summary fills in separately and blocks nothing.</span>}
            <button type="button" className="tb-btn ml-auto !px-2.5 !py-1.5 text-[12.5px]" disabled={busy || st === "GENERATING"} onClick={regenerate}>
              {busy || st === "GENERATING" ? "Generating…" : "Regenerate"}
            </button>
          </div>
          {err && <ErrorState title="Triage could not be loaded" message={err} />}
          {a && (
            <div className="tnum grid grid-cols-2 gap-3 sm:grid-cols-4">
              {[
                [formatNumber(a.total_exceptions), "total exceptions"],
                [a.total_value_at_stake.map((m) => formatMoney(m.amount, m.currency)).join(" · ") || "-", "value at stake"],
                [`${formatNumber(a.root_cause_split.ingestion.count)} · ${formatPct(a.root_cause_split.ingestion.pct_of_total_exceptions)}`, "likely ingestion issues"],
                [`${formatNumber(a.root_cause_split.data_quality.count)} · ${formatPct(a.root_cause_split.data_quality.pct_of_total_exceptions)}`, "likely data issues"],
              ].map(([v, l]) => (
                <div key={l} className="flex flex-col gap-0.5">
                  <span className="text-[20px] font-medium">{v}</span>
                  <span className="text-[12px]" style={{ color: "var(--muted)" }}>{l}</span>
                </div>
              ))}
            </div>
          )}
          {n && (
            <div className="flex flex-col gap-3">
              <p className="m-0 max-w-[820px] text-[14px] leading-[1.6]">{n.executive_summary}</p>
              <ul className="m-0 flex list-none flex-col gap-2 p-0">
                {n.actions.map((x, i) => (
                  <li key={i} className="flex flex-wrap items-baseline gap-2 text-[13px]">
                    <StatusPill tone="muted">{CAT_LABEL[x.category] ?? x.category}</StatusPill>
                    <span className="font-medium">{x.title}</span>
                    <span style={{ color: "var(--muted)" }}>{x.rationale}</span>
                    {x.filter_check_type && (
                      <button type="button" className="cursor-pointer text-[12.5px] underline" style={{ color: "var(--accentText)" }} onClick={() => onFilter(x.filter_check_type)}>
                        Show these
                      </button>
                    )}
                  </li>
                ))}
              </ul>
              <div className="grid grid-cols-[minmax(0,1fr)] gap-4 md:grid-cols-2">
                {([
                  ["Fix in the tool (ingestion / mapping)", n.ingestion_issues, "No likely ingestion issues identified."],
                  ["Query with the cedant (data quality)", n.data_issues, "No likely genuine data issues identified."],
                ] as const).map(([h, list, none]) => (
                  <div key={h} className="flex flex-col gap-1.5 rounded-md p-4" style={{ boxShadow: "inset 0 0 0 1px var(--line)" }}>
                    <span className="text-[13px] font-medium">{h}</span>
                    {list.length ? (
                      <ul className="m-0 flex flex-col gap-1 pl-4 text-[13px]" style={{ color: "var(--muted)" }}>{list.map((x, i) => <li key={i}>{x}</li>)}</ul>
                    ) : (
                      <span className="text-[12.5px]" style={{ color: "var(--faint)" }}>{none}</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
          {st === "UNAVAILABLE" && <span className="text-[13px]" style={{ color: "var(--muted)" }}>The counts above are exact. A written AI summary needs an AI provider configured on the server.</span>}
          {st === "FAILED" && <span className="text-[13px]" style={{ color: "var(--muted)" }}>{s?.narrative_error ?? "The AI summary could not be generated."} The counts above are exact.</span>}
          {s?.narrative_warning && <span className="text-[12.5px]" style={{ color: "var(--warn)" }}>{s.narrative_warning}</span>}
        </div>
      )}
    </section>
  );
}
