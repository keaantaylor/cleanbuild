import { Reveal } from "./Reveal";
import styles from "./HeroVisual.module.css";

const BEFORE_ROWS: { cells: string[]; problem?: number }[] = [
  { cells: ["Claim Ref", "Montant payé", "Reserve", "Incurred"] },
  { cells: ["CLM-0091", "€12,400.00", "3200", "15600"] },
  { cells: ["CLM-0092", "", "1800", "1800"], problem: 1 },
  { cells: ["CLM-0093", "8,750", "0", "9750"], problem: 3 },
  { cells: ["CLM-0091", "12400", "3200", "15600"], problem: 0 },
];

export function HeroVisual() {
  return (
    <Reveal className={styles.wrap}>
      <div className={styles.panel} aria-hidden="true">
        <div className={styles.panelHeader}>
          <span className={styles.dot} /> cedant_bordereau_q3.xlsx
        </div>
        <div className={styles.grid}>
          {BEFORE_ROWS.map((row, ri) =>
            row.cells.map((cell, ci) => (
              <div
                key={`${ri}-${ci}`}
                className={[
                  styles.cell,
                  ri === 0 ? styles.head : "",
                  row.problem === ci ? styles.problem : "",
                  ri === 1 && ci === 1 ? styles.foreign : "",
                ].join(" ")}
              >
                {cell || "—"}
              </div>
            )),
          )}
        </div>
      </div>

      <div className={styles.connector}>
        <span className={styles.connectorLine} />
        <span aria-hidden="true">→</span>
      </div>

      <div className={styles.panel} aria-hidden="true">
        <div className={styles.panelHeader}>
          <span className={styles.dot} /> Health report
        </div>
        <div className={styles.after}>
          <div className={styles.gradeRow}>
            <span className={styles.gradeValue}>4/5</span>
            <span className={styles.gradeLabel}>Good — 3 rows need review</span>
          </div>
          <div className={styles.statLine}><span>Rows assessed</span><strong>1,203 / 1,203</strong></div>
          <div className={styles.statLine}><span>Missing mandatory field</span><strong>1 row</strong></div>
          <div className={styles.statLine}><span>Arithmetic not evaluable</span><strong>1 row</strong></div>
          <div className={styles.statLine}><span>Exact duplicate</span><strong>1 pair</strong></div>
        </div>
      </div>
    </Reveal>
  );
}
