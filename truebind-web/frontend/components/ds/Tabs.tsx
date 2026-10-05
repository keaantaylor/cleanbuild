"use client";

import { useRef } from "react";
import s from "./Tabs.module.css";

export interface TabItem {
  id: string;
  label: React.ReactNode;
  count?: number;
}

/** WAI-ARIA tabs with roving focus: ←/→, Home and End move between tabs.
 * Render panels with tabPanelProps(id) so each is labelled by its tab. */
export function Tabs({
  items,
  value,
  onChange,
  label,
  variant = "line",
  idBase = "tab",
}: {
  items: TabItem[];
  value: string;
  onChange: (id: string) => void;
  label: string;
  variant?: "line" | "segmented";
  idBase?: string;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const move = (i: number) => {
    const n = (i + items.length) % items.length;
    refs.current[n]?.focus();
    onChange(items[n].id);
  };
  const current = items.findIndex((t) => t.id === value);
  return (
    <div role="tablist" aria-label={label} className={variant === "segmented" ? s.segmented : s.list}>
      {items.map((t, i) => (
        <button
          key={t.id}
          ref={(el) => {
            refs.current[i] = el;
          }}
          type="button"
          role="tab"
          id={`${idBase}-${t.id}`}
          aria-selected={t.id === value}
          aria-controls={`${idBase}-panel-${t.id}`}
          tabIndex={t.id === value ? 0 : -1}
          className={s.tab}
          onClick={() => onChange(t.id)}
          onKeyDown={(e) => {
            if (e.key === "ArrowRight") move(current + 1);
            else if (e.key === "ArrowLeft") move(current - 1);
            else if (e.key === "Home") move(0);
            else if (e.key === "End") move(items.length - 1);
            else return;
            e.preventDefault();
          }}
        >
          {t.label}
          {t.count !== undefined && <span className={s.count}>{t.count.toLocaleString("en-GB")}</span>}
        </button>
      ))}
    </div>
  );
}

export function tabPanelProps(id: string, idBase = "tab") {
  return { role: "tabpanel" as const, id: `${idBase}-panel-${id}`, "aria-labelledby": `${idBase}-${id}`, tabIndex: 0 };
}
