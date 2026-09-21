"use client";

import { useState } from "react";
import { Reveal } from "./Reveal";
import styles from "./AiShowcase.module.css";

const WALL = [
  { value: "1,203", label: "rows assessed" },
  { value: "41", label: "missing mandatory field" },
  { value: "18", label: "arithmetic mismatch" },
  { value: "76", label: "not evaluable" },
  { value: "12", label: "mapping completeness" },
  { value: "27", label: "probable duplicate" },
];

const ACTIONS = [
  {
    title: "Review the Blackrock sheet's column mapping",
    rationale: "68 of the 76 not-evaluable rows and all 12 mapping-completeness findings are on this one sheet.",
  },
  {
    title: "Confirm the 18 arithmetic mismatches with the cedant",
    rationale: "These are on well-mapped sheets — paid + reserve genuinely doesn't tie out to incurred.",
  },
  {
    title: "Clear the 4 exact-reference duplicates first",
    rationale: "Same claim reference appearing twice is the highest-confidence finding in this file.",
  },
];

export function AiShowcase() {
  const [shown, setShown] = useState(false);

  return (
    <section id="ai-triage" className={`${styles.section} mkt-section`}>
      <div className="mkt-container">
        <Reveal className={styles.header}>
          <span className="mkt-eyebrow">AI-assisted triage</span>
          <h2 className={styles.heading}>From a wall of numbers to a starting point.</h2>
          <p className={styles.disclaimer}>
            This is a fixed, illustrative example — not a live demo. In the app, the AI
            never sees raw claim data or does its own maths: it explains and prioritises
            exceptions that the deterministic validation engine already found, citing only
            the figures that engine already computed.
          </p>
        </Reveal>

        <Reveal>
          <div className={styles.stage}>
            <div className={styles.wall}>
              {WALL.map((w) => (
                <div key={w.label} className={styles.wallItem}>
                  <div className={styles.wallValue}>{w.value}</div>
                  <div className={styles.wallLabel}>{w.label}</div>
                </div>
              ))}
            </div>
            <p className={styles.wallCaption}>Raw counts — no indication of what matters most.</p>

            <div className={styles.toggleRow} style={{ marginTop: "var(--spacing-6)" }}>
              <button type="button" className="mkt-btn mkt-btn-primary" onClick={() => setShown((s) => !s)}>
                {shown ? "Hide AI summary" : "Generate AI summary →"}
              </button>
            </div>

            <div className={`${styles.after} ${shown ? styles.shown : ""}`}>
              <div className={styles.afterHeader}>
                <span className={styles.badge}>✨ AI-generated summary</span>
              </div>
              <p className={styles.summary}>
                1,203 rows were assessed across 4 sheets. Most of the volume traces back to one
                sheet&rsquo;s column mapping rather than the underlying claims data — fixing
                that first will resolve the majority of flagged rows. Separately, 18 rows on
                well-mapped sheets have a genuine arithmetic mismatch worth raising with the
                cedant, and 4 claim references appear twice.
              </p>

              <div className={styles.actions}>
                {ACTIONS.map((a, i) => (
                  <div key={a.title} className={styles.actionCard}>
                    <div>
                      <span className={styles.actionRank}>{i + 1}</span>
                      <span className={styles.actionTitle}>{a.title}</span>
                    </div>
                    <p className={styles.actionRationale}>{a.rationale}</p>
                  </div>
                ))}
              </div>

              <div className={styles.splitRow}>
                <div className={`${styles.splitCard} ${styles.ingestion}`}>
                  <div className={styles.splitValue}>53 rows</div>
                  <div className={styles.splitLabel}>Likely ingestion — fix in the tool</div>
                </div>
                <div className={`${styles.splitCard} ${styles.dataQuality}`}>
                  <div className={styles.splitValue}>49 rows</div>
                  <div className={styles.splitLabel}>Likely genuine — query the cedant</div>
                </div>
              </div>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
