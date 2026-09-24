"use client";

import Link from "next/link";
import type { Recommendation } from "@/lib/types";
import { Pill, severityTone } from "@/components/ds";
import styles from "./ops.module.css";

const TARGET_HREF: Record<string, (id: string) => string> = {
  MANDATORY_FIELD: (id) => `/exceptions?reportId=${id}&checkType=MANDATORY_FIELD`,
  ARITHMETIC: (id) => `/exceptions?reportId=${id}&checkType=ARITHMETIC`,
  DUPLICATE: (id) => `/duplicates?reportId=${id}`,
  MAPPING: (id) => `/reports/${id}?tab=sheets`,
};

export function Recommendations({ items, reportId, showFile }: {
  items: Recommendation[]; reportId?: string; showFile?: boolean;
}) {
  if (!items.length) return <p className={styles.muted}>No actions recommended — nothing in the evidence needs attention.</p>;
  return (
    <ul className={styles.recList}>
      {items.map((r) => {
        const rid = r.report_id ?? reportId;
        const href = r.target && rid ? TARGET_HREF[r.target]?.(rid) : undefined;
        return (
          <li key={`${rid}-${r.id}`} className={styles.rec}>
            <p className={styles.recTitle}>
              <Pill tone={severityTone(r.severity)}>{r.severity.toLowerCase()}</Pill>
              {r.title}
            </p>
            {href && <Link href={href} className={styles.sub}>Review →</Link>}
            <p className={styles.recEvidence}><strong>Evidence:</strong> {r.evidence}</p>
            <p className={styles.recAction}><strong>Next:</strong> {r.action}
              {showFile && r.file_name && <span className={styles.sub}> · {r.file_name}</span>}</p>
          </li>
        );
      })}
    </ul>
  );
}
