"use client";

import styles from "./TopNav.module.css";

export function TopNav({ reportName, timestamp }: { reportName?: string; timestamp?: string }) {
  return (
    <header className={styles.topnav}>
      <div>
        {reportName && <span className={styles.reportName}>{reportName}</span>}
        {timestamp && <span className={styles.timestamp}>{timestamp}</span>}
      </div>
      <div className={styles.user}>web_user</div>
    </header>
  );
}
