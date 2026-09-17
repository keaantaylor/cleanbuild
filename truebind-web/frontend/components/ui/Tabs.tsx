"use client";

import styles from "./Tabs.module.css";

export function Tabs({ options, active, onChange }: { options: { value: string; label: string; count?: number }[]; active: string; onChange: (value: string) => void }) {
  return (
    <div className={styles.tabs} role="tablist">
      {options.map((opt) => (
        <button
          key={opt.value}
          role="tab"
          aria-selected={opt.value === active}
          className={`${styles.tab} ${opt.value === active ? styles.active : ""}`}
          onClick={() => onChange(opt.value)}
        >
          {opt.label}
          {opt.count !== undefined && <span className={styles.count}>{opt.count}</span>}
        </button>
      ))}
    </div>
  );
}
