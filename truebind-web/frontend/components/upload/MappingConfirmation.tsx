"use client";

import { useState } from "react";
import type { MappingField } from "@/lib/types";
import { MappingStateBadge } from "@/components/ui/statusBadges";
import { Button } from "@/components/ui/Button";
import styles from "./MappingConfirmation.module.css";

export function MappingConfirmation({
  sheetName, headerRowIndex, fields, headers, onConfirm, saving,
}: {
  sheetName: string;
  headerRowIndex: number | null;
  fields: MappingField[];
  headers: string[];
  onConfirm: (choices: Record<string, string | null>) => void;
  saving: boolean;
}) {
  const [choices, setChoices] = useState<Record<string, string | null>>(
    () => Object.fromEntries(fields.map((f) => [f.field_code, f.source_column])),
  );

  return (
    <div className={styles.wrapper}>
      <div className={styles.header}>
        <h3>{sheetName}</h3>
        <span className={styles.headerRow}>
          Header row detected at row {(headerRowIndex ?? 0) + 1}
        </span>
      </div>

      <table className={styles.table}>
        <thead>
          <tr>
            <th>Canonical field</th>
            <th>Source column</th>
            <th>State</th>
            <th>Sample values</th>
          </tr>
        </thead>
        <tbody>
          {fields.map((f) => (
            <tr key={f.field_code}>
              <td>
                <div className={styles.fieldName}>{f.field_name}</div>
                <div className={styles.fieldCode}>{f.field_code}</div>
              </td>
              <td>
                <select
                  className={styles.select}
                  value={choices[f.field_code] ?? ""}
                  onChange={(e) =>
                    setChoices((prev) => ({ ...prev, [f.field_code]: e.target.value || null }))
                  }
                >
                  <option value="">— not mapped —</option>
                  {headers.map((h) => (
                    <option key={h} value={h}>{h}</option>
                  ))}
                </select>
              </td>
              <td><MappingStateBadge state={f.mapping_state} /></td>
              <td className={styles.samples}>{f.sample_values.join(", ") || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className={styles.footer}>
        <Button onClick={() => onConfirm(choices)} disabled={saving}>
          {saving ? "Confirming…" : "Confirm & continue"}
        </Button>
      </div>
    </div>
  );
}
