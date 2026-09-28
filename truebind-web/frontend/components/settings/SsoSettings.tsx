"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { ROLE_LABEL } from "@/lib/auth";
import type { Role, SsoConfig, SsoConfigInput } from "@/lib/types";
import { ErrorState, KeyValue, Panel, Pill, SkeletonRows, useToast } from "@/components/ds";
import { Button } from "@/components/ui/Button";
import styles from "./settings.module.css";

function toInput(c: SsoConfig): SsoConfigInput {
  return {
    issuer: c.issuer ?? "", client_id: c.client_id ?? "", client_secret: null,
    token_auth_method: c.token_auth_method ?? "client_secret_post", domains: c.domains,
    jit_provisioning: c.jit_provisioning, default_role: (c.default_role ?? "VIEWER") as Role, enabled: c.configured ? c.enabled : true,
  };
}

export function SsoSettings({ canManage }: { canManage: boolean }) {
  const toast = useToast();
  const { data, error, loading, reload } = useApi(() => api.getSso());
  const [form, setForm] = useState<SsoConfigInput | null>(null);
  const [domains, setDomains] = useState("");
  const [busy, setBusy] = useState(false);
  if (loading && !data) return <Panel title="Single sign-on"><SkeletonRows rows={4} /></Panel>;
  if (error || !data) return <ErrorState title="Single sign-on settings could not be loaded" message={error ?? ""} onRetry={reload} />;
  const f = form ?? toInput(data);
  const domainText = form ? domains : data.domains.join(", ");

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const list = domainText.split(/[\s,;]+/).map((d) => d.trim()).filter(Boolean);
      await api.saveSso({ ...f, domains: list, client_secret: f.client_secret || null });
      setForm(null);
      reload();
      toast({ tone: "good", title: "Single sign-on saved", body: "Members with these e-mail domains can now sign in through your identity provider." });
    } catch (err) {
      toast({ tone: "bad", title: "Not saved", body: err instanceof ApiError ? err.message : "Please try again." });
    } finally {
      setBusy(false);
    }
  }

  const edit = (patch: Partial<SsoConfigInput>) => { if (!form) setDomains(domainText); setForm({ ...f, ...patch }); };

  return (
    <Panel title="Single sign-on (OIDC)" icon="link"
      subtitle="Microsoft Entra ID, WorkOS or any OpenID Connect provider. People sign in with their work e-mail and are sent to your identity provider."
      actions={<Pill tone={data.configured && data.enabled ? "live" : "neutral"}>{data.configured ? (data.enabled ? "Active" : "Disabled") : "Not configured"}</Pill>}>
      <div className={styles.form}>
        <KeyValue items={[["Redirect (callback) URL", <code key="cb" className={styles.codeBox}>{data.callback_url}</code>]]} />
        <p className={styles.help}>Register this URL in your identity provider. Grant the <code>openid email profile</code> scopes.</p>
        {canManage ? (
          <form className={styles.form} onSubmit={save}>
            <label className={styles.field}>Issuer URL
              <input className={styles.input} value={f.issuer} required placeholder="https://login.microsoftonline.com/<tenant-id>/v2.0" onChange={(e) => edit({ issuer: e.target.value })} />
            </label>
            <div className={styles.row}>
              <label className={styles.field}>Client ID<input className={styles.input} value={f.client_id} required onChange={(e) => edit({ client_id: e.target.value })} /></label>
              <label className={styles.field}>Client secret
                <input className={styles.input} type="password" value={f.client_secret ?? ""} autoComplete="off"
                  placeholder={data.has_client_secret ? "Saved — leave blank to keep" : ""} onChange={(e) => edit({ client_secret: e.target.value })} />
              </label>
            </div>
            <label className={styles.field}>E-mail domains
              <input className={styles.input} value={domainText} required placeholder="example.com, example.co.uk"
                onChange={(e) => { if (!form) setForm(f); setDomains(e.target.value); }} />
              <span className={styles.help}>Only domains your organisation owns. Each domain can belong to one organisation.</span>
            </label>
            <div className={styles.row}>
              <div className={styles.field}>
                <label htmlFor="sso-role">Role for new people</label>
                <select id="sso-role" className={styles.select} value={f.default_role} onChange={(e) => edit({ default_role: e.target.value as Role })}>
                  {(["VIEWER", "ANALYST", "ADMIN", "SENDER"] as Role[]).map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
                </select>
              </div>
              <div className={styles.field}>
                <label htmlFor="sso-auth">Client authentication</label>
                <select id="sso-auth" className={styles.select} value={f.token_auth_method} onChange={(e) => edit({ token_auth_method: e.target.value })}>
                  <option value="client_secret_post">client_secret_post</option>
                  <option value="client_secret_basic">client_secret_basic</option>
                </select>
              </div>
            </div>
            <label className={styles.check}><input type="checkbox" checked={f.jit_provisioning} onChange={(e) => edit({ jit_provisioning: e.target.checked })} />
              <span>Create accounts on first sign-in<span className={styles.help}><br />Off: only people you have invited can sign in with SSO. Existing accounts from other organisations are never added automatically.</span></span>
            </label>
            <label className={styles.check}><input type="checkbox" checked={f.enabled} onChange={(e) => edit({ enabled: e.target.checked })} /><span>Enabled</span></label>
            <div className={styles.actions}>
              <Button type="submit" loading={busy} disabled={!form}>Save</Button>
              {form && <Button type="button" variant="ghost" onClick={() => setForm(null)}>Discard</Button>}
              {data.configured && !form && (
                <Button type="button" variant="ghost" onClick={async () => {
                  if (!window.confirm("Remove single sign-on? Members will need a password or an invitation to sign in.")) return;
                  try { await api.removeSso(); reload(); } catch (err) { toast({ tone: "bad", title: "Not removed", body: err instanceof ApiError ? err.message : "" }); }
                }}>Remove</Button>
              )}
            </div>
          </form>
        ) : (
          <p className={styles.muted}>Only owners and admins can change single sign-on.</p>
        )}
      </div>
    </Panel>
  );
}
