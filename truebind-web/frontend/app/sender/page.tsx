"use client";

import { useState } from "react";
import { PaperPlaneTilt, Tray } from "@phosphor-icons/react";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { useUi } from "@/lib/ui";
import { formatDateTime } from "@/lib/formatters";
import type { Preflight } from "@/lib/types";
import { useMe } from "@/components/auth/AuthGate";
import { Dropzone } from "@/components/nocturne/intake";
import { EmptyState, ErrorState, LoadingState, PageHeader, StatusPill } from "@/components/nocturne/ui";
import type { Tone } from "@/components/nocturne/status";

const errorText = (e: unknown) => (e instanceof ApiError ? e.message : "Please try again.");

/** A submission's status from the sender's side: they only need to know it arrived and where it is. */
function submissionStatus(s: string): { label: string; tone: Tone } {
  if (["UPLOADED", "QUEUED", "INGESTING", "PROCESSING"].includes(s)) return { label: "Being checked", tone: "med" };
  if (s === "WAITING_FOR_REVIEW") return { label: "With the reviewer", tone: "med" };
  if (s === "COMPLETE") return { label: "Received · checked", tone: "ok" };
  if (s === "FAILED") return { label: "Could not be read", tone: "err" };
  if (s === "CANCELLED") return { label: "Cancelled", tone: "muted" };
  if (s === "EXPIRED") return { label: "Expired", tone: "muted" };
  return { label: s, tone: "muted" };
}

function Count({ n, label, bad }: { n: number; label: string; bad?: boolean }) {
  return (
    <div className="flex flex-col gap-1 rounded-md px-4 py-3" style={{ background: "var(--bg2)", boxShadow: "inset 0 0 0 1px var(--line)" }}>
      <span className="tnum text-[22px] font-medium" style={{ color: bad && n > 0 ? "var(--warn)" : "var(--text)" }}>{n.toLocaleString("en-GB")}</span>
      <span className="text-[12.5px]" style={{ color: "var(--muted)" }}>{label}</span>
    </div>
  );
}

