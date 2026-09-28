"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { decimalMoney } from "@/lib/findings";
import type { BinderInput } from "@/lib/types";
import { ErrorState, Panel, SkeletonRows, useToast } from "@/components/ds";
import { Button } from "@/components/ui/Button";
import styles from "./settings.module.css";

const EMPTY: BinderInput = {
  name: "", umr: null, coverholder: null, inception_date: "", expiry_date: "", currencies: [], limit_currency: "GBP",
  claims_authority: null, aggregate_limit: null,
};

function errorText(err: unknown): string {
  return err instanceof ApiError ? err.message : "Please try again.";
}

export function BindersSettings({ canManage }: { canManage: boolean }) {
  const toast = useToast();
  const { data, error, loading, reload } = useApi(() => api.listBinders());
  const [f, setF] = useState<BinderInput>(EMPTY);
  const [ccys, setCcys] = useState("");
  const [busy, setBusy] = useState(false);
  if (loading && !data) return <Panel title="Binders"><SkeletonRows rows={3} /></Panel>;
  if (error || !data) return <ErrorState title="Binders could not be loaded" message={error ?? ""} onRetry={reload} />;
  const edit = (patch: Partial<BinderInput>) => setF({ ...f, ...patch });
  async function add(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api.createBinder({ ...f, currencies: ccys.split(/[\s,]+/).filter(Boolean),
        claims_authority: f.claims_authority || null, aggregate_limit: f.aggregate_limit || null,
        umr: f.umr || null, coverholder: f.coverholder || null });
      setF(EMPTY);
      setCcys("");
      reload();
      toast({ tone: "good", title: "Binder added", body: "Assign it to a report on the report's Checks section." });
    } catch (err) {
      toast({ tone: "bad", title: "Binder not added", body: errorText(err) });
    } finally {
      setBusy(false);
    }
  }
  return (
    <Panel title="Binders" icon="shield"
      subtitle="The binding authorities your bordereaux are checked against: period, permitted currencies, claims settlement authority and aggregate limit. Rules a binder does not set are reported as not assessed.">
      <div className={styles.form}>
        {data.length === 0 && <p className={styles.muted}>No binders yet.</p>}
        {data.length > 0 && (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <caption className={styles.srOnly}>Binders</caption>
              <thead><tr><th scope="col">Binder</th><th scope="col">Period</th><th scope="col">Currencies</th><th scope="col">Authority</th><th scope="col">Aggregate</th><th scope="col"><span className={styles.srOnly}>Actions</span></th></tr></thead>
              <tbody>{data.map((b) => (
                <tr key={b.id}>
                  <td><div className={styles.who}><strong>{b.name}</strong><span>{[b.umr, b.coverholder].filter(Boolean).join(" · ") || "—"}</span></div></td>
                  <td>{b.inception_date} to {b.expiry_date}</td>
                  <td>{b.currencies.join(", ") || "Not set"}</td>
                  <td>{b.claims_authority ? decimalMoney(b.claims_authority, b.limit_currency) : "Not set"}</td>
                  <td>{b.aggregate_limit ? decimalMoney(b.aggregate_limit, b.limit_currency) : "Not set"}</td>
                  <td>{canManage && <Button size="sm" variant="ghost" onClick={async () => {
                    if (!window.confirm(`Remove binder “${b.name}”?`)) return;
                    try { await api.deleteBinder(b.id); reload(); } catch (err) { toast({ tone: "bad", title: "Not removed", body: errorText(err) }); }
                  }}>Remove</Button>}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
        {canManage ? (
          <form className={styles.form} onSubmit={add} aria-label="Add a binder">
            <div className={styles.row}>
              <label className={styles.field} htmlFor="b-name">Name
                <input id="b-name" className={styles.input} required maxLength={200} value={f.name} onChange={(e) => edit({ name: e.target.value })} /></label>
              <label className={styles.field} htmlFor="b-umr">UMR <span className={styles.help}>Optional</span>
                <input id="b-umr" className={styles.input} maxLength={64} value={f.umr ?? ""} onChange={(e) => edit({ umr: e.target.value })} /></label>
            </div>
            <label className={styles.field} htmlFor="b-ch">Coverholder <span className={styles.help}>Optional</span>
              <input id="b-ch" className={styles.input} maxLength={200} value={f.coverholder ?? ""} onChange={(e) => edit({ coverholder: e.target.value })} /></label>
            <div className={styles.row}>
              <label className={styles.field} htmlFor="b-inc">Inception date
                <input id="b-inc" type="date" className={styles.input} required value={f.inception_date} onChange={(e) => edit({ inception_date: e.target.value })} /></label>
              <label className={styles.field} htmlFor="b-exp">Expiry date (inclusive)
                <input id="b-exp" type="date" className={styles.input} required value={f.expiry_date} onChange={(e) => edit({ expiry_date: e.target.value })} /></label>
            </div>
            <label className={styles.field} htmlFor="b-ccys">Permitted settlement currencies
              <input id="b-ccys" className={styles.input} value={ccys} placeholder="GBP, EUR" onChange={(e) => setCcys(e.target.value)} />
              <span className={styles.help}>ISO 4217 codes separated by commas. Leave empty to skip the currency rule.</span></label>
            <div className={styles.row}>
              <label className={styles.field} htmlFor="b-lccy">Limit currency
                <input id="b-lccy" className={styles.input} required maxLength={3} value={f.limit_currency} onChange={(e) => edit({ limit_currency: e.target.value.toUpperCase() })} /></label>
              <label className={styles.field} htmlFor="b-auth">Claims settlement authority <span className={styles.help}>Per claim, optional</span>
                <input id="b-auth" className={styles.input} inputMode="decimal" pattern="\d+(\.\d{1,2})?" value={f.claims_authority ?? ""} onChange={(e) => edit({ claims_authority: e.target.value })} /></label>
            </div>
            <label className={styles.field} htmlFor="b-agg">Aggregate limit <span className={styles.help}>Indemnity paid across the report, optional</span>
              <input id="b-agg" className={styles.input} inputMode="decimal" pattern="\d+(\.\d{1,2})?" value={f.aggregate_limit ?? ""} onChange={(e) => edit({ aggregate_limit: e.target.value })} /></label>
            <div className={styles.actions}><Button type="submit" loading={busy}>Add binder</Button></div>
          </form>
        ) : <p className={styles.muted}>Only people who can edit data can add binders.</p>}
      </div>
    </Panel>
  );
}
