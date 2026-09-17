"use client";

import { use, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ExcludedRow, ReportSummary } from "@/lib/types";
import { CoverageBanner } from "@/components/report/CoverageBanner";
import { GradeCard } from "@/components/report/GradeCard";
import { CompletenessChart } from "@/components/report/CompletenessChart";
import { MetricCard } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { ExcludedRowsPanel } from "@/components/report/ExcludedRowsPanel";
import styles from "./page.module.css";

export default function ReportDetailPage({ params }: { params: Promise<{ reportId: string }> }) {
  const { reportId } = use(params);
  const [summary, setSummary] = useState<ReportSummary | null>(null);
  const [excludedRows, setExcludedRows] = useState<ExcludedRow[]>([]);

  useEffect(() => {
    api.getReportSummary(reportId).then(setSummary);
    api.listExcludedRows(reportId).then(setExcludedRows);
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
          <MetricCard
            label="Missing mandatory" value={summary.missing_mandatory_rows} tone="error" icon="⚠"
            explain="Rows missing claim reference and/or insured name — the only two fields Truebind treats as unconditionally required. Click through to Exceptions to see exactly which rows and which field."
          />
          <MetricCard
            label="Arithmetic mismatches" value={summary.arithmetic_mismatches} tone="warning" icon="≠"
            explain="Rows where indemnity paid + indemnity reserve does not equal total incurred, beyond a small rounding tolerance. This is real data disagreement, not a coverage gap."
          />
          <MetricCard
            label="Not evaluable" value={summary.arithmetic_not_evaluable} tone="notEvaluable" icon="?"
            explain="Rows where the paid+reserve=incurred check could not be run at all, because one of those fields was never mapped on that sheet or is blank/unparseable on that row. Never shown as a pass — Truebind refuses to guess. See Exceptions → Not evaluable for the row-by-row reasons."
          />
          <MetricCard
            label="Probable duplicates"
            value={summary.exact_duplicates + summary.probable_duplicates}
            tone="warning"
            icon="⧉"
            explain="Rows whose claim reference is identical (certain) or whose insured name and loss date are close enough to plausibly be the same claim reported twice (probable). Truebind never merges these automatically — review each pair on the Duplicates screen."
          />
        </div>
      </div>

      <section className={styles.section}>
        <h2>Completeness by canonical field</h2>
        <CompletenessChart fields={summary.field_completeness} />
      </section>

      {Object.keys(summary.not_evaluable_by_reason).length > 0 && (
        <section className={styles.section}>
          <h2>Why rows are not evaluable</h2>
          <ul className={styles.bySheetList}>
            {Object.entries(summary.not_evaluable_by_reason).map(([reason, count]) => (
              <li key={reason}>
                <span>{NOT_EVALUABLE_REASON_LABEL[reason] ?? reason}</span>
                <span className="tabular-nums">{count}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

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

      {excludedRows.length > 0 && (
        <section className={styles.section}>
          <h2>Rows excluded before assessment</h2>
          <p className={styles.sectionIntro}>
            These rows were never counted as claims and never flagged as exceptions — Truebind
            recognized them as blank lines, subtotal/total lines, or a repeated header row, and
            removed them before mapping or validation ever saw them.
          </p>
          <ExcludedRowsPanel rows={excludedRows} />
        </section>
      )}
    </div>
  );
}

const NOT_EVALUABLE_REASON_LABEL: Record<string, string> = {
  incurred_unmapped: "Total incurred was never mapped on that sheet",
  paid_and_reserve_unmapped: "Both paid and reserve were never mapped on that sheet",
  incurred_blank: "Total incurred is blank or unparseable on that row",
  paid_and_reserve_blank: "Both paid and reserve are blank or unparseable on that row",
};
