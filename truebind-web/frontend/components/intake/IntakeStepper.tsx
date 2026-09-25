import type { Report } from "@/lib/types";
import { Icon } from "@/components/ds/Icon";
import styles from "./intake.module.css";

const STEPS = ["Upload", "File checks", "Read workbook", "Map columns", "Confirm", "Validate", "Report"];

/** Where a file is in the seven-step intake, derived from its real status
 * and job stage -- the stepper never runs ahead of the backend. */
export function intakeStep(report: Report | null, uploading: boolean): number {
  if (!report) return uploading ? 1 : 0;
  const j = report.job;
  switch (report.status) {
    case "UPLOADED": case "QUEUED":
      return j?.kind === "PROCESS" ? 5 : 1;
    case "INGESTING":
      return j?.stage === "proposing_mapping" || j?.stage === "saving" ? 3 : 2;
    case "WAITING_FOR_REVIEW": return 4;
    case "PROCESSING": return 5;
    case "COMPLETE": return 6;
    default: return j?.kind === "PROCESS" ? 5 : 2;
  }
}

export function IntakeStepper({ current, failed }: { current: number; failed?: boolean }) {
  return (
    <ol className={styles.stepper} aria-label="Intake progress">
      {STEPS.map((label, i) => {
        const state = i < current || (i === current && current === STEPS.length - 1) ? "done" : i === current ? (failed ? "failed" : "active") : "todo";
        return (
          <li key={label} className={`${styles.step} ${styles[`st-${state}`]}`} aria-current={state === "active" ? "step" : undefined}>
            <span className={styles.stepDot}>{state === "done" ? <Icon name="check" size={12} strokeWidth={3} /> : state === "failed" ? <Icon name="x" size={12} strokeWidth={3} /> : i + 1}</span>
            <span className={styles.stepLabel}>{label}</span>
          </li>
        );
      })}
    </ol>
  );
}
