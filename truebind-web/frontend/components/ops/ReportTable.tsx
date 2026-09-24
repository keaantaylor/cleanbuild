"use client";

import Link from "next/link";
import type { Report } from "@/lib/types";
import { IN_PROGRESS } from "@/lib/api";
import { FileCard, StatusPill } from "@/components/ds";
import { formatBytes, formatNumber, timeAgo, formatDateTime } from "@/lib/formatters";
import styles from "./ops.module.css";

/** Files that are not finished continue in Intake (live progress, then
 * mapping review); finished or failed ones open their report. */
export function reportHref(r: Report): string {
  return IN_PROGRESS.has(r.status) || r.status === "WAITING_FOR_REVIEW" ? `/upload?reportId=${r.id}` : `/reports/${r.id}`;
}

function nextAction(r: Report): string {
  if (r.status === "WAITING_FOR_REVIEW") return "Review mapping";
  if (IN_PROGRESS.has(r.status)) return "Watch";
  if (r.status === "FAILED") return "See why";
  return "Open report";
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
            {detailed && <th scope="col" className={styles.num}>Issues found</th>}
            <th scope="col" className={styles.num}>Grade</th>
            {detailed && <th scope="col"><span className="sr-only">Action</span></th>}
          </tr>
        </thead>
        <tbody>
          {reports.map((r) => (
            <tr key={r.id}>
              <td>
                <FileCard name={r.file_name} href={reportHref(r)}
                  meta={`${(r.file_kind ?? "").toUpperCase()} · ${formatBytes(r.file_size_bytes)}`} />
              </td>
              {detailed && <td>{r.sender ?? <span className={styles.sub}>—</span>}<div className={styles.sub}>{r.programme ?? ""}</div></td>}
              {detailed && <td className={styles.sub}>{r.source_channel === "upload" ? "Web upload" : r.source_channel}</td>}
              <td><time dateTime={r.created_at} title={formatDateTime(r.created_at)}>{timeAgo(r.created_at)}</time></td>
              <td><StatusPill status={r.status} /></td>
              <td className={styles.num}>{r.sheet_count_total || "—"}</td>
              <td className={styles.num}>{r.rows_processed ? formatNumber(r.rows_processed) : "—"}</td>
              {detailed && <td className={styles.num}>{r.issues_found == null ? "—"
                : r.issues_found === 0 ? <span className={styles.ok}>0</span>
                : <Link href={`/exceptions?reportId=${r.id}`} className={styles.issues}>{formatNumber(r.issues_found)}</Link>}</td>}
              <td className={styles.num}>{r.grade ? `${r.grade}/5` : "—"}</td>
              {detailed && <td><Link href={reportHref(r)} className={styles.rowAction}>{nextAction(r)} →</Link></td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