function Result({ r }: { r: Preflight }) {
  return (
    <div className="flex flex-col gap-4" aria-live="polite">
      <div className="flex flex-wrap items-center gap-3">
        <StatusPill tone={r.ready ? "ok" : "warn"}>{r.ready ? "Ready to send" : "Needs attention"}</StatusPill>
        <span className="text-[14px]">{r.verdict}</span>
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Count n={r.rows} label="rows read" />
        <Count n={r.missing_mandatory_rows} label="rows missing a mandatory field" bad />
        <Count n={r.arithmetic_mismatches} label="rows whose amounts don’t add up" bad />
        <Count n={r.exact_duplicates} label="exact duplicate rows" bad />
      </div>
      <p className="m-0 text-[12.5px]" style={{ color: "var(--faint)" }}>{r.coverage_statement}</p>
      <div className="overflow-x-auto rounded-md" style={{ boxShadow: "inset 0 0 0 1px var(--line)" }}>
        <table className="w-full min-w-[560px] border-collapse text-[13px]">
          <caption className="sr-only">Sheets and the columns recognised</caption>
          <thead>
            <tr className="text-left text-[11px] uppercase tracking-[.06em]" style={{ color: "var(--faint)" }}>
              {["Sheet", "Rows", "Required fields not found", "Columns not recognised"].map((h) => <th key={h} scope="col" className="px-4 py-2.5 font-medium">{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {r.sheets.map((s) => (
              <tr key={s.sheet_name} style={{ boxShadow: "0 -1px 0 var(--line)" }}>
                <th scope="row" className="px-4 py-2.5 text-left font-medium">{s.sheet_name}</th>
                <td className="tnum px-4 py-2.5">{s.rows.toLocaleString("en-GB")}</td>
                <td className="px-4 py-2.5" style={{ color: s.missing_required_fields.length ? "var(--warn)" : undefined }}>{s.missing_required_fields.join(", ") || "None"}</td>
                <td className="px-4 py-2.5">{s.unmapped_columns.join(", ") || "None"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {r.issues.length > 0 && (
        <div className="flex flex-col gap-2">
          <span className="text-[14px] font-medium">
            Issues ({r.issues_total.toLocaleString("en-GB")}
            {r.issues_total > r.issues.length ? `, first ${r.issues.length} shown` : ""})
          </span>
          <ul className="m-0 flex list-none flex-col p-0 text-[13px]">
            {r.issues.map((i, n) => (
              <li key={n} className="grid grid-cols-1 gap-x-3 gap-y-0.5 py-2 sm:grid-cols-[160px_1fr]" style={{ boxShadow: "0 -1px 0 var(--line)" }}>
                <span className="tnum" style={{ color: "var(--faint)" }}>{i.sheet_name ?? "File"}{i.row_number != null ? ` · row ${i.row_number}` : ""}</span>
                <span className="[overflow-wrap:anywhere]">{i.message}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default function SenderPage() {
  const me = useMe();
  const { toast } = useUi();
  const subs = useApi(() => api.senderSubmissions(), []);
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<Preflight | null>(null);
  const [busy, setBusy] = useState<"check" | "send" | null>(null);
  const org = me?.tenant.name ?? "the organisation";

  const check = async (f: File) => {
    setFile(f);
    setBusy("check");
    setResult(null);
    try {
      setResult(await api.senderPreflight(f));
    } catch (e) {
      toast(`File not checked: ${errorText(e)}`, "err");
    } finally {
      setBusy(null);
    }
  };
  const send = async () => {
    if (!file) return;
    setBusy("send");
    try {
      await api.senderSubmit(file);
      toast(`${file.name} was sent to ${org}`, "ok");
      setFile(null);
      setResult(null);
      subs.reload();
    } catch (e) {
      toast(`Not sent: ${errorText(e)}`, "err");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="mx-auto flex max-w-[1100px] flex-col gap-6 px-4 pb-12 pt-8 sm:px-9">
      <PageHeader kicker="Sender portal" title="Check a bordereau before you send it" sub={`Run the same checks ${org} runs, fix what you can, then send. The pre-flight check keeps nothing: the file is checked and discarded.`} />
      <section className="tb-card flex flex-col gap-5 p-4 sm:p-6">
        <div className="flex flex-col gap-1">
          <span className="text-[16px] font-medium">Pre-flight check</span>
          <span className="text-[13px]" style={{ color: "var(--muted)" }}>Excel (.xlsx, .xls, .xlsm) or CSV.</span>
        </div>
        <Dropzone upload={null} onFile={(f) => void check(f)} />
        {file && (
          <div className="flex flex-wrap items-center gap-3">
            <span className="min-w-0 flex-1 truncate text-[13.5px]">{file.name}</span>
            <button type="button" className="tb-btn" disabled={busy !== null} onClick={() => void check(file)}>{busy === "check" ? "Checking…" : "Check again"}</button>
            <button type="button" className={`tb-btn ${result?.ready ? "tb-btn-solid" : "tb-btn-primary"}`} disabled={busy !== null} onClick={() => void send()}>
              <PaperPlaneTilt />
              {busy === "send" ? "Sending…" : `Send to ${org}`}
            </button>
          </div>
        )}
        {busy === "check" && <LoadingState label="Checking the file" rows={4} />}
        {result && <Result r={result} />}
      </section>
      <section className="tb-card flex flex-col gap-4 p-4 sm:p-6">
        <div className="flex flex-col gap-1">
          <span className="text-[16px] font-medium">Your submissions</span>
          <span className="text-[13px]" style={{ color: "var(--muted)" }}>Files you have sent and where they are. {org} reviews them in its own workspace.</span>
        </div>
        {subs.error ? (
          <ErrorState title="Your submissions could not be loaded" message={subs.error} onRetry={subs.reload} />
        ) : !subs.data ? (
          <LoadingState label="Loading submissions" rows={3} />
        ) : subs.data.length === 0 ? (
          <EmptyState icon={<Tray />} title="Nothing sent yet" body="Files you send appear here with their status." />
        ) : (
          <div className="overflow-x-auto rounded-md" style={{ boxShadow: "inset 0 0 0 1px var(--line)" }}>
            <table className="w-full min-w-[520px] border-collapse text-[13px]">
              <caption className="sr-only">Your submissions, newest first</caption>
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-[.06em]" style={{ color: "var(--faint)" }}>
                  {["File", "Rows", "Sent", "Status"].map((h) => <th key={h} scope="col" className="px-4 py-2.5 font-medium">{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {subs.data.map((s) => {
                  const st = submissionStatus(s.status);
                  return (
                    <tr key={s.id} style={{ boxShadow: "0 -1px 0 var(--line)" }}>
                      <th scope="row" className="px-4 py-2.5 text-left font-medium">{s.file_name}</th>
                      <td className="tnum px-4 py-2.5">{s.rows_total ? s.rows_total.toLocaleString("en-GB") : "—"}</td>
                      <td className="tnum px-4 py-2.5">{formatDateTime(s.created_at)}</td>
                      <td className="px-4 py-2.5"><StatusPill tone={st.tone}>{st.label}</StatusPill></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
