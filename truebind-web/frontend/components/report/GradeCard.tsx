import { Tooltip } from "@/components/ui/Tooltip";
import styles from "./GradeCard.module.css";

const GRADE_CLASS: Record<string, string> = { "5": "g5", "4": "g4", "3": "g3", "2": "g2", "1": "g1" };
const GRADE_LABEL: Record<string, string> = {
  "5": "Excellent", "4": "Good", "3": "Fair", "2": "Poor", "1": "Very poor",
};
const GRADE_BAND_TEXT: Record<string, string> = {
  "5": "composite score 90–100",
  "4": "composite score 75–89",
  "3": "composite score 55–74",
  "2": "composite score 35–54",
  "1": "composite score below 35",
};

const SCORE_EXPLANATION = "Composite score = average field completeness % − (1.0 × % of rows with at "
  + "least one exception) − (0.5 × % of rows flagged as a possible duplicate), clipped to 0–100. "
  + "Only fields that were mapped somewhere in the file count toward completeness — a field nobody's "
  + "sheet ever had a column for is excluded from the average, not scored as 0%. Bands: 5 Excellent "
  + "(90–100) · 4 Good (75–89) · 3 Fair (55–74) · 2 Poor (35–54) · 1 Very poor (below 35).";

export function GradeCard({ grade, score, cappedByCoverage }: { grade: string | null; score: number | null; cappedByCoverage: boolean }) {
  const cls = grade ? GRADE_CLASS[grade] : "g3";
  return (
    <div className={`${styles.card} ${styles[cls ?? "g3"]}`}>
      <div className={styles.grade}>{grade ?? "—"} / 5</div>
      <div className={styles.label}>
        <Tooltip text={SCORE_EXPLANATION}>
          {grade ? `${GRADE_LABEL[grade]} (${GRADE_BAND_TEXT[grade]})` : "Not yet graded"}
        </Tooltip>
      </div>
      {score !== null && <div className={styles.score}>Composite score {score.toFixed(0)}/100</div>}
      {cappedByCoverage && <div className={styles.caveat}>Score not fully reliable — coverage was incomplete.</div>}
    </div>
  );
}
