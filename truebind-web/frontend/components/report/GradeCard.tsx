import styles from "./GradeCard.module.css";

const GRADE_CLASS: Record<string, string> = { "5": "g5", "4": "g4", "3": "g3", "2": "g2", "1": "g1" };
const GRADE_LABEL: Record<string, string> = {
  "5": "Excellent", "4": "Good", "3": "Fair", "2": "Poor", "1": "Very poor",
};

export function GradeCard({ grade, score, cappedByCoverage }: { grade: string | null; score: number | null; cappedByCoverage: boolean }) {
  const cls = grade ? GRADE_CLASS[grade] : "g3";
  return (
    <div className={`${styles.card} ${styles[cls ?? "g3"]}`}>
      <div className={styles.grade}>{grade ?? "—"} / 5</div>
      <div className={styles.label}>{grade ? GRADE_LABEL[grade] : "Not yet graded"}</div>
      {score !== null && <div className={styles.score}>Composite score {score.toFixed(0)}/100</div>}
      {cappedByCoverage && <div className={styles.caveat}>Score not fully reliable — coverage was incomplete.</div>}
    </div>
  );
}
