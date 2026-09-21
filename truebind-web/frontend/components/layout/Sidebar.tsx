"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import styles from "./Sidebar.module.css";

const LINKS = [
  { href: "/upload", label: "Upload" },
  { href: "/reports", label: "Reports" },
  { href: "/exceptions", label: "Exceptions" },
  { href: "/duplicates", label: "Duplicates" },
  { href: "/audit", label: "Audit" },
  { href: "/todo", label: "To-do" },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <nav className={styles.sidebar} aria-label="Main navigation">
      <Link href="/upload" className={styles.logo}>Truebind</Link>
      <ul className={styles.links}>
        {LINKS.map((link) => {
          const isActive = pathname === link.href || pathname.startsWith(`${link.href}/`);
          return (
            <li key={link.href}>
              <Link href={link.href} className={`${styles.link} ${isActive ? styles.active : ""}`}>
                {link.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
