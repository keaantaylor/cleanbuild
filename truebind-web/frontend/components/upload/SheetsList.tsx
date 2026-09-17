import type { Sheet } from "@/lib/types";
import styles from "./SheetsList.module.css";

export function SheetsList({ sheets, activeSheet, onSelect }: {
  sheets: Sheet[]; activeSheet: string | null; onSelect: (sheetName: string) => void;
}) {
  return (
    <ul className={styles.list}>
      {sheets.map((sheet) => (
        <li key={sheet.id}>
          <button
            className={`${styles.item} ${sheet.sheet_name === activeSheet ? styles.active : ""}`}
            onClick={() => onSelect(sheet.sheet_name)}
            disabled={sheet.status === "SKIPPED"}
          >
            <span className={styles.name}>{sheet.sheet_name}</span>
            {sheet.status === "SKIPPED" && <span className={styles.skipped} title={sheet.skip_reason ?? undefined}>skipped</span>}
            {sheet.status === "CONFIRMED" && <span className={styles.confirmed} aria-hidden="true">✓</span>}
            {sheet.status === "PENDING_CONFIRMATION" && <span className={styles.pending} aria-hidden="true">●</span>}
          </button>
        </li>
      ))}
    </ul>
  );
}
