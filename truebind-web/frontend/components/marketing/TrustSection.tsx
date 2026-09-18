import { Reveal } from "./Reveal";
import styles from "./TrustSection.module.css";

const POINTS = [
  {
    icon: "📝",
    title: "Every mapping decision is logged",
    body: "Alias match, AI-suggested, or a human override — each one recorded with who confirmed it and when, not just the final result.",
  },
  {
    icon: "🔎",
    title: "Every exception is traceable",
    body: "Down to the specific sheet, row and rule that flagged it — never a bare count with no way back to the source.",
  },
  {
    icon: "🚫",
    title: "Nothing is silently dropped or altered",
    body: "A sheet Truebind can’t confidently map is never dropped — it’s flagged for review and still counted in the coverage total.",
  },
  {
    icon: "🤝",
    title: "Duplicates are never auto-merged",
    body: "A probable duplicate is routed to a reviewer, who marks it not a duplicate, flagged for the sender, or confirmed — the underlying rows are always left untouched.",
  },
];

const LOG_LINES = [
  { when: "14:02:11", who: "web_user", action: "MAPPING_CONFIRMED", where: "Blackrock · CR0126CM" },
  { when: "14:02:44", who: "web_user", action: "MAPPING_OVERRIDDEN", where: "Crawford · CR0110CM" },
  { when: "14:05:09", who: "ai_triage_summariser", action: "AI_SUMMARY_GENERATED", where: "report 8a2f19d…" },
  { when: "14:07:52", who: "web_user", action: "EXCEPTION_STATUS_CHANGED", where: "duplicate · flagged_for_sender" },
];

export function TrustSection() {
  return (
    <section id="trust" className={`${styles.section} mkt-section`}>
      <div className="mkt-container">
        <Reveal className={styles.header}>
          <span className={`mkt-eyebrow ${styles.eyebrow}`}>Trust &amp; auditability</span>
          <h2 className={styles.heading}>Built for reviewers who have to defend the number.</h2>
          <p className={styles.lede}>
            Insurance and reinsurance buyers care about this more than almost anything else in
            the tool. So it&rsquo;s not a footnote — it&rsquo;s the design principle behind
            every screen.
          </p>
        </Reveal>

        <div className={styles.layout}>
          <Reveal className={styles.points}>
            {POINTS.map((p) => (
              <div key={p.title} className={styles.point}>
                <span className={styles.pointIcon} aria-hidden="true">{p.icon}</span>
                <div>
                  <div className={styles.pointTitle}>{p.title}</div>
                  <div className={styles.pointBody}>{p.body}</div>
                </div>
              </div>
            ))}
          </Reveal>

          <Reveal delayMs={120} className={styles.logPanel}>
            <div className={styles.logHeader}>Audit log excerpt</div>
            {LOG_LINES.map((l, i) => (
              <div key={i} className={styles.logLine}>
                <span className={styles.logWhen}>{l.when}</span>
                <span><span className={styles.logAction}>{l.action}</span> — {l.who}</span>
                <span className={styles.logWhen}>{l.where}</span>
              </div>
            ))}
          </Reveal>
        </div>
      </div>
    </section>
  );
}
