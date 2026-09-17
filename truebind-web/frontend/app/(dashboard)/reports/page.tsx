"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { Report } from "@/lib/types";
import { Table, type Column } from "@/components/ui/Table";
import { GradeBadge } from "@/components/ui/statusBadges";
import { formatDateTime, formatPct } from "@/lib/formatters";

export default function ReportsPage() {
  const [reports, setReports] = useState<Report[] | null>(null);

  useEffect(() => {
    api.listReports().then(setReports);
  }, []);

  const columns: Column<Report>[] = [
    { key: "file_name", header: "File", render: (r) => <Link href={`/reports/${r.id}`}>{r.file_name}</Link> },
    { key: "status", header: "Status", render: (r) => r.status },
    { key: "coverage", header: "Coverage", render: (r) => formatPct(r.coverage_pct) },
    { key: "grade", header: "Grade", render: (r) => <GradeBadge grade={r.grade} /> },
    { key: "rows", header: "Rows", render: (r) => `${r.rows_processed} / ${r.rows_total}`, align: "right" },
    { key: "created", header: "Uploaded", render: (r) => formatDateTime(r.created_at) },
  ];

  return (
    <div>
      <h1>Reports</h1>
      {reports === null ? <p>Loading…</p> : <Table columns={columns} rows={reports} rowKey={(r) => r.id} />}
    </div>
  );
}
