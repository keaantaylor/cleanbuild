"use client";

import Link from "next/link";
import type { Report } from "@/lib/types";
import { IN_PROGRESS } from "@/lib/api";
import { Icon, StatusPill } from "@/components/ds";
import { formatBytes, formatNumber, timeAgo, formatDateTime } from "@/lib/formatters";
import styles from "./ops.module.css";

/** Files that are not finished continue in Intake (live progress, then
 * mapping review); finished or failed ones open their report. */
export function reportHref(r: Report): string {
  return IN_PROGRESS.has(r.status) || r.status === "WAITING_FOR_REVIEW" ? `/upload?reportId=${r.id}` : `/reports/${r.id}`;
}

/** Inbound files with their provenance and state. */
export function ReportTable({ reports, detailed }: { reports: Report[]; detailed?: boolean }) {
  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th scope="col">File</th>
            {detailed && <th scope="col">Sender / programme</th>}
            {detailed && <th scope="col">Channel</th>}
            <th scope="col">Received</th>
            <th scope="col">Status</th>
            <th scope="col" className={styles.num}>Sheets</th>
            <th scope="col" className={styles.num}>Rows</th>
            <th scope="col" className={styles.num}>Grade</th>
          </tr>
        </thead>
        <tbody>
          {reports.map((r) => (
            <tr key={r.id}>
              <td>
                <div className={styles.fileCell}>
                  <span className={styles.fileIcon}><Icon name="file" size={15} /></span>
                  <div style={{ minWidth: 0 }}>
                    <Link href={reportHref(r)} className={styles.fileName} title={r.file_name}>{r.file_name}</Link>
                    <span className={styles.sub}>{(r.file_kind ?? "").toUpperCase()} · {formatBytes(r.file_size_bytes)}</span>
                  </div>
                </div>
              </td>
              {detailed && <td>{r.sender ?? <span className={styles.sub}>—</span>}<div className={styles.sub}>{r.programme ?? ""}</div></td>}
              {detailed && <td className={styles.sub}>{r.source_channel === "upload" ? "Web upload" : r.source_channel}</td>}
              <td><time dateTime={r.created_at} title={formatDateTime(r.created_at)}>{timeAgo(r.created_at)}</time></td>
              <td><StatusPill status={r.status} /></td>
              <td className={styles.num}>{r.sheet_count_total || "—"}</td>
              <td className={styles.num}>{r.rows_processed ? formatNumber(r.rows_processed) : "—"}</td>
              <td className={styles.num}>{r.grade ? `${r.grade}/5` : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
