import Link from "next/link";
import styles from "./MarketingFooter.module.css";

export function MarketingFooter() {
  return (
    <footer className={styles.footer}>
      <div className={styles.inner}>
        <div>
          <div className={styles.brand}>Truebind</div>
          <div className={styles.tagline}>Bordereau ingestion, validation and audit.</div>
        </div>
        <ul className={styles.links}>
          <li><a href="#how-it-works">How it works</a></li>
          <li><a href="#trust">Trust &amp; auditability</a></li>
          <li><Link href="/overview">Launch the app</Link></li>
        </ul>
      </div>
    </footer>
  );
}
