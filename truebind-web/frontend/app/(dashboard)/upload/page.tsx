"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import type { MappingField, Report, Sheet } from "@/lib/types";
import { FileUpload } from "@/components/upload/FileUpload";
import { SheetsList } from "@/components/upload/SheetsList";
import { MappingConfirmation } from "@/components/upload/MappingConfirmation";
import { AlertBanner } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { formatBytes } from "@/lib/formatters";
import styles from "./page.module.css";

export default function UploadPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [stage, setStage] = useState<string | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [sheets, setSheets] = useState<Sheet[]>([]);
  const [activeSheet, setActiveSheet] = useState<string | null>(null);
  const [fields, setFields] = useState<MappingField[]>([]);
  const [headers, setHeaders] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Upload only stores the file and queues an INGEST job; the worker reads
  // the workbook and proposes a mapping. Wait for that job, then show sheets.
  async function loadForReview(reportId: string) {
    const done = await api.waitForReport(reportId, (r) => {
      setReport(r);
      setStage(r.job?.stage ?? r.status);
    });
    setStage(null);
    if (done.status !== "WAITING_FOR_REVIEW" && done.status !== "COMPLETE") {
      setError(done.processing_error || done.job?.error_message || `The file could not be read (status ${done.status}).`);
      return;
    }
    const sheetList = await api.listSheets(reportId);
    setSheets(sheetList);
    const firstOpen = sheetList.find((s) => s.status === "PENDING_CONFIRMATION") ?? sheetList.find((s) => s.status !== "SKIPPED");
    if (firstOpen) setActiveSheet(firstOpen.id);
  }

  async function handleFile(file: File) {
    setBusy(true);
    setError(null);
    try {
      const uploaded = await api.uploadReport(file);
      setReport(uploaded);
      await loadForReview(uploaded.id);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not upload the file.");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    const resumeId = searchParams.get("reportId");
    if (!resumeId || report) return;
    void (async () => {
      setBusy(true);
      try {
        await loadForReview(resumeId);
      } catch (e) {
        setError(e instanceof ApiError ? e.message : "Could not load this report.");
      } finally {
        setBusy(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  useEffect(() => {
    if (!report || !activeSheet) return;
    let cancelled = false;
    (async () => {
      try {
        const m = await api.getSheetMappingFull(report.id, activeSheet);
        if (!cancelled) {
          setFields(m.fields);
          setHeaders(m.headers);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof ApiError ? e.message : "Could not load this sheet's mapping.");
      }
    })();
    return () => { cancelled = true; };
  }, [report?.id, activeSheet]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleConfirm(choices: Record<string, string | null>) {
    if (!report || !activeSheet) return;
    setBusy(true);
    setError(null);
    try {
      await api.confirmSheetMapping(report.id, activeSheet, choices);
      const sheetList = await api.listSheets(report.id);
      setSheets(sheetList);
      const nextOpen = sheetList.find((s) => s.status === "PENDING_CONFIRMATION");
      // Cleared in the same batch as activeSheet so MappingConfirmation
      // never mounts using the outgoing sheet's fields while the new
      // sheet's mapping is still in flight (see useEffect below) --
      // that race previously let a later sheet silently submit an
      // earlier sheet's column names.
      setFields([]);
      setHeaders([]);
      setActiveSheet(nextOpen ? nextOpen.id : null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not confirm this sheet's mapping.");
    } finally {
      setBusy(false);
    }
  }

  async function handleProcess() {
    if (!report) return;
    setBusy(true);
    setError(null);
    try {
      await api.processReport(report.id);
      router.push(`/reports/${report.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not process this report.");
    } finally {
      setBusy(false);
    }
  }

  const allDone = sheets.length > 0 && sheets.every((s) => s.status !== "PENDING_CONFIRMATION");
  const activeFields = fields;

  const activeSheetObj = sheets.find((s) => s.id === activeSheet);

  if (report && sheets.length === 0) {
    return (
      <div className={styles.page}>
        <h1>{report.file_name}</h1>
        {error ? (
          <AlertBanner tone="error" title="The file could not be processed">{error}</AlertBanner>
        ) : (
          <AlertBanner tone="info" title="Reading your workbook…">
            {stage ? `Current step: ${stage.replace(/_/g, " ").toLowerCase()}.` : "Queued."} This updates automatically.
          </AlertBanner>
        )}
        {error && <Button onClick={() => { setReport(null); setError(null); router.replace("/upload"); }}>Upload another file</Button>}
      </div>
    );
  }

  if (!report) {
    return (
      <div className={`${styles.page} ${styles.landing}`}>
        <div className={styles.intro}>
          <span className="eyebrow">Step one of three</span>
          <h1>Bring any bordereau.</h1>
          <p className={styles.subhead}>Any sender&rsquo;s layout, any column order, one sheet or twenty.</p>
        </div>

        {error && <AlertBanner tone="error" title="Upload failed">{error}</AlertBanner>}
        <FileUpload onFile={handleFile} busy={busy} />

        <ol className={`stepList ${styles.explainer}`}>
          <li>
            <span className="stepNumber">01</span>
            <div>
              <p className="stepTitle">Every sheet, not the first</p>
              <p className="stepBody">A workbook can carry any number of sender tabs. Truebind inspects each one and detects its own header row, even below a title banner.</p>
            </div>
          </li>
          <li>
            <span className="stepNumber">02</span>
            <div>
              <p className="stepTitle">You confirm the mapping</p>
              <p className="stepBody">Every column is matched by alias or AI, never assumed. Nothing is ingested until you&rsquo;ve reviewed and confirmed each sheet&rsquo;s mapping.</p>
            </div>
          </li>
          <li>
            <span className="stepNumber">03</span>
            <div>
              <p className="stepTitle">Flags, never edits</p>
              <p className="stepBody">Mismatches, missing fields and probable duplicates are surfaced for review. Truebind never silently corrects or merges your data.</p>
            </div>
          </li>
        </ol>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.summary}>
        <div>
          <span className="eyebrow">Step two of three</span>
          <h1>{report.file_name}</h1>
          <span className={styles.meta}>{formatBytes(report.file_size_bytes)} · {report.sheet_count_total} sheet(s)</span>
        </div>
        <Button onClick={handleProcess} disabled={!allDone || busy}>
          {busy ? "Working…" : "Proceed to health report"}
        </Button>
      </div>

      {error && <AlertBanner tone="error" title="Something went wrong">{error}</AlertBanner>}

      <div className={styles.layout}>
        <aside className={styles.sheetsPane}>
          <h3>Sheets</h3>
          <SheetsList sheets={sheets} activeSheet={activeSheet} onSelect={setActiveSheet} />
        </aside>
        <div className={styles.mappingPane}>
          {activeSheet && activeFields.length > 0 ? (
            <MappingConfirmation
              key={activeSheet}
              sheetName={activeSheetObj?.sheet_name ?? ""}
              headerRowIndex={activeSheetObj?.header_row_index ?? null}
              fields={activeFields}
              headers={headers}
              onConfirm={handleConfirm}
              saving={busy}
            />
          ) : activeSheet ? (
            <p>Loading {activeSheetObj?.sheet_name}&rsquo;s mapping…</p>
          ) : (
            <AlertBanner tone="info" title="All sheets confirmed">
              Every sheet has been mapped or skipped. Click &ldquo;Proceed to health report&rdquo; above.
            </AlertBanner>
          )}
        </div>
      </div>
    </div>
  );
}
