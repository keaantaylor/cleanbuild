"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon, type IconName } from "@/components/ds/Icon";
import { useShell } from "./ShellContext";
import styles from "./Sidebar.module.css";

type Item = { href: string; label: string; icon: IconName; badge?: "work" | "alerts" };
const GROUPS: { label: string; items: Item[] }[] = [
  { label: "Operate", items: [
    { href: "/overview", label: "Overview", icon: "overview" },
    { href: "/inbox", label: "Inbox", icon: "inbox" },
    { href: "/upload", label: "Intake", icon: "upload" },
    { href: "/todo", label: "Work queue", icon: "todo", badge: "work" },
  ] },
  { label: "Analyse", items: [
    { href: "/reports", label: "Reports", icon: "reports" },
    { href: "/exceptions", label: "Exceptions", icon: "exceptions" },
    { href: "/duplicates", label: "Duplicates", icon: "duplicates" },
  ] },
  { label: "Deliver", items: [
    { href: "/exports", label: "Exports", icon: "exports" },
    { href: "/automations", label: "Automations", icon: "automations" },
  ] },
  { label: "Govern", items: [
    { href: "/alerts", label: "Alerts", icon: "bell", badge: "alerts" },
    { href: "/audit", label: "Audit trail", icon: "audit" },
  ] },
];

export function Sidebar() {
  const pathname = usePathname();
  const { workItems, unreadAlerts } = useShell();
  return (
    <nav className={styles.rail} aria-label="Main navigation">
      <Link href="/overview" className={styles.brand}>
        <span className={styles.mark} aria-hidden="true">TB</span>
        <span>TrueBind</span>
      </Link>
      <div className={styles.groups}>
        {GROUPS.map((g) => (
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
                      {count > 0 && <span className={styles.badge} aria-label={`${count} pending`}>{count > 99 ? "99+" : count}</span>}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>
    </nav>
  );
}
