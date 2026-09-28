"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { formatDateTime } from "@/lib/formatters";
import { ErrorState, Panel, SkeletonRows, useToast } from "@/components/ds";
import { Button } from "@/components/ui/Button";
import styles from "./settings.module.css";

const SOURCE_LABEL: Record<string, string> = {
  OFSI: "UK OFSI consolidated list", OFAC: "US OFAC SDN list", EU: "EU financial sanctions file",
  UN: "UN Security Council consolidated list", CUSTOM: "Own watch list",
};

function errorText(err: unknown): string {
  return err instanceof ApiError ? err.message : "Please try again.";
}

export function SanctionsSettings({ canManage }: { canManage: boolean }) {
  const toast = useToast();
  const { data, error, loading, reload } = useApi(() => api.listSanctionsLists());
  const [name, setName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  if (loading && !data) return <Panel title="Sanctions lists"><SkeletonRows rows={3} /></Panel>;
  if (error || !data) return <ErrorState title="Sanctions lists could not be loaded" message={error ?? ""} onRetry={reload} />;
  async function load(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    try {
      const loaded = await api.loadSanctionsList(name.trim(), file);
      setName("");
      setFile(null);
      (e.target as HTMLFormElement).reset();
      reload();
      toast({ tone: "good", title: "List loaded", body: `${loaded.entry_count.toLocaleString("en-GB")} names from the ${SOURCE_LABEL[loaded.source] ?? loaded.source}. Run the sanctions check again on a report to screen it.` });
    } catch (err) {
      toast({ tone: "bad", title: "List not loaded", body: errorText(err) });
    } finally {
      setBusy(false);
    }
  }
  return (
    <Panel title="Sanctions lists" icon="shield"
      subtitle="Insured names are screened against every list loaded here. A match is a potential match for a person to review — never a verdict. Download the current official lists from their publishers and load them here; the format is recognised from the file.">
      <div className={styles.form}>
        {data.length === 0 && <p className={styles.muted}>No list loaded yet, so sanctions screening reports “not assessed” on every report.</p>}
        {data.length > 0 && (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <caption className={styles.srOnly}>Loaded sanctions lists</caption>
              <thead><tr><th scope="col">List</th><th scope="col">Names</th><th scope="col">Loaded</th><th scope="col">SHA-256</th><th scope="col"><span className={styles.srOnly}>Actions</span></th></tr></thead>
              <tbody>{data.map((l) => (
                <tr key={l.id}>
                  <td><div className={styles.who}><strong>{l.name}</strong><span>{SOURCE_LABEL[l.source] ?? l.source} · {l.file_name}</span></div></td>
                  <td>{l.entry_count.toLocaleString("en-GB")}</td>
                  <td><div className={styles.who}><span>{formatDateTime(l.uploaded_at)}</span><span>{l.uploaded_by}</span></div></td>
                  <td><code title={l.sha256}>{l.sha256.slice(0, 12)}…</code></td>
                  <td>{canManage && <Button size="sm" variant="ghost" onClick={async () => {
                    if (!window.confirm(`Remove “${l.name}”? Reports screened later will not be checked against it.`)) return;
                    try { await api.deleteSanctionsList(l.id); reload(); } catch (err) { toast({ tone: "bad", title: "Not removed", body: errorText(err) }); }
                  }}>Remove</Button>}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
        {canManage ? (
          <form className={styles.form} onSubmit={load} aria-label="Load a sanctions list">
            <label className={styles.field} htmlFor="sl-name">List name
              <input id="sl-name" className={styles.input} required maxLength={200} value={name} placeholder="OFSI consolidated list, 1 September" onChange={(e) => setName(e.target.value)} /></label>
            <label className={styles.field} htmlFor="sl-file">List file
              <input id="sl-file" className={styles.input} type="file" required accept=".csv,.xml,text/csv,application/xml,text/xml" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
              <span className={styles.help}>UK OFSI CSV, US OFAC sdn.csv, EU sanctions CSV, UN consolidated XML, or a CSV with a “name” column. Up to 50 MB.</span></label>
            <div className={styles.actions}><Button type="submit" loading={busy} disabled={!file || !name.trim()}>Load list</Button></div>
          </form>
        ) : <p className={styles.muted}>Only people who can edit data can load lists.</p>}
      </div>
    </Panel>
  );
}
