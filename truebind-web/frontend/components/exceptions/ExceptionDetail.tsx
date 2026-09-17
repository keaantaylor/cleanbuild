"use client";

import { useState } from "react";
import type { ExceptionRow, Obligation } from "@/lib/types";
import { SeverityBadge } from "@/components/ui/statusBadges";
import { Button } from "@/components/ui/Button";
import { formatCurrency, formatDate } from "@/lib/formatters";
import styles from "./ExceptionDetail.module.css";

export function ExceptionDetail({
  exception, obligations, onCreateObligation,
}: {
  exception: ExceptionRow;
  obligations: Obligation[];
  onCreateObligation: (owner: string, deadline: string, note: string) => Promise<void>;
}) {
  const [owner, setOwner] = useState("");
  const [deadline, setDeadline] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);

  return (
    <div className={styles.panel}>
      <h3>Exception detail</h3>
      <div className={styles.row}>
        <SeverityBadge severity={exception.severity} />
        <span>{exception.check_type}</span>
      </div>
      <p className={styles.message}>{exception.message}</p>

      <dl className={styles.facts}>
        <div><dt>Claim reference</dt><dd>{exception.claim_reference ?? "—"}</dd></div>
        <div><dt>Sheet</dt><dd>{exception.sheet_name ?? "—"}</dd></div>
        <div><dt>Row</dt><dd>{exception.row_index + 1}</dd></div>
        <div><dt>Amount</dt><dd>{formatCurrency(exception.amount)}</dd></div>
      </dl>

      <h4>Obligations</h4>
      {obligations.length === 0 && <p className={styles.empty}>No obligation raised for this row yet.</p>}
      <ul className={styles.obligationList}>
        {obligations.map((o) => (
          <li key={o.id}>
            <strong>{o.status}</strong> — {o.owner ?? "unassigned"}, due {formatDate(o.deadline)}
            {o.note && <div className={styles.note}>{o.note}</div>}
          </li>
        ))}
      </ul>

      <form
        className={styles.form}
        onSubmit={async (e) => {
          e.preventDefault();
          setSaving(true);
          try {
            await onCreateObligation(owner, deadline, note);
            setOwner(""); setDeadline(""); setNote("");
          } finally {
            setSaving(false);
          }
        }}
      >
        <label>
          Owner
          <input value={owner} onChange={(e) => setOwner(e.target.value)} placeholder="Assign to…" />
        </label>
        <label>
          Deadline
          <input type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} />
        </label>
        <label>
          Note
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Optional note" />
        </label>
        <Button type="submit" disabled={saving || !owner}>{saving ? "Saving…" : "Raise obligation"}</Button>
      </form>
    </div>
  );
}
