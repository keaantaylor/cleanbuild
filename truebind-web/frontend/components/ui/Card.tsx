import styles from "./Card.module.css";

export function Card({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={[styles.card, className].filter(Boolean).join(" ")}>{children}</div>;
}

export function MetricCard({
  label, value, tone, icon,
}: { label: string; value: string | number; tone?: "success" | "warning" | "error" | "notEvaluable" | "neutral"; icon?: string }) {
  return (
    <div className={[styles.card, styles.metric, tone ? styles[`metric-${tone}`] : ""].filter(Boolean).join(" ")}>
      {icon && <div className={styles.metricIcon} aria-hidden="true">{icon}</div>}
      <div className={`${styles.metricValue} tabular-nums`}>{value}</div>
      <div className={styles.metricLabel}>{label}</div>
    </div>
  );
}
