import Link from "next/link";
import { HeroVisual } from "./HeroVisual";
import styles from "./Hero.module.css";

export function Hero() {
  return (
    <section className={`${styles.hero} mkt-container`}>
      <div className={styles.grid}>
        <div className={styles.copy}>
          <span className="mkt-eyebrow">Bordereau processing</span>
          <h1 className={styles.headline}>
            Every cedant&rsquo;s spreadsheet, one audited exception report.
          </h1>
          <p className={styles.subheadline}>
            Truebind ingests real-world bordereaux — multi-sheet, multi-currency Excel
            submissions with inconsistent headers and formatting from every cedant — maps
            each column automatically, reconciles the numbers, and flags exactly what needs
            a human: missing fields, arithmetic that doesn&rsquo;t tie out, and claims that
            look like duplicates. No more checking thousands of rows by hand.
          </p>
          <div className={styles.ctas}>
            <Link href="/overview" className="mkt-btn mkt-btn-primary">Launch the app</Link>
            <a href="#how-it-works" className={styles.secondaryCta}>
              See how it works <span aria-hidden="true">↓</span>
            </a>
          </div>
        </div>

        <div className={styles.visualRow}>
          <HeroVisual />
        </div>
      </div>
    </section>
  );
}
