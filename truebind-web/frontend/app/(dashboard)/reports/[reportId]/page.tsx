"use client";

import { use, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { ExcludedRow, Report, ReportSummary } from "@/lib/types";
import { CoverageBanner } from "@/components/report/CoverageBanner";
import { GradeCard } from "@/components/report/GradeCard";
import { CompletenessChart } from "@/components/report/CompletenessChart";
import { MetricCard } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { AlertBanner } from "@/components/ui/Alert";
import { ExcludedRowsPanel } from "@/components/report/ExcludedRowsPanel";
import styles from "./page.module.css";

const POLL_INTERVAL_MS = 1500;

export default function ReportDetailPage({ params }: { params: Promise<{ reportId: string }> }) {
  const { reportId } = use(params);
  const [report, setReport] = useState<Report | null>(null);
  const [summary, setSummary] = useState<ReportSummary | null>(null);
  const [excludedRows, setExcludedRows] = useState<ExcludedRow[]>([]);
  const [pollError, setPollError] = useState<string | null>(null);

  // Section 6: /process now runs on a background thread and returns
  // before the pipeline has actually finished, so this page has to poll
  // for completion instead of assuming a COMPLETE report is already
  // sitting there the moment it mounts -- fetching the summary of a
  // report that's still PROCESSING would silently render a misleadingly
  // "clean" all-zero health report instead of showing that it isn't
  // ready yet. A poll request that fails (a network blip, the backend
  // briefly unreachable) must surface too, rather than leaving this page
  // stuck on "Processing…" forever with nothing to say why it stopped
  // updating -- Section 7's silent-failure standard applied to the
  // frontend, not just the pipeline.
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    // Tracks the last known status across retries -- a local variable, not
    // the `report` state, since this closure is created once per reportId
    // and would otherwise always see the stale value from the render that
    // started it.
    let lastKnownStatus: string | null = null;

    async function poll() {
      try {
        const r = await api.getReport(reportId);
        if (cancelled) return;
        lastKnownStatus = r.status;
        setReport(r);
        setPollError(null);
        if (r.status === "PROCESSING") {
          timer = setTimeout(poll, POLL_INTERVAL_MS);
          return;
        }
        if (r.status === "COMPLETE") {
          const [s, excluded] = await Promise.all([api.getReportSummary(reportId), api.listExcludedRows(reportId)]);
          if (!cancelled) {
            setSummary(s);
            setExcludedRows(excluded);
          }
        }
      } catch (e) {
        if (cancelled) return;
        setPollError(e instanceof ApiError ? e.message : "Could not reach the server.");
        // Keep retrying on a transient failure rather than stopping outright --
        // once a report is known to exist, only a COMPLETE/FAILED terminal
        // status (handled above) should ever stop this loop.
        if (lastKnownStatus === null || lastKnownStatus === "PROCESSING") {
          timer = setTimeout(poll, POLL_INTERVAL_MS);
        }
      }
    }
    poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [reportId]);

  if (pollError && !report) {
    return (
      <div className={styles.page}>
        <AlertBanner tone="error" title="Could not load this report">{pollError}</AlertBanner>
      </div>
    );
  }

  if (!report) return <p>Loading…</p>;

  if (report.status === "PROCESSING") {
    return (
      <div className={styles.page}>
        <AlertBanner tone="info" title="Processing your file…">
          This can take a little while for a large workbook. This page will update automatically —
          no need to refresh.
        </AlertBanner>
        {pollError && (
          <AlertBanner tone="warning" title="Having trouble checking status">
            {pollError} Still retrying automatically.
          </AlertBanner>
        )}
      </div>
    );
  }

  if (report.status === "FAILED") {
    return (
      <div className={styles.page}>
        <AlertBanner tone="error" title="Processing failed">
          {report.processing_error || "An unexpected error occurred while processing this report."}
        </AlertBanner>
      </div>
    );
  }

  if (!summary) return <p>Loading…</p>;
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

      {summary.unmapped_sheets.length > 0 && (
        <section className={styles.section}>
          <h2>Sheets requiring mapping</h2>
          <p className={styles.sectionIntro}>
            These sheets&rsquo; rows were received and are counted above — none were dropped — but no
            column could be automatically matched to a canonical field. Open the sheet on the mapping
            screen to map it manually.
          </p>
          <ul className={styles.bySheetList}>
            {summary.unmapped_sheets.map((s) => (
              <li key={s.sheet_name}>
                <span>{s.sheet_name}</span>
                <span>{s.reason}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {summary.non_claim_summary_sheets.length > 0 && (
        <section className={styles.section}>
          <h2>Sheets recognised as summaries, not claims</h2>
          <p className={styles.sectionIntro}>
            These sheets bind only monetary columns with no claim reference (or insured name + date) —
            Truebind recognised them as a dashboard/rollup tab rather than a claims register and excluded
            their rows from every total on this report entirely, rather than risk counting an aggregate
            figure as if it were an individual claim.
          </p>
          <ul className={styles.bySheetList}>
            {summary.non_claim_summary_sheets.map((s) => (
              <li key={s.sheet_name}>
                <span>{s.sheet_name}</span>
                <span>{s.reason}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {summary.skipped_sheets.length > 0 && (
        <section className={styles.section}>
          <h2>Sheets skipped entirely</h2>
          <p className={styles.sectionIntro}>
            These sheets contributed zero rows to this report — never silently: each is named here
            with the reason it could not be processed.
          </p>
          <ul className={styles.bySheetList}>
            {summary.skipped_sheets.map((s) => (
              <li key={s.sheet_name}>
                <span>{s.sheet_name}</span>
                <span>{s.reason}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className={styles.section}>
        <h2>Row-count reconciliation</h2>
        {!summary.reconciliation.reconciles && (
          <p className={styles.sectionIntro} style={{ color: "var(--color-error)", fontWeight: 600 }}>
            Mismatch found — the numbers below do not add up as expected. This needs investigation.
          </p>
        )}
        <ul className={styles.bySheetList}>
          <li><span>Source worksheets</span><span className="tabular-nums">{summary.reconciliation.source_worksheets}</span></li>
          <li><span>Source data rows</span><span className="tabular-nums">{summary.reconciliation.source_data_rows}</span></li>
          <li><span>Mapped rows</span><span className="tabular-nums">{summary.reconciliation.mapped_rows}</span></li>
          <li><span>Unmapped rows</span><span className="tabular-nums">{summary.reconciliation.unmapped_rows}</span></li>
          <li><span>Duplicate rows</span><span className="tabular-nums">{summary.reconciliation.duplicate_rows}</span></li>
          <li><span>Rejected rows</span><span className="tabular-nums">{summary.reconciliation.rejected_rows}</span></li>
          <li><span>Exported rows</span><span className="tabular-nums">{summary.reconciliation.exported_rows}</span></li>
          <li><span>Rows requiring review</span><span className="tabular-nums">{summary.reconciliation.rows_requiring_review}</span></li>
          {summary.reconciliation.non_claim_summary_rows > 0 && (
            <li><span>Excluded as summary/aggregate rows</span><span className="tabular-nums">{summary.reconciliation.non_claim_summary_rows}</span></li>
          )}
        </ul>
      </section>

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
