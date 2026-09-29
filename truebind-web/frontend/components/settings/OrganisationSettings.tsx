"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import type { OrgType } from "@/lib/types";
import { ErrorState, Panel, SkeletonRows, useToast } from "@/components/ds";
import { Button } from "@/components/ui/Button";
import styles from "./settings.module.css";

const ORG_TYPES: { value: OrgType; label: string }[] = [
  { value: "capacity_provider", label: "Capacity provider (managing agent, carrier)" },
  { value: "mga", label: "MGA / coverholder" },
  { value: "tpa", label: "Third-party administrator" },
];

export function OrganisationSettings({ canManage }: { canManage: boolean }) {
  const toast = useToast();
  const { data, error, loading, reload } = useApi(() => api.getOrg());
  const [draft, setDraft] = useState<{ name: string; org_type: OrgType; require_2fa: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  if (loading && !data) return <Panel title="Organisation"><SkeletonRows rows={3} /></Panel>;
  if (error || !data) return <ErrorState title="Organisation settings could not be loaded" message={error ?? ""} onRetry={reload} />;
  const form = draft ?? { name: data.name, org_type: data.org_type, require_2fa: data.require_2fa };
  const dirty = form.name !== data.name || form.org_type !== data.org_type || form.require_2fa !== data.require_2fa;

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api.updateOrg(form);
      setDraft(null);
      reload();
      toast({ tone: "good", title: "Organisation updated", body: "The change is recorded in the audit trail." });
    } catch (err) {
      toast({ tone: "bad", title: "Not saved", body: err instanceof ApiError ? err.message : "Please try again." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title="Organisation" icon="server" subtitle="Who you are in TrueBind, and the rules every member signs in under.">
      <form className={styles.form} onSubmit={save}>
        <div className={styles.row}>
          <label className={styles.field}>Name
            <input className={styles.input} value={form.name} maxLength={200} required disabled={!canManage}
              onChange={(e) => setDraft({ ...form, name: e.target.value })} />
          </label>
          <div className={styles.field}>
            <label htmlFor="org-type">Organisation type</label>
            <select id="org-type" className={styles.select} value={form.org_type} disabled={!canManage}
              onChange={(e) => setDraft({ ...form, org_type: e.target.value as OrgType })}>
              {ORG_TYPES.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
        </div>
        <label className={styles.check}>
          <input type="checkbox" checked={form.require_2fa} disabled={!canManage}
            onChange={(e) => setDraft({ ...form, require_2fa: e.target.checked })} />
          <span>Require two-step verification for every member
            <span className={styles.help}><br />Members without it are asked to set it up before they can continue. Single sign-on users rely on your identity provider&rsquo;s MFA. Turn it on for your own account first.</span>
          </span>
        </label>
        <p className={styles.help}>Data retention: {data.retention_days} days.</p>
        {canManage && (
          <div className={styles.actions}>
            <Button type="submit" loading={busy} disabled={!dirty}>Save changes</Button>
            {dirty && <Button type="button" variant="ghost" onClick={() => setDraft(null)}>Discard</Button>}
          </div>
        )}
      </form>
    </Panel>
  );
}
