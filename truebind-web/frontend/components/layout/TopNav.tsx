"use client";

import Link from "next/link";
import { useMe } from "@/components/auth/AuthGate";
import { Icon } from "@/components/ds/Icon";
import { api } from "@/lib/api";
import { useShell } from "./ShellContext";
import styles from "./TopNav.module.css";

function ServiceStatus() {
  const { system } = useShell();
  if (!system) return <span className={styles.service}><span className={styles.dot} />Checking processing…</span>;
  const busy = system.running + system.queued;
  if (!system.worker_available) {
    return (
      <span className={`${styles.service} ${styles.down}`} title="No processing worker has checked in recently">
        <span className={styles.dot} />Processing service unavailable
      </span>
    );
  }
  return (
    <span className={`${styles.service} ${styles.up}`}
          title={`${system.workers_alive} worker(s) online (${system.worker_modes.join(", ")})`}>
      <span className={styles.dot} />{busy ? `Processing · ${busy} job${busy === 1 ? "" : "s"}` : "Processing online"}
    </span>
  );
}

function signOut() {
  // Full navigation on sign-out so no signed-in state survives in memory.
  // eslint-disable-next-line @next/next/no-location-assign-relative-destination
  api.logout().finally(() => window.location.assign("/login"));
}

export function TopNav() {
  const me = useMe();
  const { unreadAlerts } = useShell();
  return (
    <header className={styles.topbar}>
      <ServiceStatus />
      <div className={styles.right}>
        <Link href="/upload" className={styles.cta}><Icon name="upload" size={15} />New intake</Link>
        <Link href="/alerts" className={styles.iconBtn} aria-label={`Alerts, ${unreadAlerts} unread`}>
          <Icon name="bell" size={18} />
          {unreadAlerts > 0 && <span className={styles.count}>{unreadAlerts > 99 ? "99+" : unreadAlerts}</span>}
        </Link>
        {me && (
          <div className={styles.user}>
            <span className={styles.avatar} aria-hidden="true">{me.user.display_name.slice(0, 1).toUpperCase()}</span>
            <span className={styles.who}>
              <span className={styles.name}>{me.user.display_name}</span>
              <span className={styles.org}>{me.tenant.name} · {me.role.toLowerCase()}</span>
            </span>
            <button type="button" className={styles.iconBtn} aria-label="Sign out" onClick={signOut}>
              <Icon name="logout" size={17} />
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
