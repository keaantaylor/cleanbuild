"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { formatDateTime } from "@/lib/formatters";
import type { Preflight } from "@/lib/types";
import { useMe } from "@/components/auth/AuthGate";
import { ErrorState, PageHeader, Panel, Pill, SkeletonRows, StatusPill, ds, useToast } from "@/components/ds";
import { Button } from "@/components/ui/Button";
import styles from "./sender.module.css";

function errorText(err: unknown): string {
  return err instanceof ApiError ? err.message : "Please try again.";
}

function Result({ r }: { r: Preflight }) {
  return (
    <div className={styles.result} aria-live="polite">
      <p className={styles.verdict}><Pill tone={r.ready ? "good" : "warn"}>{r.ready ? "Ready to send" : "Needs attention"}</Pill> {r.verdict}</p>
      <ul className={styles.counts}>
        <li><strong>{r.rows.toLocaleString("en-GB")}</strong> rows read</li>
        <li><strong>{r.missing_mandatory_rows.toLocaleString("en-GB")}</strong> rows missing a mandatory field</li>
        <li><strong>{r.arithmetic_mismatches.toLocaleString("en-GB")}</strong> rows whose amounts do not add up</li>
        <li><strong>{r.exact_duplicates.toLocaleString("en-GB")}</strong> exact duplicate rows</li>
      </ul>
      <p className={styles.small}>{r.coverage_statement}</p>
      <table className={styles.table}>
        <caption className={styles.caption}>Sheets and the columns recognised</caption>
        <thead><tr><th scope="col">Sheet</th><th scope="col">Rows</th><th scope="col">Required fields not found</th><th scope="col">Columns not recognised</th></tr></thead>
        <tbody>{r.sheets.map((s) => (
          <tr key={s.sheet_name}><th scope="row">{s.sheet_name}</th><td>{s.rows.toLocaleString("en-GB")}</td>
            <td>{s.missing_required_fields.join(", ") || "None"}</td><td>{s.unmapped_columns.join(", ") || "None"}</td></tr>
        ))}</tbody>
      </table>
      {r.issues.length > 0 && (
        <>
          <h3 className={styles.h3}>Issues ({r.issues_total.toLocaleString("en-GB")}{r.issues_total > r.issues.length ? `, first ${r.issues.length} shown` : ""})</h3>
          <ul className={styles.issues}>
            {r.issues.map((i, n) => (
              <li key={n}><span className={styles.where}>{i.sheet_name ?? "File"}{i.row_number != null ? ` · row ${i.row_number}` : ""}</span> {i.message}</li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

export default function SenderPage() {
  const me = useMe();
  const toast = useToast();
  const subs = useApi(() => api.senderSubmissions(), []);
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<Preflight | null>(null);
  const [busy, setBusy] = useState<"check" | "send" | null>(null);
  async function check() {
    if (!file) return;
    setBusy("check");
    setResult(null);
    try { setResult(await api.senderPreflight(file)); }
    catch (err) { toast({ tone: "bad", title: "File not checked", body: errorText(err) }); }
    finally { setBusy(null); }
  }
  async function send() {
    if (!file) return;
    setBusy("send");
    try {
      await api.senderSubmit(file);
      toast({ tone: "good", title: "Sent", body: `${file.name} was sent to ${me?.tenant.name ?? "the organisation"}.` });
      setFile(null);
      setResult(null);
      subs.reload();
    } catch (err) { toast({ tone: "bad", title: "Not sent", body: errorText(err) }); }
    finally { setBusy(null); }
  }
  return (
    <>
      <PageHeader eyebrow="Sender portal" title="Check a bordereau before you send it"
        description={`Run the same checks ${me?.tenant.name ?? "the organisation"} runs, fix what you can, then send. Pre-flight keeps nothing: the file is checked and discarded.`} />
      <div className={ds.stack}>
        <Panel title="Pre-flight check" icon="check">
          <div className={styles.form}>
            <label className={styles.field} htmlFor="pf-file">Bordereau file (.xlsx, .xls, .xlsm or .csv)
              <input id="pf-file" type="file" className={styles.input} accept=".xlsx,.xls,.xlsm,.csv"
                onChange={(e) => { setFile(e.target.files?.[0] ?? null); setResult(null); }} /></label>
            <div className={styles.actions}>
              <Button onClick={check} loading={busy === "check"} disabled={!file || busy !== null}>Check file</Button>
              <Button variant={result?.ready ? "primary" : "secondary"} onClick={send} loading={busy === "send"} disabled={!file || busy !== null}>Send to {me?.tenant.name ?? "organisation"}</Button>
            </div>
          </div>
          {result && <Result r={result} />}
        </Panel>
        <Panel title="Your submissions" icon="inbox" subtitle="Files you have sent and where they are. The organisation reviews them in its own workspace.">
          {subs.error ? <ErrorState message={subs.error} onRetry={subs.reload} />
            : !subs.data ? <SkeletonRows rows={3} />
            : subs.data.length === 0 ? <p className={styles.small}>Nothing sent yet.</p>
            : <table className={styles.table}>
                <caption className={styles.caption}>Your submissions, newest first</caption>
                <thead><tr><th scope="col">File</th><th scope="col">Sent</th><th scope="col">Status</th></tr></thead>
                <tbody>{subs.data.map((s) => (
                  <tr key={s.id}><th scope="row">{s.file_name}</th><td>{formatDateTime(s.created_at)}</td><td><StatusPill status={s.status} /></td></tr>
                ))}</tbody>
              </table>}
        </Panel>
      </div>
    </>
  );
}
