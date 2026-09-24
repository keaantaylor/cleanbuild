"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon } from "@/components/ds/Icon";
import { BrandMark } from "./BrandMark";
import { NAV_GROUPS } from "./nav";
import { useShell } from "./ShellContext";
import styles from "./Sidebar.module.css";

export function Sidebar() {
  const pathname = usePathname();
  const { workItems, unreadAlerts, system } = useShell();
  const busy = system ? system.running + system.queued : 0;
  return (
    <nav className={styles.rail} aria-label="Main navigation">
      <Link href="/overview" className={styles.brand}>
        <BrandMark />
        <span>TrueBind</span>
      </Link>
      <button type="button" className={styles.search} onClick={() => window.dispatchEvent(new Event("tb:command"))}>
        <Icon name="search" size={15} /><span>Search or jump to…</span><kbd>⌘K</kbd>
      </button>
      <div className={styles.groups}>
        {NAV_GROUPS.map((g) => (
          <div key={g.label} className={styles.group}>
            <p className={styles.groupLabel}>{g.label}</p>
            <ul className={styles.links}>
              {g.items.map((item) => {
                const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
                const count = item.badge === "work" ? workItems : item.badge === "alerts" ? unreadAlerts : 0;
                return (
                  <li key={item.href}>
                    <Link href={item.href} className={`${styles.link} ${active ? styles.active : ""}`}
                          aria-current={active ? "page" : undefined}>
                      <Icon name={item.icon} size={17} />
                      <span className={styles.linkLabel}>{item.label}</span>
                      {item.href === "/upload" && busy > 0 && <span className={styles.live} aria-label={`${busy} processing`} />}
                      {count > 0 && <span className={styles.badge} aria-label={`${count} pending`}>{count > 99 ? "99+" : count}</span>}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>
      <div className={styles.foot}>
        <span className={`${styles.engine} ${system?.worker_available ? styles.engineUp : system ? styles.engineDown : ""}`}>
          <span className={styles.engineDot} />
          {!system ? "Checking engine…" : system.worker_available
            ? busy ? `Engine · ${busy} in flight` : "Engine online"
            : "Engine offline"}
        </span>
      </div>
    </nav>
  );
}
