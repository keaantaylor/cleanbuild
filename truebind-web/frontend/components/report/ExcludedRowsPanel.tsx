"use client";

import { useState } from "react";
import type { ExcludedRow } from "@/lib/types";
import styles from "./ExcludedRowsPanel.module.css";

const REASON_LABEL: Record<string, string> = {
  blank: "Blank row",
  blank_run: "Run of blank rows",
  subtotal: "Subtotal/total row",
  repeated_header: "Repeated header row",
  title: "Title / label row",
};

export function ExcludedRowsPanel({ rows }: { rows: ExcludedRow[] }) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const bySheet = new Map<string, ExcludedRow[]>();
  for (const r of rows) {
    const list = bySheet.get(r.sheet_name) ?? [];
    list.push(r);
    bySheet.set(r.sheet_name, list);
  }

  return (
    <div className={styles.wrapper}>
      {Array.from(bySheet.entries()).map(([sheetName, sheetRows]) => (
        <div key={sheetName} className={styles.sheetGroup}>
          <div className={styles.sheetName}>{sheetName}</div>
          <ul className={styles.list}>
            {sheetRows.map((r) => {
              const isOpen = expandedId === r.id;
              return (
                <li key={r.id}>
                  <button
                    className={styles.rowButton}
                    onClick={() => setExpandedId(isOpen ? null : r.id)}
                    aria-expanded={isOpen}
                  >
                    <span className={styles.rowNumber}>Row {r.row_number}</span>
                    <span className={styles.reason}>{REASON_LABEL[r.reason] ?? r.reason}</span>
                    <span className={styles.chevron} aria-hidden="true">{isOpen ? "−" : "+"}</span>
                  </button>
                  {isOpen && (
                    <div className={styles.detail}>
                      <p className={styles.detailText}>{r.detail}</p>
                      <dl className={styles.values}>
                        {Object.entries(r.values).map(([col, val]) => (
                          <div key={col} className={styles.valueRow}>
                            <dt>{col}</dt>
                            <dd>{val || "—"}</dd>
                          </div>
                        ))}
                      </dl>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </div>
  );
}
