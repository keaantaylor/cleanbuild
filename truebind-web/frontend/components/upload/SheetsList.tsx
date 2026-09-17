import type { Sheet } from "@/lib/types";
import styles from "./SheetsList.module.css";

function summaryFor(sheet: Sheet): string {
  if (sheet.status === "SKIPPED") {
    return `${sheet.row_count} rows · skipped · ${sheet.skip_reason ?? "no header"}`;
  }
  const headerLine = (sheet.header_row_index ?? 0) + 1;
  const base = `${sheet.row_count} rows · header line ${headerLine}`;
  return sheet.status === "CONFIRMED" ? `${base} · mapped` : base;
}

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
            <span
              className={
                sheet.status === "CONFIRMED" ? styles.markConfirmed
                  : sheet.status === "SKIPPED" ? styles.markSkipped
                  : styles.markPending
              }
              aria-hidden="true"
            >
              {sheet.status === "CONFIRMED" ? "✓" : sheet.status === "SKIPPED" ? "—" : "●"}
            </span>
            <span className={styles.body}>
              <span className={styles.name}>{sheet.sheet_name}</span>
              <span className={styles.meta}>{summaryFor(sheet)}</span>
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}
