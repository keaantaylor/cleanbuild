"use client";

import { useId, useState } from "react";
import { Reveal } from "./Reveal";
import { useCountUp } from "@/lib/useCountUp";
import styles from "./SavingsCalculator.module.css";

function formatHours(n: number): string {
  return new Intl.NumberFormat("en-GB", { maximumFractionDigits: 0 }).format(n);
}

function formatMoney(n: number): string {
  return new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP", maximumFractionDigits: 0 }).format(n);
}

export function SavingsCalculator() {
  const [bordereauxPerMonth, setBordereauxPerMonth] = useState(20);
  const [hoursPerBordereau, setHoursPerBordereau] = useState(4);
  const [hourlyCost, setHourlyCost] = useState(45);
  const [reductionPct, setReductionPct] = useState(50);

  const monthlyHoursRaw = bordereauxPerMonth * hoursPerBordereau;
  const monthlyHoursSaved = monthlyHoursRaw * (reductionPct / 100);
  const monthlyCostSaved = monthlyHoursSaved * hourlyCost;
  const annualHoursSaved = monthlyHoursSaved * 12;
  const annualCostSaved = monthlyCostSaved * 12;

  const animatedMonthlyHours = useCountUp(monthlyHoursSaved);
  const animatedMonthlyCost = useCountUp(monthlyCostSaved);
  const animatedAnnualHours = useCountUp(annualHoursSaved);
  const animatedAnnualCost = useCountUp(annualCostSaved);

  const idBordereaux = useId();
  const idHours = useId();
  const idCost = useId();
  const idReduction = useId();

  return (
    <section id="savings" className={`${styles.section} mkt-section`}>
      <div className="mkt-container">
        <Reveal className={styles.header}>
          <span className="mkt-eyebrow">Savings estimator</span>
          <h2 className={styles.heading}>What could first-pass automation be worth to you?</h2>
        </Reveal>

        <Reveal>
          <div className={styles.card}>
            <div className={styles.inputs}>
              <div className={styles.field}>
                <div className={styles.fieldLabelRow}>
                  <label htmlFor={idBordereaux}>Bordereaux processed per month</label>
                  <span className={styles.fieldValue}>{bordereauxPerMonth}</span>
                </div>
                <input
                  id={idBordereaux} type="range" min={1} max={200} step={1} className={styles.slider}
                  value={bordereauxPerMonth} onChange={(e) => setBordereauxPerMonth(Number(e.target.value))}
                />
              </div>

              <div className={styles.field}>
                <div className={styles.fieldLabelRow}>
                  <label htmlFor={idHours}>Analyst hours per bordereau, today</label>
                  <span className={styles.fieldValue}>{hoursPerBordereau} h</span>
                </div>
                <input
                  id={idHours} type="range" min={0.5} max={20} step={0.5} className={styles.slider}
                  value={hoursPerBordereau} onChange={(e) => setHoursPerBordereau(Number(e.target.value))}
                />
              </div>

              <div className={styles.field}>
                <div className={styles.fieldLabelRow}>
                  <label htmlFor={idCost}>Loaded hourly cost</label>
                  <span className={styles.fieldValue}>{formatMoney(hourlyCost)}</span>
                </div>
                <input
                  id={idCost} type="range" min={15} max={150} step={5} className={styles.slider}
                  value={hourlyCost} onChange={(e) => setHourlyCost(Number(e.target.value))}
                />
              </div>

              <div className={styles.field}>
                <div className={styles.fieldLabelRow}>
                  <label htmlFor={idReduction}>Assumed first-pass time reduction</label>
                  <span className={styles.fieldValue}>{reductionPct}%</span>
                </div>
                <input
                  id={idReduction} type="range" min={40} max={60} step={1} className={styles.slider}
                  value={reductionPct} onChange={(e) => setReductionPct(Number(e.target.value))}
                />
                <span className={styles.fieldHint}>
                  A human still reviews every flagged exception — this reflects faster first-pass
                  triage, not a fully automated review.
                </span>
              </div>
            </div>

            <div className={styles.results}>
              <div className={styles.resultGroup}>
                <span className={styles.resultLabel}>Estimated monthly savings</span>
                <span className={styles.resultValue}>{formatHours(animatedMonthlyHours)} hours</span>
                <span className={styles.resultSub}>{formatMoney(animatedMonthlyCost)}</span>
              </div>
              <div className={styles.resultGroup}>
                <span className={styles.resultLabel}>Estimated annual savings</span>
                <span className={styles.resultValue}>{formatHours(animatedAnnualHours)} hours</span>
                <span className={styles.resultSub}>{formatMoney(animatedAnnualCost)}</span>
              </div>

              <details className={styles.details}>
                <summary className={styles.detailsSummary}>How this is calculated</summary>
                <div className={styles.calcBody}>
                  <p>
                    This is an estimate based on the numbers you entered above, not a measured
                    result from real customers — Truebind doesn&rsquo;t have usage data to
                    support a specific savings claim yet.
                  </p>
                  <div className={styles.calcFormula}>
{`monthly hours saved = bordereaux/month × hours/bordereau × reduction %
                     = ${bordereauxPerMonth} × ${hoursPerBordereau} × ${reductionPct}%
                     = ${formatHours(monthlyHoursSaved)} hours

monthly cost saved   = monthly hours saved × hourly cost
                     = ${formatHours(monthlyHoursSaved)} × ${formatMoney(hourlyCost)}
                     = ${formatMoney(monthlyCostSaved)}

annual = monthly × 12`}
                  </div>
                </div>
              </details>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
