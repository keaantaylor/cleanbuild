import styles from "./Badge.module.css";

export type BadgeTone = "success" | "warning" | "error" | "info" | "notEvaluable" | "neutral"
  | "leakagePossible" | "leakageProbable" | "leakageCertain" | "sanctions";

export function Badge({ tone, children, symbol }: { tone: BadgeTone; children: React.ReactNode; symbol?: string }) {
  return (
    <span className={`${styles.badge} ${styles[tone]}`}>
      {symbol && <span aria-hidden="true">{symbol}</span>}
      {children}
    </span>
  );
}
