import Link from "next/link";
import styles from "./MarketingNav.module.css";

const SECTION_LINKS = [
  { href: "#problem", label: "The problem" },
  { href: "#how-it-works", label: "How it works" },
  { href: "#ai-triage", label: "AI triage" },
  { href: "#savings", label: "Savings" },
  { href: "#trust", label: "Trust" },
];

export function MarketingNav() {
  return (
    <header className={styles.nav}>
      <div className={styles.inner}>
        <Link href="/" className={styles.logo}>Truebind</Link>
        <ul className={styles.links}>
          {SECTION_LINKS.map((l) => (
            <li key={l.href}><a href={l.href}>{l.label}</a></li>
          ))}
        </ul>
        <div className={styles.actions}>
          <Link href="/upload" className="mkt-btn mkt-btn-primary">Launch the app</Link>
        </div>
      </div>
    </header>
  );
}
