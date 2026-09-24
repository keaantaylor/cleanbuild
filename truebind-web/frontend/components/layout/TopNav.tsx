"use client";

import { useMe } from "@/components/auth/AuthGate";
import { api } from "@/lib/api";
import styles from "./TopNav.module.css";

export function TopNav({ reportName, timestamp }: { reportName?: string; timestamp?: string }) {
  const me = useMe();
  return (
    <header className={styles.topnav}>
      <div>
        {reportName && <span className={styles.reportName}>{reportName}</span>}
        {timestamp && <span className={styles.timestamp}>{timestamp}</span>}
      </div>
      <div className={styles.user}>
        {me ? `${me.user.display_name} · ${me.tenant.name}` : ""}{" "}
        <button type="button" onClick={() => api.logout().finally(() => { window.location.href = "/login"; })}
          style={{ marginLeft: 12, background: "none", border: 0, color: "inherit", textDecoration: "underline", cursor: "pointer" }}>
          Sign out
        </button>
      </div>
    </header>
  );
}
