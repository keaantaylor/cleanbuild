"use client";

import { useState } from "react";
import type { DuplicatePair, DuplicateReviewStatus } from "@/lib/types";
import { DuplicateMatchBadge } from "@/components/ui/statusBadges";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { formatCurrency, formatDate } from "@/lib/formatters";
import styles from "./SideBySideComparison.module.css";

const FIELDS: { key: string; label: string; format: (v: unknown) => string }[] = [
  { key: "claim_reference", label: "Claim reference", format: (v) => String(v ?? "—") },
  { key: "insured_name", label: "Insured name", format: (v) => String(v ?? "—") },
  { key: "date_of_loss", label: "Date of loss", format: (v) => formatDate(v as string) },
  { key: "paid_amount", label: "Paid", format: (v) => formatCurrency(v as number) },
  { key: "reserve_amount", label: "Reserve", format: (v) => formatCurrency(v as number) },
  { key: "incurred_amount", label: "Incurred", format: (v) => formatCurrency(v as number) },
];

function normalize(v: unknown): string {
  return String(v ?? "").trim().toLowerCase().replace(/[^a-z0-9]/g, "");
}

function fieldStatus(a: unknown, b: unknown): "match" | "differs" | "unmapped" {
  if (a === null || a === undefined || b === null || b === undefined) return "unmapped";
  return normalize(a) === normalize(b) ? "match" : "differs";
}

export function SideBySideComparison({
  pair, index, total, onReview,
}: { pair: DuplicatePair; index: number; total: number; onReview: (status: DuplicateReviewStatus) => Promise<void> }) {
  const [saving, setSaving] = useState<DuplicateReviewStatus | null>(null);

  async function handleReview(status: DuplicateReviewStatus) {
    setSaving(status);
    try {
      await onReview(status);
    } finally {
      setSaving(null);
    }
  }

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <span>pair {index + 1} of {total} · 0 merged automatically</span>
        <DuplicateMatchBadge matchType={pair.match_type} />
      </div>
      <p className={styles.detail}>{pair.detail}</p>

      <table className={styles.table}>
        <thead>
          <tr><th>Field</th><th>Row A</th><th>Row B</th><th>Comparison</th></tr>
        </thead>
        <tbody>
          {FIELDS.map((f) => {
            const status = fieldStatus(pair.row_a[f.key], pair.row_b[f.key]);
            return (
              <tr key={f.key}>
                <td>{f.label}</td>
                <td>{f.format(pair.row_a[f.key])}</td>
                <td>{f.format(pair.row_b[f.key])}</td>
                <td>
                  {status === "match" && <Badge tone="success">● matched</Badge>}
                  {status === "differs" && <Badge tone="error">✕ differs</Badge>}
                  {status === "unmapped" && <Badge tone="neutral">▲ not comparable</Badge>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {pair.review_status && (
        <p className={styles.reviewed}>Reviewed as: <strong>{pair.review_status.replace(/_/g, " ")}</strong></p>
      )}

      <div className={styles.actions}>
        <Button variant="secondary" disabled={!!saving} onClick={() => handleReview("not_duplicate")}>
          {saving === "not_duplicate" ? "Saving…" : "Not a duplicate"}
        </Button>
        <Button variant="secondary" disabled={!!saving} onClick={() => handleReview("flagged_for_sender")}>
          {saving === "flagged_for_sender" ? "Saving…" : "Flag for sender"}
        </Button>
        <Button disabled={!!saving} onClick={() => handleReview("confirmed_duplicate")}>
          {saving === "confirmed_duplicate" ? "Saving…" : "Mark as duplicate pair"}
        </Button>
      </div>
    </div>
  );
}
