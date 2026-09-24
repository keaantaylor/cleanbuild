"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";
import { useMe } from "@/components/auth/AuthGate";
import { Icon } from "@/components/ds/Icon";
import { useToast } from "@/components/ds/overlays";
import { api } from "@/lib/api";
import { NAV_GROUPS } from "./nav";
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
    <span className={`${styles.service} ${busy ? styles.busy : styles.up}`}
          title={`${system.workers_alive} worker(s) online (${system.worker_modes.join(", ")})`}>
      <span className={styles.dot} />{busy ? `Processing · ${busy} job${busy === 1 ? "" : "s"}` : "Processing online"}
    </span>
  );
}

/** Tell the user when background work settles, wherever they are. Driven by
 * the shell's real job counts -- no toast without a real transition. */
function useCompletionToasts() {
  const { system } = useShell();
  const toast = useToast();
  const prev = useRef<number | null>(null);
  useEffect(() => {
    if (!system) return;
    const busy = system.running + system.queued;
    if (prev.current !== null && prev.current > 0 && busy === 0) {
      toast({ tone: "good", title: "Processing finished", body: "Every queued file has been handled.",
              action: { label: "Open inbox", href: "/inbox" } });
    }
    prev.current = busy;
  }, [system, toast]);
}

function signOut() {
  // Full navigation on sign-out so no signed-in state survives in memory.
  // eslint-disable-next-line @next/next/no-location-assign-relative-destination
  api.logout().finally(() => window.location.assign("/login"));
}

export function TopNav() {
  const me = useMe();
  const pathname = usePathname();
  const { unreadAlerts } = useShell();
  useCompletionToasts();
  const group = NAV_GROUPS.find((g) => g.items.some((i) => pathname === i.href || pathname.startsWith(`${i.href}/`)));
  const item = group?.items.find((i) => pathname === i.href || pathname.startsWith(`${i.href}/`));
  return (
    <header className={styles.topbar}>
      <div className={styles.left}>
        {group && item && (
          <span className={styles.where}><span className={styles.whereGroup}>{group.label}</span>
            <Icon name="chevronRight" size={12} /><span className={styles.whereItem}>{item.label}</span></span>
        )}
        <ServiceStatus />
      </div>
      <div className={styles.right}>
        <button type="button" className={styles.cmd} onClick={() => window.dispatchEvent(new Event("tb:command"))}
                aria-label="Open command palette">
          <Icon name="search" size={15} /><span className={styles.cmdText}>Search</span><kbd>⌘K</kbd>
        </button>
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
            <button type="button" className={styles.iconBtn} aria-label="Sign out" title="Sign out" onClick={signOut}>
              <Icon name="logout" size={17} />
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
