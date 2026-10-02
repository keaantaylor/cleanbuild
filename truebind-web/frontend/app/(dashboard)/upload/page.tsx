"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { api, IN_PROGRESS } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { useShell } from "@/components/layout/ShellContext";
import { ErrorState, LoadingState, PageHeader, StatusPill } from "@/components/nocturne/ui";
import { Dropzone, FileGlyph, IntakeStepper, MappingReview, ProcessingPanel, intakeStep, useIntake } from "@/components/nocturne/intake";
import { reportStatus } from "@/components/nocturne/status";
import { timeAgo } from "@/lib/formatters";

export default function IntakePage() {
  return (
    <Suspense>
      <Intake />
    </Suspense>
  );
}

function Intake() {
  const router = useRouter();
  const params = useSearchParams();
  const shell = useShell();
  const [sender, setSender] = useState("");
  const [programme, setProgramme] = useState("");
  const recent = useApi(() => api.listReports(), []);
  const flow = useIntake({
    onChange: () => {
      shell.refresh();
      recent.reload();
    },
    onComplete: (r) => router.push(`/reports/${r.id}`),
  });
  const { report, sheets, setSheets, error, upload, start, follow, process, cancel, retry, reset } = flow;

  // Deep links (?reportId=) from the work queue, Inbox and alerts resume a file mid-flow.
  const reportId = params.get("reportId");
  useEffect(() => {
    if (reportId) void follow(reportId);
  }, [reportId, follow]);

  const onFile = async (f: File) => {
    const r = await start(f, { sender: sender.trim() || undefined, programme: programme.trim() || undefined });
    if (r) router.replace(`/upload?reportId=${r.id}`);
  };
  const again = () => {
    reset();
    router.replace("/upload");
  };

  const header = (
    <PageHeader
      kicker="Intake"
      title={report ? report.file_name : "Bring in a bordereau"}
      sub={
        report
          ? report.status === "WAITING_FOR_REVIEW"
            ? "TrueBind proposed a source column for every Lloyd’s CRS field. Check anything marked “Needs review” or “Ambiguous”, confirm each sheet, then produce the report."
            : `${report.sender ? `From ${report.sender} · ` : ""}${reportStatus(report).label}`
          : "Any sender’s layout, any column order, one sheet or many. TrueBind reads every sheet, finds its header row, proposes a mapping, then validates and reconciles every row."
      }
      actions={
        report ? (
          <>
            <StatusPill tone={reportStatus(report).tone}>{reportStatus(report).label}</StatusPill>
            <button type="button" className="tb-btn" onClick={again}>
              Upload another
            </button>
          </>
        ) : undefined
      }
    />
  );

  return (
    <div className="flex max-w-[1440px] flex-col gap-6 px-4 pb-12 pt-8 sm:px-6">
      {header}
      <IntakeStepper current={intakeStep(report, !!upload)} failed={report?.status === "FAILED"} />

      {report && (IN_PROGRESS.has(report.status) || report.status === "FAILED" || report.status === "CANCELLED") && (
        <ProcessingPanel report={report} system={shell.system} onCancel={IN_PROGRESS.has(report.status) ? cancel : undefined} onRetry={report.status === "FAILED" || report.status === "CANCELLED" ? retry : shell.refresh} />
      )}

      {report?.status === "WAITING_FOR_REVIEW" &&
        (sheets.length ? <MappingReview report={report} sheets={sheets} onSheetsChange={setSheets} onProcess={process} /> : <LoadingState label="Loading sheets" rows={6} />)}

      {report?.status === "COMPLETE" && (
        <div className="tb-card flex flex-wrap items-center gap-4 p-4 sm:p-5">
          <span className="flex-1 text-[14px]">This report is complete.</span>
          <Link href={`/reports/${report.id}`} className="tb-btn tb-btn-solid">
            Open the report
          </Link>
        </div>
      )}

      {report?.status === "EXPIRED" && <ErrorState title="This file has expired" message="Its retention period ended and the source file was removed. Upload it again to re-run the checks." onRetry={again} />}

      {error && <ErrorState title="Something went wrong" message={error} />}

      {!report && (
        <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
          <div className="flex flex-col gap-4">
            <Dropzone upload={upload} onFile={onFile} />
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className="tb-label" htmlFor="in-sender">Sender (optional)</label>
                <input id="in-sender" className="tb-input" value={sender} onChange={(e) => setSender(e.target.value)} maxLength={200} placeholder="e.g. Harbour MGA" disabled={!!upload} />
              </div>
              <div>
                <label className="tb-label" htmlFor="in-programme">Programme / account (optional)</label>
                <input id="in-programme" className="tb-input" value={programme} onChange={(e) => setProgramme(e.target.value)} maxLength={200} placeholder="e.g. Property binder 2026" disabled={!!upload} />
              </div>
            </div>
            <div className="tb-card flex flex-col gap-3 p-4">
              <span className="text-[15px] font-medium">What happens next</span>
              <ol className="m-0 flex list-none flex-col gap-2.5 p-0 text-[13px]">
                {[
                  ["File checks", "Type, size and structure are verified before anything reads it."],
                  ["Workbook reading", "Every sheet is inspected; header rows are found even below titles. Totals and blank lines are recorded, never counted."],
                  ["Mapping proposal", "Columns are matched to Lloyd’s CRS fields by alias rules first; AI is used only for headers the rules can’t place (headers only, never cell values)."],
                  ["You confirm", "Nothing is validated until you accept or correct each sheet’s mapping."],
                  ["Validation & report", "Arithmetic, required data, duplicates vs development, and a row-by-row reconciliation."],
                ].map(([t, d], i) => (
                  <li key={t} className="grid grid-cols-[22px_1fr] gap-2.5">
                    <span className="tnum grid h-[22px] w-[22px] place-items-center rounded-full text-[11px]" style={{ boxShadow: "inset 0 0 0 1px var(--line2)", color: "var(--muted)" }}>{i + 1}</span>
                    <span>
                      <span className="font-medium">{t}. </span>
                      <span style={{ color: "var(--muted)" }}>{d}</span>
                    </span>
                  </li>
                ))}
              </ol>
            </div>
          </div>
          <div className="flex flex-col gap-3">
            <div className="flex items-baseline justify-between">
              <span className="text-[15px] font-medium">Recent intakes</span>
              <Link href="/inbox" className="text-[12.5px]" style={{ color: "var(--accentText)" }}>Inbox →</Link>
            </div>
            <div className="tb-card overflow-hidden">
              {recent.error && !recent.data ? (
                <div className="p-4"><ErrorState title="Recent intakes could not be loaded" message={recent.error} onRetry={recent.reload} /></div>
              ) : !recent.data ? (
                <div className="p-4"><LoadingState label="Loading recent intakes" rows={5} /></div>
              ) : recent.data.length === 0 ? (
                <p className="m-0 px-4 py-6 text-center text-[13px]" style={{ color: "var(--faint)" }}>Nothing yet. Your first file will appear here.</p>
              ) : (
                recent.data.slice(0, 7).map((r) => {
                  const st = reportStatus(r);
                  return (
                    <Link key={r.id} href={st.href} className="flex items-center gap-3 px-4 py-3 transition-colors hover:bg-[var(--accentTint)]" style={{ boxShadow: "0 1px 0 var(--line)" }}>
                      <FileGlyph name={r.file_name} size={18} />
                      <span className="flex min-w-0 flex-1 flex-col">
                        <span className="truncate text-[13px] font-medium">{r.file_name}</span>
                        <span className="text-[12px]" style={{ color: "var(--faint)" }}>{r.sender ? `${r.sender} · ` : ""}{timeAgo(r.created_at)}</span>
                      </span>
                      <StatusPill tone={st.tone}>{st.label}</StatusPill>
                    </Link>
                  );
                })
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
