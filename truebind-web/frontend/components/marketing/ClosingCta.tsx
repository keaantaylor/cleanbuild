import Link from "next/link";
import { Reveal } from "./Reveal";
import styles from "./ClosingCta.module.css";

export function ClosingCta() {
  return (
    <section className={`${styles.section} mkt-section`}>
      <div className="mkt-container">
        <Reveal>
          <div className={styles.card}>
            <h2 className={styles.heading}>See it on your own file.</h2>
            <p className={styles.body}>
              Upload a real bordereau and walk through mapping, validation and the audited
              report yourself — no setup required.
            </p>
            <div className={styles.ctas}>
              <Link href="/overview" className="mkt-btn mkt-btn-primary">Launch the app</Link>
              <a href="#how-it-works" className="mkt-btn mkt-btn-secondary">Revisit how it works</a>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
