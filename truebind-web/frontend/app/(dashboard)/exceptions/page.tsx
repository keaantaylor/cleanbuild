"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ExceptionRow, Obligation } from "@/lib/types";
import { ReportPicker } from "@/components/report/ReportPicker";
import { ExceptionsTable } from "@/components/exceptions/ExceptionsTable";
import { ExceptionDetail } from "@/components/exceptions/ExceptionDetail";
import { Tabs } from "@/components/ui/Tabs";
import styles from "./page.module.css";

const FILTERS = [
  { value: "", label: "All flagged" },
  { value: "MANDATORY_FIELD", label: "Missing mandatory" },
  { value: "ARITHMETIC", label: "Arithmetic" },
  { value: "MAPPING_COMPLETENESS", label: "Mapping completeness" },
  { value: "DATA_QUALITY", label: "Data quality" },
];

export default function ExceptionsPage() {
  const [reportId, setReportId] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [exceptions, setExceptions] = useState<ExceptionRow[]>([]);
  const [selected, setSelected] = useState<ExceptionRow | null>(null);
  const [obligations, setObligations] = useState<Obligation[]>([]);

  useEffect(() => {
    if (!reportId) return;
    api.listExceptions(reportId, filter || undefined).then(setExceptions);
    api.listObligations({ reportId }).then(setObligations);
    setSelected(null);
  }, [reportId, filter]);

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
  const counts = FILTERS.map((f) =>
    f.value ? exceptions.filter((e) => e.check_type === f.value).length : exceptions.length,
  );

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1>Exceptions</h1>
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
              <ExceptionsTable rows={exceptions} onSelect={setSelected} />
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
