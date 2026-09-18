"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { ExceptionSummary, NarrativeStatus } from "@/lib/types";
import { formatCurrency, formatDateTime, formatNumber, formatPct } from "@/lib/formatters";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import styles from "./AiTriagePanel.module.css";

const POLL_INTERVAL_MS = 2000;

const CATEGORY_LABEL: Record<string, string> = {
  ingestion: "Ingestion / mapping",
  data_quality: "Data quality",
  duplicate: "Duplicate",
  other: "Other",
};

export function AiTriagePanel({
  reportId, onFilterAction,
}: {
  reportId: string;
  onFilterAction: (filter: { checkType?: string | null; sheetName?: string | null }) => void;
}) {
  const [summary, setSummary] = useState<ExceptionSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const pollUntilSettled = useCallback((initial: ExceptionSummary) => {
    setSummary(initial);
    if (initial.narrative_status !== "GENERATING") return;

    const tick = async () => {
      try {
        const latest = await api.getExceptionSummary(reportId);
        if (latest) setSummary(latest);
        if (latest && latest.narrative_status === "GENERATING") {
          timerRef.current = setTimeout(tick, POLL_INTERVAL_MS);
        }
      } catch {
        // Transient poll failure -- try again on the next tick rather than
        // surfacing a hard error for what's likely a blip.
        timerRef.current = setTimeout(tick, POLL_INTERVAL_MS);
      }
    };
    timerRef.current = setTimeout(tick, POLL_INTERVAL_MS);
  }, [reportId]);

  const generate = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const created = await api.generateExceptionSummary(reportId);
      pollUntilSettled(created);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not generate the AI summary.");
    } finally {
      setLoading(false);
    }
  }, [reportId, pollUntilSettled]);

  useEffect(() => {
    let cancelled = false;
    setSummary(null);
    setError(null);
    setLoading(true);

    (async () => {
      try {
        const existing = await api.getExceptionSummary(reportId);
        if (cancelled) return;
        if (existing) {
          pollUntilSettled(existing);
          setLoading(false);
        } else {
          // First time this report's exceptions have been viewed --
          // populate the panel automatically rather than making the
          // reviewer click a button for what they'll almost always want.
          await generate();
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof ApiError ? e.message : "Could not load the AI summary.");
          setLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
      if (timerRef.current) clearTimeout(timerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reportId]);

  const aggregate = summary?.aggregate;
  const narrative = summary?.narrative;
  const status: NarrativeStatus | null = summary?.narrative_status ?? null;
  const isGenerating = loading || status === "GENERATING";

  return (
    <section className={styles.panel} aria-labelledby="ai-triage-heading">
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <Badge tone="info" symbol="✨">AI-generated summary</Badge>
          <h2 id="ai-triage-heading" className={styles.heading}>Exception triage</h2>
        </div>
        <div className={styles.headerRight}>
          {summary?.completed_at && status !== "GENERATING" && (
            <span className={styles.meta}>Generated {formatDateTime(summary.completed_at)}</span>
          )}
          <Button variant="secondary" onClick={generate} disabled={isGenerating}>
            {isGenerating ? "Generating…" : "Regenerate"}
          </Button>
        </div>
      </div>

      {error && <div className={styles.errorBanner}>{error}</div>}

      {isGenerating && (
        <div className={styles.loadingRow} role="status" aria-live="polite">
          <span className={styles.spinner} aria-hidden="true" />
          Generating an AI summary of these exceptions — the report itself is already complete;
          this narrative is populating separately and won&rsquo;t block anything.
        </div>
      )}

      {!isGenerating && aggregate && (
        <>
          <div className={styles.statStrip}>
            <div className={styles.stat}>
              <span className={styles.statValue}>{formatNumber(aggregate.total_exceptions)}</span>
              <span className={styles.statLabel}>total exceptions</span>
            </div>
            <div className={styles.stat}>
              <span className={styles.statValue}>{formatCurrency(aggregate.total_value_at_stake)}</span>
              <span className={styles.statLabel}>value at stake</span>
            </div>
            <div className={styles.stat}>
              <span className={styles.statValue}>
                {formatPct(aggregate.root_cause_split.ingestion.pct_of_total_exceptions)}
              </span>
              <span className={styles.statLabel}>likely ingestion issues</span>
            </div>
            <div className={styles.stat}>
              <span className={styles.statValue}>
                {formatPct(aggregate.root_cause_split.data_quality.pct_of_total_exceptions)}
              </span>
              <span className={styles.statLabel}>likely data issues</span>
            </div>
          </div>

          {status === "UNAVAILABLE" && (
            <p className={styles.degradedNote}>
              AI narrative unavailable (no ANTHROPIC_API_KEY configured for this deployment) — the
              hard numbers above are still the deterministic output of the validation engine and are
              unaffected.
            </p>
          )}
          {status === "FAILED" && (
            <p className={styles.degradedNote}>
              The AI narrative failed to generate{summary?.narrative_error ? `: ${summary.narrative_error}` : "."} The
              hard numbers above are unaffected. Try regenerating.
            </p>
          )}

          {status === "COMPLETE" && narrative && (
            <div className={styles.narrative}>
              {summary?.narrative_warning && (
                <div className={styles.warningBanner} role="alert">
                  ⚠ {summary.narrative_warning}
                </div>
              )}

              <p className={styles.executiveSummary}>{narrative.executive_summary}</p>

              <div className={styles.actions}>
                {narrative.actions.map((action, i) => (
                  <button
                    key={i}
                    type="button"
                    className={styles.actionCard}
                    onClick={() => onFilterAction({ checkType: action.filter_check_type, sheetName: action.filter_sheet_name })}
                  >
                    <div className={styles.actionHeader}>
                      <span className={styles.actionRank}>{i + 1}</span>
                      <span className={styles.actionTitle}>{action.title}</span>
                      <Badge tone={action.category === "ingestion" ? "info" : action.category === "duplicate" ? "leakageProbable" : "warning"}>
                        {CATEGORY_LABEL[action.category] ?? action.category}
                      </Badge>
                    </div>
                    <p className={styles.actionRationale}>{action.rationale}</p>
                  </button>
                ))}
              </div>

              <div className={styles.issueColumns}>
                <div className={styles.issueColumn}>
                  <h3>Fix in the tool (ingestion / mapping)</h3>
                  {narrative.ingestion_issues.length === 0 ? (
                    <p className={styles.emptyIssue}>No likely ingestion issues identified.</p>
                  ) : (
                    <ul>{narrative.ingestion_issues.map((s, i) => <li key={i}>{s}</li>)}</ul>
                  )}
                </div>
                <div className={styles.issueColumn}>
                  <h3>Query with the cedant (data quality)</h3>
                  {narrative.data_issues.length === 0 ? (
                    <p className={styles.emptyIssue}>No likely genuine data issues identified.</p>
                  ) : (
                    <ul>{narrative.data_issues.map((s, i) => <li key={i}>{s}</li>)}</ul>
                  )}
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
