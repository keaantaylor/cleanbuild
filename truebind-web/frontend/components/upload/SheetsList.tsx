import type { Sheet } from "@/lib/types";
import styles from "./SheetsList.module.css";

function summaryFor(sheet: Sheet): string {
  if (sheet.status === "SKIPPED") {
    return `${sheet.row_count} rows · skipped · ${sheet.skip_reason ?? "no header"}`;
  }
  const headerLine = (sheet.header_row_index ?? 0) + 1;
  const base = `${sheet.row_count} rows · header line ${headerLine}`;
  if (sheet.mapping_status === "unmapped") {
    return `${base} · 0/${sheet.fields_total} fields mapped · requires mapping`;
  }
  if (sheet.mapping_status === "partial") {
    return `${base} · ${sheet.fields_mapped}/${sheet.fields_total} fields mapped`;
  }
  if (sheet.mapping_status === "non_claim_summary") {
    return `${base} · summary/aggregate sheet, not claims · excluded from totals`;
  }
  return sheet.status === "CONFIRMED" ? `${base} · mapped` : base;
}

function markFor(sheet: Sheet): { className: string; glyph: string } {
  if (sheet.status === "SKIPPED") return { className: styles.markSkipped, glyph: "—" };
  if (sheet.mapping_status === "unmapped") return { className: styles.markUnmapped, glyph: "!" };
  if (sheet.mapping_status === "partial") return { className: styles.markPartial, glyph: "!" };
  if (sheet.mapping_status === "non_claim_summary") return { className: styles.markExcluded, glyph: "Σ" };
  if (sheet.status === "CONFIRMED") return { className: styles.markConfirmed, glyph: "✓" };
  return { className: styles.markPending, glyph: "●" };
}

export function SheetsList({ sheets, activeSheet, onSelect }: {
  sheets: Sheet[]; activeSheet: string | null; onSelect: (sheetName: string) => void;
}) {
  return (
    <ul className={styles.list}>
      {sheets.map((sheet) => {
        const mark = markFor(sheet);
        return (
          <li key={sheet.id}>
            <button
              className={`${styles.item} ${sheet.sheet_name === activeSheet ? styles.active : ""}`}
              onClick={() => onSelect(sheet.sheet_name)}
              disabled={sheet.status === "SKIPPED"}
            >
              <span className={mark.className} aria-hidden="true">{mark.glyph}</span>
              <span className={styles.body}>
                <span className={styles.name}>{sheet.sheet_name}</span>
                <span className={styles.meta}>{summaryFor(sheet)}</span>
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
