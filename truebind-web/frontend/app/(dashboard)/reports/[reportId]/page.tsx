"use client";

import { use, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ReportSummary } from "@/lib/types";
import { CoverageBanner } from "@/components/report/CoverageBanner";
import { GradeCard } from "@/components/report/GradeCard";
import { CompletenessChart } from "@/components/report/CompletenessChart";
import { MetricCard } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import styles from "./page.module.css";

export default function ReportDetailPage({ params }: { params: Promise<{ reportId: string }> }) {
  const { reportId } = use(params);
  const [summary, setSummary] = useState<ReportSummary | null>(null);

  useEffect(() => {
    api.getReportSummary(reportId).then(setSummary);
  }, [reportId]);

  if (!summary) return <p>Loading…</p>;
  const { report } = summary;
  const cappedByCoverage = summary.sheets_processed !== summary.sheets_total || report.rows_processed !== report.rows_total;

  const bySheet = Object.entries(summary.missing_mandatory_by_sheet).sort((a, b) => b[1] - a[1]);

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1>{report.file_name}</h1>
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
        rowsAssessed={report.rows_processed}
        rowsTotal={report.rows_total}
        sheetsProcessed={summary.sheets_processed}
        sheetsTotal={summary.sheets_total}
      />

      <div className={styles.topRow}>
        <GradeCard grade={report.grade} score={report.score} cappedByCoverage={cappedByCoverage} />
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
