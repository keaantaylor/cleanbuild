"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { channelStatus } from "@/lib/findings";
import { formatDateTime } from "@/lib/formatters";
import type { SftpInput, WebhookDelivery, WebhookEvent } from "@/lib/types";
import { ErrorState, KeyValue, Panel, Pill, SkeletonRows, useToast } from "@/components/ds";
import { Button } from "@/components/ui/Button";
import styles from "./settings.module.css";

const EVENTS: { value: WebhookEvent; label: string }[] = [
  { value: "report.completed", label: "Report completed" },
  { value: "report.failed", label: "Report failed" },
  { value: "report.waiting_for_review", label: "Mapping ready for review" },
];

function errorText(err: unknown): string {
  return err instanceof ApiError ? err.message : "Please try again.";
}

function StatusPill({ status }: { status: string }) {
  const s = channelStatus(status);
  return <Pill tone={s.tone}>{s.label}</Pill>;
}

function InboundEmail({ canManage }: { canManage: boolean }) {
  const toast = useToast();
  const { data, error, loading, reload } = useApi(() => api.getInbound());
  const [busy, setBusy] = useState(false);
  if (loading && !data) return <Panel title="E-mail intake"><SkeletonRows rows={2} /></Panel>;
  if (error || !data) return <ErrorState title="E-mail intake could not be loaded" message={error ?? ""} onRetry={reload} />;
  async function rotate() {
    if (data?.address && !window.confirm("Create a new address? The current one stops accepting mail immediately.")) return;
    setBusy(true);
    try {
      await api.rotateInbound();
      reload();
      toast({ tone: "good", title: "Inbound address ready", body: "Senders can now e-mail bordereaux to it." });
    } catch (err) {
      toast({ tone: "bad", title: "Not changed", body: errorText(err) });
    } finally {
      setBusy(false);
    }
  }
  return (
    <Panel title="E-mail intake" icon="mail"
      subtitle="Bordereaux e-mailed to this address are checked and ingested like uploads. Each attachment becomes a report."
      actions={<StatusPill status={!data.configured ? "not_configured" : data.address ? "active" : "not_set_up"} />}>
      <div className={styles.form}>
        {!data.configured && <p className={styles.muted}>E-mail intake is not configured on this server yet.</p>}
        {data.configured && (data.address
          ? <KeyValue items={[["Inbound address", <code key="a" className={styles.codeBox}>{data.address}</code>]]} />
          : <p className={styles.muted}>No address yet.</p>)}
        {data.configured && canManage && (
          <div className={styles.actions}>
            <Button type="button" loading={busy} onClick={rotate}>{data.address ? "Replace address" : "Create address"}</Button>
          </div>
        )}
      </div>
    </Panel>
  );
}

