"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Report } from "@/lib/types";
import styles from "./ReportPicker.module.css";

export function ReportPicker({ value, onChange }: { value: string | null; onChange: (reportId: string) => void }) {
  const [reports, setReports] = useState<Report[]>([]);

  useEffect(() => {
    api.listReports().then((list) => {
      setReports(list);
      if (!value && list.length > 0) onChange(list[0].id);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (reports.length === 0) {
    return <p className={styles.empty}>No reports yet — upload a bordereau first.</p>;
  }

  return (
    <select className={styles.select} value={value ?? ""} onChange={(e) => onChange(e.target.value)}>
      {reports.map((r) => (
        <option key={r.id} value={r.id}>{r.file_name}</option>
      ))}
    </select>
  );
}
