import { Tooltip } from "./Tooltip";
import styles from "./Card.module.css";

export function Card({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={[styles.card, className].filter(Boolean).join(" ")}>{children}</div>;
}

export function MetricCard({
  label, value, tone, icon, explain,
}: {
  label: string; value: string | number;
  tone?: "success" | "warning" | "error" | "notEvaluable" | "neutral"; icon?: string;
  /** Plain-language: what this counts, how it's calculated, why it matters. */
  explain?: string;
}) {
  return (
    <div className={[styles.metric, tone ? styles[`metric-${tone}`] : ""].filter(Boolean).join(" ")}>
      <div className={styles.metricLabel}>
        {icon && <span className={styles.metricIcon} aria-hidden="true">{icon}</span>}
        {explain ? <Tooltip text={explain}>{label}</Tooltip> : label}
      </div>
      <div className={`${styles.metricValue} tabular-nums`}>{value}</div>
    </div>
  );
}