function Deliveries({ endpointId, canManage }: { endpointId: string; canManage: boolean }) {
  const toast = useToast();
  const { data, error, loading, reload } = useApi(() => api.webhookDeliveries(endpointId));
  if (loading && !data) return <SkeletonRows rows={2} />;
  if (error || !data) return <p className={styles.muted}>Deliveries could not be loaded.</p>;
  if (!data.length) return <p className={styles.muted}>No deliveries yet.</p>;
  const tone = (d: WebhookDelivery) => (d.status === "DELIVERED" ? "good" : d.status === "PENDING" ? "neutral" : "bad");
  return (
    <table className={styles.table}>
      <caption className={styles.srOnly}>Recent webhook deliveries</caption>
      <thead><tr><th scope="col">Event</th><th scope="col">Status</th><th scope="col">Attempts</th><th scope="col">When</th><th scope="col"><span className={styles.srOnly}>Actions</span></th></tr></thead>
      <tbody>
        {data.slice(0, 10).map((d) => (
          <tr key={d.id}>
            <td>{d.event_type}</td>
            <td><Pill tone={tone(d)}>{d.status.toLowerCase()}</Pill>{d.last_error ? <span className={styles.help}> {d.last_error}</span> : null}</td>
            <td>{d.attempts}</td>
            <td>{formatDateTime(d.created_at)}</td>
            <td>{canManage && d.status !== "PENDING" && (
              <Button size="sm" variant="ghost" onClick={async () => {
                try { await api.replayWebhook(d.id); reload(); toast({ tone: "good", title: "Queued to send again" }); }
                catch (err) { toast({ tone: "bad", title: "Not queued", body: errorText(err) }); }
              }}>Send again</Button>
            )}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Webhooks({ canManage }: { canManage: boolean }) {
  const toast = useToast();
  const { data, error, loading, reload } = useApi(() => api.listWebhooks());
  const [url, setUrl] = useState("");
  const [events, setEvents] = useState<WebhookEvent[]>(["report.completed"]);
  const [secret, setSecret] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  if (loading && !data) return <Panel title="Webhooks"><SkeletonRows rows={3} /></Panel>;
  if (error || !data) return <ErrorState title="Webhooks could not be loaded" message={error ?? ""} onRetry={reload} />;
  async function add(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const created = await api.createWebhook(url.trim(), events);
      setSecret(created.secret);
      setUrl("");
      reload();
    } catch (err) {
      toast({ tone: "bad", title: "Endpoint not added", body: errorText(err) });
    } finally {
      setBusy(false);
    }
  }
  return (
    <Panel title="Webhooks" icon="link"
      subtitle="Report events are posted to your systems, signed (webhook-id, webhook-timestamp, webhook-signature: HMAC-SHA256). Failed deliveries are retried with backoff."
      actions={<StatusPill status={data.length ? "active" : "not_set_up"} />}>
      <div className={styles.form}>
        {secret && (
          <div role="status" className={styles.notice}>
            <strong>Signing secret — copy it now, it will not be shown again.</strong>
            <code className={styles.codeBox}>{secret}</code>
            <Button size="sm" variant="ghost" onClick={() => setSecret(null)}>I have stored it</Button>
          </div>
        )}
        {data.length === 0 && <p className={styles.muted}>No endpoints yet.</p>}
        {data.map((ep) => (
          <div key={ep.id} className={styles.card}>
            <div className={styles.row}>
              <div><code>{ep.url}</code><div className={styles.help}>{ep.events.join(", ")}</div></div>
              <div className={styles.actions}>
                <Button size="sm" variant="ghost" onClick={() => setOpen(open === ep.id ? null : ep.id)} aria-expanded={open === ep.id}>Deliveries</Button>
                {canManage && <Button size="sm" variant="ghost" onClick={async () => {
                  try { await api.testWebhook(ep.id); toast({ tone: "good", title: "Test event queued", body: "It is sent within a few seconds." }); }
                  catch (err) { toast({ tone: "bad", title: "Not queued", body: errorText(err) }); }
                }}>Send test</Button>}
                {canManage && <Button size="sm" variant="ghost" onClick={async () => {
                  if (!window.confirm("Remove this endpoint? It stops receiving events.")) return;
                  try { await api.deleteWebhook(ep.id); reload(); } catch (err) { toast({ tone: "bad", title: "Not removed", body: errorText(err) }); }
                }}>Remove</Button>}
              </div>
            </div>
            {open === ep.id && <Deliveries endpointId={ep.id} canManage={canManage} />}
          </div>
        ))}
        {canManage ? (
          <form className={styles.form} onSubmit={add}>
            <label className={styles.field} htmlFor="hook-url">Endpoint URL
              <input id="hook-url" className={styles.input} type="url" required value={url} placeholder="https://example.com/truebind-events"
                onChange={(e) => setUrl(e.target.value)} />
              <span className={styles.help}>Must be https and reachable on the public internet.</span>
            </label>
            <fieldset className={styles.field}>
              <legend>Events</legend>
              {EVENTS.map((ev) => (
                <label key={ev.value} className={styles.check}>
                  <input type="checkbox" checked={events.includes(ev.value)}
                    onChange={(e) => setEvents(e.target.checked ? [...events, ev.value] : events.filter((x) => x !== ev.value))} />
                  <span>{ev.label}</span>
                </label>
              ))}
            </fieldset>
            <div className={styles.actions}><Button type="submit" loading={busy} disabled={!url || events.length === 0}>Add endpoint</Button></div>
          </form>
        ) : <p className={styles.muted}>Only owners and admins can change webhooks.</p>}
      </div>
    </Panel>
  );
}

const EMPTY_SFTP: SftpInput = {
  host: "", port: 22, username: "", password: "", private_key: null, host_key_fingerprint: "", remote_dir: "/",
  auto_deliver: false, enabled: true,
};

function Sftp({ canManage }: { canManage: boolean }) {
  const toast = useToast();
  const { data, error, loading, reload } = useApi(() => api.getSftp());
  const [form, setForm] = useState<SftpInput | null>(null);
  const [useKey, setUseKey] = useState(false);
  const [busy, setBusy] = useState(false);
  if (loading && data === null && !error) return <Panel title="SFTP delivery"><SkeletonRows rows={3} /></Panel>;
  if (error) return <ErrorState title="SFTP settings could not be loaded" message={error} onRetry={reload} />;
  const current = data ?? null;
  const f = form ?? (current ? { ...EMPTY_SFTP, ...current, password: "", private_key: null } : EMPTY_SFTP);
  const edit = (patch: Partial<SftpInput>) => setForm({ ...f, ...patch });
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api.saveSftp({ ...f, password: useKey ? null : f.password || null, private_key: useKey ? f.private_key || null : null });
      setForm(null);
      reload();
      toast({ tone: "good", title: "SFTP destination saved", body: "Use Test connection to check it." });
    } catch (err) {
      toast({ tone: "bad", title: "Not saved", body: errorText(err) });
    } finally {
      setBusy(false);
    }
  }
  return (
    <Panel title="SFTP delivery" icon="send"
      subtitle="Outputs are written to your partner's SFTP server. The server's host key is pinned: if it changes, nothing is sent."
      actions={<StatusPill status={current?.enabled ? "active" : "not_set_up"} />}>
      <div className={styles.form}>
        {current && (
          <KeyValue items={[
            ["Server", `${current.username}@${current.host}:${current.port}`],
            ["Folder", current.remote_dir],
            ["Host key", <code key="fp">{current.host_key_fingerprint}</code>],
            ["Sign-in", current.auth === "private_key" ? "Private key (stored encrypted)" : "Password (stored encrypted)"],
            ["Automatic", current.auto_deliver ? "Claims and exceptions sent when a report completes" : "Off — send from a report"],
          ]} />
        )}
        {canManage ? (
          <form className={styles.form} onSubmit={save}>
            <div className={styles.row}>
              <label className={styles.field} htmlFor="sftp-host">Host<input id="sftp-host" className={styles.input} required value={f.host} onChange={(e) => edit({ host: e.target.value })} /></label>
              <label className={styles.field} htmlFor="sftp-port">Port<input id="sftp-port" className={styles.input} type="number" min={1} max={65535} required value={f.port} onChange={(e) => edit({ port: Number(e.target.value) })} /></label>
            </div>
            <div className={styles.row}>
              <label className={styles.field} htmlFor="sftp-user">Username<input id="sftp-user" className={styles.input} required value={f.username} onChange={(e) => edit({ username: e.target.value })} /></label>
              <label className={styles.field} htmlFor="sftp-dir">Folder<input id="sftp-dir" className={styles.input} required value={f.remote_dir} onChange={(e) => edit({ remote_dir: e.target.value })} /></label>
            </div>
            <label className={styles.field} htmlFor="sftp-fp">Host key fingerprint
              <input id="sftp-fp" className={styles.input} required value={f.host_key_fingerprint} placeholder="SHA256:…" onChange={(e) => edit({ host_key_fingerprint: e.target.value })} />
              <span className={styles.help}>Ask your partner, or run <code>ssh-keyscan host | ssh-keygen -lf -</code> and check it with them.</span>
            </label>
            <label className={styles.check}><input type="checkbox" checked={useKey} onChange={(e) => setUseKey(e.target.checked)} /><span>Sign in with a private key instead of a password</span></label>
            {useKey ? (
              <label className={styles.field} htmlFor="sftp-key">Private key (PEM)
                <textarea id="sftp-key" className={styles.input} rows={4} autoComplete="off" value={f.private_key ?? ""} onChange={(e) => edit({ private_key: e.target.value })} />
              </label>
            ) : (
              <label className={styles.field} htmlFor="sftp-pw">Password
                <input id="sftp-pw" className={styles.input} type="password" autoComplete="off" required value={f.password ?? ""} placeholder={current ? "Enter it again to save changes" : ""} onChange={(e) => edit({ password: e.target.value })} />
              </label>
            )}
            <label className={styles.check}><input type="checkbox" checked={f.auto_deliver} onChange={(e) => edit({ auto_deliver: e.target.checked })} /><span>Send claims and exceptions automatically when a report completes</span></label>
            <div className={styles.actions}>
              <Button type="submit" loading={busy}>Save</Button>
              {current && <Button type="button" variant="ghost" onClick={async () => {
                try { const r = await api.testSftp(); toast({ tone: r.ok ? "good" : "bad", title: r.ok ? "Connection works" : "Connection failed", body: r.message }); }
                catch (err) { toast({ tone: "bad", title: "Test failed", body: errorText(err) }); }
              }}>Test connection</Button>}
              {current && <Button type="button" variant="ghost" onClick={async () => {
                if (!window.confirm("Remove the SFTP destination?")) return;
                try { await api.removeSftp(); setForm(null); reload(); } catch (err) { toast({ tone: "bad", title: "Not removed", body: errorText(err) }); }
              }}>Remove</Button>}
            </div>
          </form>
        ) : <p className={styles.muted}>Only owners and admins can change SFTP delivery.</p>}
      </div>
    </Panel>
  );
}

function Services({ canManage }: { canManage: boolean }) {
  const toast = useToast();
  const { data, error, loading, reload } = useApi(() => api.channels());
  if (loading && !data) return <Panel title="Services"><SkeletonRows rows={2} /></Panel>;
  if (error || !data?.services) return <ErrorState title="Service status could not be loaded" message={error ?? ""} onRetry={reload} />;
  const { ai, fx } = data.services;
  return (
    <Panel title="AI and exchange rates" icon="sparkles"
      subtitle="AI suggests column mappings (never applied without your confirmation). Exchange rates come from the ECB; conversions always state the rate date."
      actions={<StatusPill status={ai.configured ? "active" : "not_configured"} />}>
      <div className={styles.form}>
        <KeyValue items={[
          ["AI provider", ai.configured ? `${ai.provider} · ${ai.model}` : "Not configured — columns the aliases do not recognise stay unmapped for you to map"],
          ["AI region", ai.configured ? (ai.region ?? "—") : "—"],
          ["What is sent", ai.configured ? "Column headers and up to 3 masked sample shapes per column. Never cell values." : "Nothing"],
          ["ECB rates", fx.latest_rate_date ? `Latest fixing ${fx.latest_rate_date}${fx.auto_refresh ? " · refreshed automatically" : ""}` : "Not loaded yet"],
        ]} />
        {canManage && (
          <div className={styles.actions}>
            <Button type="button" variant="ghost" onClick={async () => {
              try { const r = await api.refreshFx(); reload(); toast({ tone: "good", title: "Rates loaded", body: `Latest fixing ${r.latest_rate_date ?? "—"}.` }); }
              catch (err) { toast({ tone: "bad", title: "Rates not loaded", body: errorText(err) }); }
            }}>Load ECB rates now</Button>
          </div>
        )}
      </div>
    </Panel>
  );
}

export function ChannelsSettings({ canManage }: { canManage: boolean }) {
  return (
    <>
      <InboundEmail canManage={canManage} />
      <Webhooks canManage={canManage} />
      <Sftp canManage={canManage} />
      <Services canManage={canManage} />
    </>
  );
}
