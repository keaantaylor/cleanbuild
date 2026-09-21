"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ExceptionRow, Obligation } from "@/lib/types";
import { ReportPicker } from "@/components/report/ReportPicker";
import { ExceptionsTable } from "@/components/exceptions/ExceptionsTable";
import { ExceptionDetail } from "@/components/exceptions/ExceptionDetail";
import { Tabs } from "@/components/ui/Tabs";
import styles from "./page.module.css";

// Client-side predicates over the full (unfiltered) exception list, not a
// server round-trip per tab -- keeps every tab's count honest regardless
// of which tab is currently active (a prior version re-fetched filtered-
// by-check_type from the server, so switching tabs made every OTHER tab's
// count reflect whatever was already loaded, not the true total).
// ARITHMETIC and NOT_EVALUABLE are deliberately separate tabs even though
// today they're the only two statuses ARITHMETIC produces: a mismatch is
// wrong data, a not-evaluable row is data Truebind refused to guess
// about -- conflating them into one "Arithmetic" bucket would blur
// exactly the distinction Section 2 exists to make visible.
const FILTERS: { value: string; label: string; predicate: (e: ExceptionRow) => boolean }[] = [
  { value: "", label: "All flagged", predicate: () => true },
  { value: "MANDATORY_FIELD", label: "Missing mandatory", predicate: (e) => e.check_type === "MANDATORY_FIELD" },
  { value: "ARITHMETIC", label: "Arithmetic mismatch", predicate: (e) => e.check_type === "ARITHMETIC" && e.status !== "NOT_EVALUABLE" },
  { value: "NOT_EVALUABLE", label: "Not evaluable", predicate: (e) => e.status === "NOT_EVALUABLE" },
  { value: "MAPPING_COMPLETENESS", label: "Mapping completeness", predicate: (e) => e.check_type === "MAPPING_COMPLETENESS" },
];

export default function ExceptionsPage() {
  const [reportId, setReportId] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [exceptions, setExceptions] = useState<ExceptionRow[]>([]);
  const [selected, setSelected] = useState<ExceptionRow | null>(null);
  const [obligations, setObligations] = useState<Obligation[]>([]);

  useEffect(() => {
    if (!reportId) return;
    api.listExceptions(reportId).then(setExceptions);
    api.listObligations({ reportId }).then(setObligations);
    setSelected(null);
    setFilter("");
  }, [reportId]);

  async function handleCreateObligation(owner: string, deadline: string, note: string) {
    if (!reportId || !selected) return;
    await api.createObligation(reportId, {
      claim_row_id: selected.claim_row_id,
      owner,
      deadline: deadline || null,
      note: note || null,
    });
    setObligations(await api.listObligations({ reportId }));
  }

  const selectedObligations = obligations.filter((o) => o.claim_row_id === selected?.claim_row_id);
  const activeFilter = FILTERS.find((f) => f.value === filter) ?? FILTERS[0];
  const filteredRows = exceptions.filter(activeFilter.predicate);
  const counts = FILTERS.map((f) => exceptions.filter(f.predicate).length);

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <span className="eyebrow">What requires attention</span>
          <h1>Exceptions</h1>
        </div>
        <ReportPicker value={reportId} onChange={setReportId} />
      </div>

      {reportId && (
        <>
          <Tabs
            options={FILTERS.map((f, i) => ({ value: f.value, label: f.label, count: i === 0 ? undefined : counts[i] }))}
            active={filter}
            onChange={setFilter}
          />

          <div className={styles.layout}>
            <div className={styles.tableCol}>
              <ExceptionsTable rows={filteredRows} onSelect={setSelected} />
            </div>
            {selected && (
              <div className={styles.detailCol}>
                <ExceptionDetail
                  exception={selected}
                  obligations={selectedObligations}
                  onCreateObligation={handleCreateObligation}
                />
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
