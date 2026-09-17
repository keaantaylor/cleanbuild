import styles from "./Alert.module.css";

type Tone = "success" | "warning" | "error" | "info";

export function AlertBanner({ tone, title, children }: { tone: Tone; title: string; children?: React.ReactNode }) {
  return (
    <div className={`${styles.alert} ${styles[tone]}`} role="alert">
      <div className={styles.title}>{title}</div>
      {children && <div className={styles.body}>{children}</div>}
    </div>
  );
}
