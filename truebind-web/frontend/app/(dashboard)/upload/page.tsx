"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { api, ApiError, IN_PROGRESS } from "@/lib/api";
import type { Report, Sheet } from "@/lib/types";
import { formatBytes } from "@/lib/formatters";
import { useApi } from "@/lib/useApi";
import { Button, ButtonLink } from "@/components/ui/Button";
import { ErrorState, Icon, Panel, PageHeader, StatusPill, ds } from "@/components/ds";
import { useShell } from "@/components/layout/ShellContext";
import { ProcessingView } from "@/components/intake/ProcessingView";
import { MappingReview } from "@/components/intake/MappingReview";
import { ReportTable } from "@/components/ops/ReportTable";
import { IntakeStepper, intakeStep } from "@/components/intake/IntakeStepper";
import styles from "@/components/intake/intake.module.css";

const ACCEPT = ".xlsx,.xlsm,.xls,.csv";

export default function IntakePage() {
  const router = useRouter();
  const params = useSearchParams();
  const shell = useShell();
  const refreshShell = shell.refresh;  // stable callback
  const [report, setReport] = useState<Report | null>(null);
  const [sheets, setSheets] = useState<Sheet[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [upload, setUpload] = useState<{ name: string; sent: number; total: number } | null>(null);
  const [dragging, setDragging] = useState(false);
  const [sender, setSender] = useState("");
  const [programme, setProgramme] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const polling = useRef<string | null>(null);
  const recent = useApi(() => api.listReports(), []);

  /** Poll one report until it leaves an in-progress state, then load what the
   * next step needs. Polls fast (0.6 s) so a small file's review screen
   * appears as soon as the worker finishes. */
  const follow = useCallback(async (id: string) => {
    polling.current = id;
    try {
      for (;;) {
        const r = await api.getReport(id);
        if (polling.current !== id) return;
        setReport(r);
        if (!IN_PROGRESS.has(r.status)) {
          refreshShell();
          if (r.status === "WAITING_FOR_REVIEW") setSheets(await api.listSheets(id));
          if (r.status === "COMPLETE") router.push(`/reports/${id}`);
          return;
        }
        await new Promise((res) => setTimeout(res, 600));
      }
    } catch (e) {
      if (polling.current === id) setError(e instanceof ApiError ? e.message : "Lost contact with the server.");
    }
  }, [router, refreshShell]);

  useEffect(() => {
    const id = params.get("reportId");
    if (!id || polling.current === id) return;
    const t = setTimeout(() => { void follow(id); }, 0);
    return () => clearTimeout(t);
  }, [params, follow]);

  useEffect(() => () => { polling.current = null; }, []);

  async function handleFile(file: File) {
    setError(null);
    setUpload({ name: file.name, sent: 0, total: file.size });
    try {
      const r = await api.uploadWithProgress(file, { sender, programme }, (sent, total) => setUpload({ name: file.name, sent, total }));
      setUpload(null);
      setReport(r);
      router.replace(`/upload?reportId=${r.id}`);
      shell.refresh();
      void follow(r.id);
    } catch (e) {
      setUpload(null);
      setError(e instanceof ApiError ? e.message : "The upload failed.");
    }
  }

  async function startProcessing() {
    if (!report) return;
    const r = await api.processReport(report.id);
    setReport(r);
    void follow(r.id);
  }

  function reset() {
    polling.current = null;
    setReport(null);
    setSheets([]);
    setError(null);
    router.replace("/upload");
  }

  // ---------------------------------------------------------------- views
  if (report && (IN_PROGRESS.has(report.status) || report.status === "FAILED" || report.status === "CANCELLED")) {
    return (
      <>
        <PageHeader eyebrow="Intake" title={report.file_name}
          description={<>{formatBytes(report.file_size_bytes)} · {(report.file_kind ?? "").toUpperCase()}{report.sender ? ` · from ${report.sender}` : ""}</>}
          actions={<><StatusPill status={report.status} /><Button variant="secondary" onClick={reset}>Upload another</Button></>} />
        <IntakeStepper current={intakeStep(report, false)} failed={report.status === "FAILED"} />
        <ProcessingView report={report} system={shell.system}
          onCancel={IN_PROGRESS.has(report.status) ? () => api.cancelReport(report.id).then(setReport).catch((e) => setError(String(e.message ?? e))) : undefined}
          onRetry={report.status === "FAILED" ? () => api.retryReport(report.id).then((r) => { setReport(r); void follow(r.id); }).catch((e) => setError(String(e.message ?? e))) : () => shell.refresh()} />
        {error && <div style={{ marginTop: 16, maxWidth: 760 }}><ErrorState message={error} /></div>}
      </>
    );
  }

  if (report && report.status === "WAITING_FOR_REVIEW") {
    return (
      <>
        <PageHeader eyebrow="Intake · review mapping" title={report.file_name}
          description="TrueBind proposed a source column for every canonical field. Check anything marked “Needs review” or “Ambiguous”, confirm each sheet, then produce the report."
          actions={<><StatusPill status={report.status} /><Button variant="ghost" onClick={reset}>Upload another</Button></>} />
        <IntakeStepper current={4} />
        {sheets.length ? (
          <MappingReview report={report} sheets={sheets} onSheetsChange={setSheets} onProcess={startProcessing} />
        ) : <Panel><p style={{ margin: 0 }}>Loading sheets…</p></Panel>}
      </>
    );
  }

  if (report && report.status === "COMPLETE") {
    return (
      <Panel>
        <p style={{ marginTop: 0 }}>This report is complete.</p>
        <ButtonLink href={`/reports/${report.id}`} variant="primary">Open the report</ButtonLink>
      </Panel>
    );
  }

  const pct = upload && upload.total ? Math.round((100 * upload.sent) / upload.total) : 0;
  return (
    <>
      <PageHeader eyebrow="Intake" title="Bring in a bordereau"
        description="Any sender's layout, any column order, one sheet or many. TrueBind reads every sheet, finds its header row, proposes a mapping, then validates and reconciles every row." />
      <IntakeStepper current={intakeStep(null, !!upload)} />
      <div className={styles.layout}>
        <div className={ds.stack}>
          <Panel>
            <label
              className={`${styles.drop} ${dragging ? styles.dragging : ""}`}
              onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => { e.preventDefault(); setDragging(false); const f = e.dataTransfer.files?.[0]; if (f) void handleFile(f); }}>
              <span className={styles.dropIcon}><Icon name="upload" size={24} /></span>
              <p className={styles.dropTitle}>{upload ? `Uploading ${upload.name}…` : "Drop a workbook here, or browse"}</p>
              <p className={styles.dropHint}>.xlsx · .xlsm · .xls · .csv — macros are never run; password-protected files are rejected</p>
              <input ref={fileInput} type="file" accept={ACCEPT} className="sr-only" disabled={!!upload}
                     onChange={(e) => { const f = e.target.files?.[0]; if (f) void handleFile(f); e.target.value = ""; }} />
              {!upload && <span className={ds.input} style={{ display: "inline-flex", alignItems: "center", fontWeight: 600 }}>Choose file</span>}
              {upload && (
                <div style={{ width: "100%", maxWidth: 420 }} aria-live="polite">
                  <div className={styles.progress}><div className={styles.progressFill} style={{ width: `${pct}%` }} /></div>
                  <p className={styles.dropHint} style={{ marginTop: 6 }}>{formatBytes(upload.sent)} of {formatBytes(upload.total)} sent</p>
                </div>
              )}
            </label>
            <div className={styles.meta}>
              <label className={styles.field}>Sender (optional)
                <input className={ds.input} value={sender} onChange={(e) => setSender(e.target.value)} maxLength={200} placeholder="e.g. Meridian MGA" />
              </label>
              <label className={styles.field}>Programme / account (optional)
                <input className={ds.input} value={programme} onChange={(e) => setProgramme(e.target.value)} maxLength={200} placeholder="e.g. Property binder 2024" />
              </label>
            </div>
          </Panel>
          {error && <ErrorState title="Upload failed" message={error} />}
          <Panel title="Recent intake" icon="inbox" flush actions={<Link href="/inbox" className={ds.muted}>Inbox →</Link>}>
            {(recent.data ?? []).length ? <ReportTable reports={(recent.data ?? []).slice(0, 5)} /> : <p className={ds.muted} style={{ padding: "0 20px 16px" }}>Nothing yet.</p>}
          </Panel>
        </div>
        <Panel title="What happens next" icon="automations">
          <ol className={styles.steps}>
            <li><div><p className={styles.stepTitle}>File checks</p><p className={styles.stepBody}>Type, size and structure are verified before anything reads it.</p></div></li>
            <li><div><p className={styles.stepTitle}>Workbook reading</p><p className={styles.stepBody}>Every sheet is inspected; header rows are found even below titles. Totals and blank lines are recorded, never counted.</p></div></li>
            <li><div><p className={styles.stepTitle}>Mapping proposal</p><p className={styles.stepBody}>Columns are matched to Lloyd&rsquo;s CRS fields by alias rules first; AI is used only for headers the rules can&rsquo;t place (headers only, never cell values).</p></div></li>
            <li><div><p className={styles.stepTitle}>You confirm</p><p className={styles.stepBody}>Nothing is validated until you accept or correct each sheet&rsquo;s mapping.</p></div></li>
            <li><div><p className={styles.stepTitle}>Validation &amp; report</p><p className={styles.stepBody}>Arithmetic, required data, duplicates vs development, and a row-by-row reconciliation.</p></div></li>
          </ol>
        </Panel>
      </div>
    </>
  );
}
