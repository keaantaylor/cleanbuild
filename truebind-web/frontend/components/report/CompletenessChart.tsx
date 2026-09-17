import type { FieldCompleteness } from "@/lib/types";
import styles from "./CompletenessChart.module.css";

function toneFor(pct: number): string {
  if (pct >= 90) return "success";
  if (pct >= 60) return "warning";
  return "error";
}

export function CompletenessChart({ fields }: { fields: FieldCompleteness[] }) {
  return (
    <div className={styles.list}>
      {fields.map((f) => {
        if (f.never_mapped) {
          return (
            <div key={f.field_code} className={styles.row}>
              <span className={styles.name}>{f.field_name}</span>
              <span className={styles.notFound}>column not found</span>
            </div>
          );
        }
        const pct = f.denominator ? (100 * f.present) / f.denominator : 0;
        const tone = toneFor(pct);
        return (
          <div key={f.field_code} className={styles.row}>
            <span className={styles.name}>{f.field_name}</span>
            <div className={styles.track}>
              <div className={`${styles.fill} ${styles[tone]}`} style={{ width: `${pct}%` }} />
            </div>
            <span className={`${styles.pct} tabular-nums`}>{pct.toFixed(0)}%</span>
          </div>
        );
      })}
    </div>
  );
}
