import styles from "./StepVisuals.module.css";

export function UploadVisual() {
  return (
    <div>
      <div className={styles.dropzone}>Drop a workbook — .xlsx, .xls, or .csv</div>
      <div className={styles.sheetTabs}>
        {["Sedgwick", "Crawford", "Blackrock", "MX Underwriting"].map((name) => (
          <span key={name} className={`${styles.sheetTab} ${styles.read}`}>✓ {name}</span>
        ))}
      </div>
      <p style={{ fontSize: "0.8125rem", color: "var(--mkt-ink-secondary)", marginTop: "1rem" }}>
        Every sheet is read independently — its own header row detected (even with a title
        banner above it), no shared template required across senders.
      </p>
    </div>
  );
}

export function MappingVisual() {
  const rows: { source: string; field: string; pill: "pillAlias" | "pillAi" | "pillManual"; label: string }[] = [
    { source: "Claim Ref", field: "Claim reference", pill: "pillAlias", label: "Alias match" },
    { source: "Amount Paid to Date (GBP)", field: "Indemnity paid", pill: "pillAlias", label: "Alias match" },
    { source: "Réserve", field: "Indemnity reserve", pill: "pillAi", label: "AI-suggested" },
    { source: "Notes internes", field: "— unmapped —", pill: "pillManual", label: "Needs review" },
  ];
  return (
    <div>
      {rows.map((r) => (
        <div key={r.source} className={styles.mappingRow}>
          <span className={styles.mappingSource}>{r.source}</span>
          <span aria-hidden="true">→</span>
          <span className={styles.mappingField}>{r.field}</span>
          <span className={`${styles.pill} ${styles[r.pill]}`}>{r.label}</span>
        </div>
      ))}
      <p style={{ fontSize: "0.8125rem", color: "var(--mkt-ink-secondary)", marginTop: "1rem" }}>
        A reviewer sees and can override every mapping before anything is ingested — nothing
        is committed silently.
      </p>
    </div>
  );
}

export function ValidationVisual() {
  const rows: { icon: "checkPass" | "checkWarn" | "checkFlag"; symbol: string; label: string; note: string }[] = [
    { icon: "checkPass", symbol: "✓", label: "Required fields present", note: "1,202 / 1,203" },
    { icon: "checkWarn", symbol: "?", label: "Arithmetic reconciliation", note: "1 not evaluable" },
    { icon: "checkPass", symbol: "✓", label: "Date logic", note: "no issues" },
    { icon: "checkPass", symbol: "✓", label: "Currency validity (ISO 4217)", note: "no issues" },
    { icon: "checkFlag", symbol: "!", label: "Duplicate scan", note: "1 exact, 2 probable" },
  ];
  return (
    <div>
      {rows.map((r) => (
        <div key={r.label} className={styles.checkRow}>
          <span className={`${styles.checkIcon} ${styles[r.icon]}`} aria-hidden="true">{r.symbol}</span>
          <span className={styles.checkLabel}>{r.label}</span>
          <span className={styles.checkNote}>{r.note}</span>
        </div>
      ))}
      <p style={{ fontSize: "0.8125rem", color: "var(--mkt-ink-secondary)", marginTop: "1rem" }}>
        A row missing an input is marked <strong>not evaluable</strong>, never silently
        treated as zero — a blank cell and a genuine zero are different facts.
      </p>
    </div>
  );
}

export function AiTriageVisual() {
  return (
    <div>
      <div className={styles.triageCard}>
        <div className={styles.triageBadge}>✨ AI-generated summary</div>
        <p className={styles.triageSummary}>
          1,203 rows assessed across 4 sheets. Most exceptions trace to one sheet&rsquo;s
          mapping, not the underlying claims data — start there before reviewing individual
          rows.
        </p>
        <div className={styles.triageAction}>
          <div className={styles.triageActionTitle}>1. Review the Blackrock sheet mapping</div>
          <div style={{ color: "var(--mkt-ink-secondary)" }}>
            It accounts for 68% of missing-field exceptions on this file.
          </div>
        </div>
      </div>
      <p style={{ fontSize: "0.8125rem", color: "var(--mkt-ink-secondary)", marginTop: "1rem" }}>
        The narrative only ever cites numbers the validation engine already computed — it
        explains and prioritises, it never does its own maths on claim values.
      </p>
    </div>
  );
}

export function ReportVisual() {
  const lines = [
    { who: "web_user", what: "confirmed mapping", where: "Blackrock · Indemnity reserve" },
    { who: "ai_triage_summariser", what: "generated summary", where: "report 8a2f…" },
    { who: "web_user", what: "reviewed duplicate", where: "flagged for sender" },
  ];
  return (
    <div>
      <div className={styles.reportGrade}>
        <span className={styles.reportGradeValue}>4 / 5</span>
        <span style={{ color: "var(--mkt-ink-secondary)", fontSize: "0.875rem" }}>Good — coverage 100%</span>
      </div>
      {lines.map((l, i) => (
        <div key={i} className={styles.auditLine}>
          <span><strong>{l.who}</strong> {l.what}</span>
          <span>{l.where}</span>
        </div>
      ))}
      <p style={{ fontSize: "0.8125rem", color: "var(--mkt-ink-secondary)", marginTop: "1rem" }}>
        Every mapping decision and reviewer action is in the audit log — exportable, traceable
        to a specific sheet, row and reason.
      </p>
    </div>
  );
}
