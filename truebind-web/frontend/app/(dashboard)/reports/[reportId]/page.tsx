"use client";

import { use, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { Report, ReportSummary } from "@/lib/types";
import { CoverageBanner } from "@/components/report/CoverageBanner";
import { GradeCard } from "@/components/report/GradeCard";
import { CompletenessChart } from "@/components/report/CompletenessChart";
import { MetricCard } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { AlertBanner } from "@/components/ui/Alert";
import styles from "./page.module.css";

const POLL_INTERVAL_MS = 1500;

const PHASE_LABELS: Record<string, string> = {
  queued: "Queued",
  "loading workbook": "Reading the workbook",
  "proposing mapping": "Proposing column mappings",
  "validating and deduplicating": "Validating and checking for duplicates",
  "persisting results": "Saving results",
};

export default function ReportDetailPage({ params }: { params: Promise<{ reportId: string }> }) {
  const { reportId } = use(params);
  const [report, setReport] = useState<Report | null>(null);
  const [summary, setSummary] = useState<ReportSummary | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function tick() {
      const r = await api.getReport(reportId);
      if (cancelled) return;
      setReport(r);

      if (r.status === "COMPLETE") {
        const s = await api.getReportSummary(reportId);
        if (!cancelled) setSummary(s);
        return;
      }
      if (r.status === "PROCESSING") {
        timerRef.current = setTimeout(tick, POLL_INTERVAL_MS);
      }
    }

    tick();
    return () => {
      cancelled = true;
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [reportId]);

  if (!report) return <p>Loading…</p>;

  if (report.status === "FAILED") {
    return (
      <div className={styles.page}>
        <div className={styles.header}>
          <h1>{report.file_name}</h1>
        </div>
        <AlertBanner tone="error" title="Processing failed">
          {report.processing_error || "This report could not be processed. Please try uploading it again."}
        </AlertBanner>
      </div>
    );
  }

  if (report.status === "PENDING_MAPPING" || report.status === "READY_FOR_REVIEW") {
    return (
      <div className={styles.page}>
        <div className={styles.header}>
          <h1>{report.file_name}</h1>
        </div>
        <AlertBanner tone="info" title="Mapping not yet confirmed">
          This report hasn&rsquo;t been processed yet. Go back to the upload screen to finish
          confirming each sheet&rsquo;s mapping, then click &ldquo;Proceed to health report&rdquo;.
        </AlertBanner>
      </div>
    );
  }

  if (report.status !== "COMPLETE" || !summary) {
    // Real progress instead of an indefinite spinner: which phase is
    // running now (fix spec Section 6.2), so a reviewer can tell "still
    // working" from "hung" at a glance.
    const phaseLabel = report.processing_phase ? (PHASE_LABELS[report.processing_phase] ?? report.processing_phase) : null;
    return (
      <div className={styles.page}>
        <div className={styles.header}>
          <h1>{report.file_name}</h1>
        </div>
        <AlertBanner tone="info" title="Generating report…">
          <div className={styles.progress}>
            <span className={styles.spinner} aria-hidden="true" />
            {phaseLabel ? `${phaseLabel}…` : "Working…"}
          </div>
        </AlertBanner>
      </div>
    );
  }

  const { report: reportDetail } = summary;
  const cappedByCoverage = summary.sheets_processed !== summary.sheets_total || reportDetail.rows_processed !== reportDetail.rows_total;

  const bySheet = Object.entries(summary.missing_mandatory_by_sheet).sort((a, b) => b[1] - a[1]);

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1>{reportDetail.file_name}</h1>
        <div className={styles.actions}>
          <Button variant="secondary" onClick={() => window.open(api.exportAuditCsvUrl(reportId), "_blank")}>
            Export audit trail
          </Button>
          <Button variant="secondary" onClick={() => window.open(api.exportByStatusUrl(reportId), "_blank")}>
            Export by status
          </Button>
        </div>
      </div>

      <CoverageBanner
        rowsAssessed={reportDetail.rows_processed}
        rowsTotal={reportDetail.rows_total}
        sheetsProcessed={summary.sheets_processed}
        sheetsTotal={summary.sheets_total}
      />

      <div className={styles.topRow}>
        <GradeCard grade={reportDetail.grade} score={reportDetail.score} cappedByCoverage={cappedByCoverage} />
        <div className={styles.metrics}>
          <MetricCard label="Missing mandatory" value={summary.missing_mandatory_rows} tone="error" icon="⚠" />
          <MetricCard label="Arithmetic mismatches" value={summary.arithmetic_mismatches} tone="warning" icon="≠" />
          <MetricCard label="Not evaluable" value={summary.arithmetic_not_evaluable} tone="notEvaluable" icon="?" />
          <MetricCard
            label="Probable duplicates"
            value={summary.exact_duplicates + summary.probable_duplicates}
            tone="warning"
            icon="⧉"
          />
        </div>
      </div>

      <section className={styles.section}>
        <h2>Completeness by canonical field</h2>
        <CompletenessChart fields={summary.field_completeness} />
      </section>

      {bySheet.length > 0 && (
        <section className={styles.section}>
          <h2>Missing mandatory fields, by sheet</h2>
          <ul className={styles.bySheetList}>
            {bySheet.map(([name, count]) => (
              <li key={name}>
                <span>{name}</span>
                <span className="tabular-nums">{count}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
