"use client";

import { useState } from "react";
import { Reveal } from "./Reveal";
import { AiTriageVisual, MappingVisual, ReportVisual, UploadVisual, ValidationVisual } from "./StepVisuals";
import styles from "./HowItWorksStepper.module.css";

const STEPS = [
  { title: "Upload", desc: "Drop a single sheet or a whole multi-sheet workbook.", Visual: UploadVisual },
  { title: "Automatic field mapping", desc: "Matched against known aliases, with manual override always available.", Visual: MappingVisual },
  { title: "Validation", desc: "Required fields, arithmetic reconciliation, date logic, currency and duplicates.", Visual: ValidationVisual },
  { title: "AI-assisted exception triage", desc: "Prioritises and explains what validation already found.", Visual: AiTriageVisual },
  { title: "Audited report", desc: "Coverage, grade, and a full mapping audit trail.", Visual: ReportVisual },
];

export function HowItWorksStepper() {
  const [active, setActive] = useState(0);
  const ActiveVisual = STEPS[active].Visual;

  return (
    <section id="how-it-works" className={`${styles.section} mkt-section`}>
      <div className="mkt-container">
        <Reveal className={styles.header}>
          <span className="mkt-eyebrow">How it works</span>
          <h2 className={styles.heading}>From raw file to audited report.</h2>
        </Reveal>

        <Reveal>
          <div className={styles.layout}>
            <ul className={styles.stepList} role="tablist" aria-label="How Truebind works" aria-orientation="vertical">
              {STEPS.map((step, i) => (
                <li key={step.title}>
                  <button
                    type="button"
                    role="tab"
                    id={`step-tab-${i}`}
                    aria-selected={active === i}
                    aria-controls="step-panel"
                    className={styles.stepButton}
                    onClick={() => setActive(i)}
                  >
                    <span className={styles.stepNumber} aria-hidden="true">{i + 1}</span>
                    <span>
                      <div className={styles.stepTitle}>{step.title}</div>
                      <div className={styles.stepDesc}>{step.desc}</div>
                    </span>
                  </button>
                </li>
              ))}
            </ul>

            <div
              className={styles.visualPane}
              id="step-panel"
              role="tabpanel"
              aria-labelledby={`step-tab-${active}`}
              tabIndex={0}
            >
              <ActiveVisual />
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
