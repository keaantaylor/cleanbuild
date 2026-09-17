"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
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
  const [report, setReport] = useState<Report | null>(null);
  const [sheets, setSheets] = useState<Sheet[]>([]);
  const [activeSheet, setActiveSheet] = useState<string | null>(null);
  const [fields, setFields] = useState<MappingField[]>([]);
  const [headers, setHeaders] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleFile(file: File) {
    setBusy(true);
    setError(null);
    try {
      const uploaded = await api.uploadReport(file);
      setReport(uploaded);
      const sheetList = await api.listSheets(uploaded.id);
      setSheets(sheetList);
      const firstOpen = sheetList.find((s) => s.status !== "SKIPPED");
      if (firstOpen) setActiveSheet(firstOpen.sheet_name);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not upload the file.");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (!report || !activeSheet) return;
    let cancelled = false;
    (async () => {
      const [mapping, headerList] = await Promise.all([
        api.getSheetMapping(report.id, activeSheet),
        api.getSheetHeaders(report.id, activeSheet),
      ]);
      if (!cancelled) {
        setFields(mapping);
        setHeaders(headerList);
      }
    })();
    return () => { cancelled = true; };
  }, [report, activeSheet]);

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
      setActiveSheet(nextOpen ? nextOpen.sheet_name : null);
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

  if (!report) {
    return (
      <div className={styles.page}>
        <h1>Upload a bordereau</h1>
        <p className={styles.intro}>
          Upload a single sheet or a whole multi-sheet workbook. Every sheet gets its own header-row
          detection and column mapping, reviewed before anything is ingested.
        </p>
        {error && <AlertBanner tone="error" title="Upload failed">{error}</AlertBanner>}
        <FileUpload onFile={handleFile} busy={busy} />
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.summary}>
        <div>
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
              sheetName={activeSheet}
              headerRowIndex={sheets.find((s) => s.sheet_name === activeSheet)?.header_row_index ?? null}
              fields={activeFields}
              headers={headers}
              onConfirm={handleConfirm}
              saving={busy}
            />
          ) : activeSheet ? (
            <p>Loading {activeSheet}&rsquo;s mapping…</p>
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
