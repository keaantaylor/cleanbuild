"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import styles from "./Sidebar.module.css";

const LINKS = [
  { href: "/upload", label: "Upload", icon: "📤" },
  { href: "/reports", label: "Reports", icon: "📊" },
  { href: "/exceptions", label: "Exceptions", icon: "⚠️" },
  { href: "/duplicates", label: "Duplicates", icon: "🔁" },
  { href: "/audit", label: "Audit", icon: "🛡️" },
  { href: "/todo", label: "To-do", icon: "✅" },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <nav className={styles.sidebar} aria-label="Main navigation">
      <div className={styles.logo}>Truebind</div>
      <ul className={styles.links}>
        {LINKS.map((link) => {
          const isActive = pathname === link.href || pathname.startsWith(`${link.href}/`);
          return (
            <li key={link.href}>
              <Link href={link.href} className={`${styles.link} ${isActive ? styles.active : ""}`}>
                <span aria-hidden="true">{link.icon}</span>
                {link.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
