import { Reveal } from "./Reveal";
import styles from "./ProblemSection.module.css";

const CARDS = [
  {
    icon: "🗂️",
    title: "Every cedant, a different layout",
    body: "“Paid”, “Amount Paid to Date (GBP)”, “Montant payé” — the same field, a dozen header conventions, and no shared template across submissions.",
  },
  {
    icon: "💱",
    title: "Currencies mixed in one file",
    body: "Values arrive as €12,400.00, £8,750, or 1.234,56 in the same column — different symbols, different thousands-separator conventions, sometimes on adjacent rows.",
  },
  {
    icon: "🧩",
    title: "Excel artifacts, not clean data",
    body: "Live formulas that only resolve inside the original workbook, merged title banners sitting above the real header row, blank “ghost” columns from deleted fields — every export carries its own noise.",
  },
  {
    icon: "⚠️",
    title: "Real money, manual review",
    body: "Thousands of rows, mandatory fields quietly missing, numbers that don’t reconcile, the same claim entered twice under two references — and one analyst checking it by eye.",
  },
];

export function ProblemSection() {
  return (
    <section id="problem" className={`${styles.section} mkt-section`}>
      <div className="mkt-container">
        <Reveal className={styles.header}>
          <span className="mkt-eyebrow">The problem</span>
          <h2 className={styles.heading}>Bordereaux don&rsquo;t arrive clean.</h2>
        </Reveal>

        <div className={styles.grid}>
          {CARDS.map((c, i) => (
            <Reveal key={c.title} delayMs={i * 80}>
              <div className={styles.card}>
                <span className={styles.cardIcon} aria-hidden="true">{c.icon}</span>
                <div className={styles.cardTitle}>{c.title}</div>
                <p className={styles.cardBody}>{c.body}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
