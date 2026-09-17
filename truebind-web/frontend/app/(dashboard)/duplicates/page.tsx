"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { DuplicatePair, DuplicateReviewStatus } from "@/lib/types";
import { ReportPicker } from "@/components/report/ReportPicker";
import { SideBySideComparison } from "@/components/duplicates/SideBySideComparison";
import styles from "./page.module.css";

export default function DuplicatesPage() {
  const [reportId, setReportId] = useState<string | null>(null);
  const [pairs, setPairs] = useState<DuplicatePair[]>([]);
  const [index, setIndex] = useState(0);

  useEffect(() => {
    if (!reportId) return;
    api.listDuplicates(reportId).then((list) => {
      setPairs(list);
      setIndex(0);
    });
  }, [reportId]);

  async function handleReview(status: DuplicateReviewStatus) {
    if (!reportId) return;
    const pair = pairs[index];
    const updated = await api.reviewDuplicate(reportId, pair.validation_result_id, status);
    setPairs((prev) => prev.map((p, i) => (i === index ? updated : p)));
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1>Duplicates</h1>
        <ReportPicker value={reportId} onChange={setReportId} />
      </div>

      {reportId && pairs.length === 0 && <p>No probable duplicates found in this report.</p>}

      {reportId && pairs.length > 0 && (
        <div className={styles.layout}>
          <ul className={styles.list}>
            {pairs.map((p, i) => (
              <li key={p.validation_result_id}>
                <button
                  className={i === index ? styles.activeItem : styles.item}
                  onClick={() => setIndex(i)}
                >
                  {String(p.row_a.claim_reference ?? "—")} ↔ {String(p.row_b.claim_reference ?? "—")}
                  {p.review_status && <span className={styles.reviewedMark}>✓</span>}
                </button>
              </li>
            ))}
          </ul>
          <div className={styles.comparison}>
            <SideBySideComparison pair={pairs[index]} index={index} total={pairs.length} onReview={handleReview} />
          </div>
        </div>
      )}
    </div>
  );
}
