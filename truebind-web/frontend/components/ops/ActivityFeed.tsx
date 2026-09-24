"use client";

import Link from "next/link";
import { describeAudit } from "@/lib/audit";
import { timeAgo, formatDateTime } from "@/lib/formatters";
import type { AuditLogEntry } from "@/lib/types";
import { Icon } from "@/components/ds";
import styles from "./ops.module.css";

export function ActivityFeed({ entries, showReportLinks = true, compact }: {
  entries: AuditLogEntry[]; showReportLinks?: boolean; compact?: boolean;
}) {
  if (!entries.length) return <p className={styles.muted}>No activity yet.</p>;
  return (
    <ol className={`${styles.feed} ${compact ? styles.compact : ""}`}>
      {entries.map((e) => {
        const d = describeAudit(e);
        return (
          <li key={e.id} className={styles.feedItem}>
            <span className={`${styles.feedIcon} ${styles[`t-${d.tone}`]}`}><Icon name={d.icon} size={14} /></span>
            <div className={styles.feedBody}>
              <p className={styles.feedTitle}>{d.title}</p>
              {d.detail && <p className={styles.feedDetail}>{d.detail}</p>}
              <p className={styles.feedMeta}>
                <time dateTime={e.created_at} title={formatDateTime(e.created_at)}>{timeAgo(e.created_at)}</time>
                {" · "}{e.actor}
                {showReportLinks && e.report_id && <> · <Link href={`/reports/${e.report_id}`}>report</Link></>}
                {e.seq !== undefined && <span className={styles.seq}> #{e.seq}</span>}
              </p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
