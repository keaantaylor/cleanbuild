import type { FieldCompleteness } from "@/lib/types";
import { Tooltip } from "@/components/ui/Tooltip";
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
              <Tooltip text="No column on any sheet in this file was ever mapped to this field — Truebind will not infer it, so it's excluded from the average completeness score rather than counted as 0%.">
                <span className={styles.name}>{f.field_name}</span>
              </Tooltip>
              <span className={styles.notFound}>column not found</span>
            </div>
          );
        }
        const pct = f.denominator ? (100 * f.present) / f.denominator : 0;
        const tone = toneFor(pct);
        return (
          <div key={f.field_code} className={styles.row}>
            <Tooltip text={`Populated on ${f.present} of ${f.denominator} row(s) where this field was mapped to a column. Rows on a sheet that never mapped this field aren't counted in that denominator, so they can't drag this percentage down.`}>
              <span className={styles.name}>{f.field_name}</span>
            </Tooltip>
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
