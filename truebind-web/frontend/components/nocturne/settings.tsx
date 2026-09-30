"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import QRCode from "qrcode";
import { Copy } from "@phosphor-icons/react";
import { api, ApiError } from "@/lib/api";
import type { BinderInput, InvitationCreated, OrgType, Role, SftpInput, SsoConfig, SsoConfigInput, WebhookDelivery, WebhookEvent } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { useUi } from "@/lib/ui";
import { ROLE_HELP, ROLE_LABEL } from "@/lib/auth";
import { decimalMoney } from "@/lib/findings";
import { formatDate, formatDateTime } from "@/lib/formatters";
import { ErrorState, LoadingState, Modal, StatusPill, Toggle } from "./ui";

const err = (e: unknown) => (e instanceof ApiError ? e.message : "Please try again.");

/** Styled replacement for window.confirm. */
export function useConfirm() {
  const [state, setState] = useState<{ title: string; body: string; action: string; resolve: (v: boolean) => void } | null>(null);
  const ask = useCallback((title: string, body: string, action = "Confirm") => new Promise<boolean>((resolve) => setState({ title, body, action, resolve })), []);
  const close = (v: boolean) => {
    state?.resolve(v);
    setState(null);
  };
  const el = (
    <Modal
      open={!!state}
      onClose={() => close(false)}
      title={state?.title ?? ""}
      actions={
        <>
          <button className="tb-btn" onClick={() => close(false)}>Cancel</button>
          <button className="tb-btn tb-btn-danger" data-autofocus onClick={() => close(true)}>{state?.action}</button>
        </>
      }
    >
      {state?.body}
    </Modal>
  );
  return [ask, el] as const;
}

export function Panel({ title, sub, status, actions, children }: { title: string; sub?: string; status?: React.ReactNode; actions?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="tb-card flex flex-col gap-4 p-4 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 max-w-[760px] flex-col gap-1">
          <span className="text-[16px] font-medium">{title}</span>
          {sub && <span className="text-[13px] leading-[1.55]" style={{ color: "var(--muted)" }}>{sub}</span>}
        </div>
        <div className="flex items-center gap-2">
          {status}
          {actions}
        </div>
      </div>
      {children}
    </section>
  );
}

function F({ label, id, hint, children }: { label: string; id?: string; hint?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <label className="tb-label" htmlFor={id}>{label}</label>
      {children}
      {hint && <span className="mt-1.5 block text-[12px]" style={{ color: "var(--faint)" }}>{hint}</span>}
    </div>
  );
}

function Check({ on, onChange, label, help, disabled }: { on: boolean; onChange: (v: boolean) => void; label: string; help?: string; disabled?: boolean }) {
  return (
    <label className={`flex items-start gap-3 ${disabled ? "opacity-60" : ""}`}>
      <span className="mt-0.5">{disabled ? <span className="inline-block h-[20px] w-[34px] rounded-full" style={{ background: on ? "var(--accent)" : "var(--line2)" }} /> : <Toggle on={on} onChange={onChange} label={label} />}</span>
      <span className="flex flex-col text-[13.5px]">
        <span className="font-medium">{label}</span>
        {help && <span className="text-[12.5px]" style={{ color: "var(--faint)" }}>{help}</span>}
      </span>
    </label>
  );
}

const Mono = ({ children }: { children: React.ReactNode }) => (
  <code className="break-all rounded-md px-2 py-1 text-[12.5px]" style={{ background: "var(--bg2)", boxShadow: "inset 0 0 0 1px var(--line)" }}>{children}</code>
);

function KV({ items }: { items: [string, React.ReactNode][] }) {
  return (
    <dl className="m-0 grid grid-cols-[minmax(96px,200px)_minmax(0,1fr)] [overflow-wrap:anywhere] gap-x-4 gap-y-2 text-[13px]">
      {items.map(([k, v]) => (
        <div key={k} className="contents">
          <dt style={{ color: "var(--faint)" }}>{k}</dt>
          <dd className="m-0 min-w-0">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

function Table({ head, children }: { head: string[]; children: React.ReactNode }) {
  return (
    <div className="overflow-x-auto rounded-[10px]" style={{ boxShadow: "inset 0 0 0 1px var(--line)" }}>
      <table className="w-full min-w-[560px] border-collapse text-[13px]">
        <thead>
          <tr className="text-left text-[11px] uppercase tracking-[.06em]" style={{ color: "var(--faint)" }}>
            {head.map((h, i) => <th key={i} className="px-4 py-2.5 font-medium">{h}</th>)}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}
const Tr = ({ children }: { children: React.ReactNode }) => <tr style={{ boxShadow: "0 -1px 0 var(--line)" }}>{children}</tr>;
const Td = ({ children, className = "" }: { children: React.ReactNode; className?: string }) => <td className={`px-4 py-2.5 align-top ${className}`}>{children}</td>;

/* ── Organisation ──────────────────────────────────────────────────────── */

const ORG_TYPES: { value: OrgType; label: string }[] = [
  { value: "capacity_provider", label: "Capacity provider (managing agent, carrier)" },
  { value: "mga", label: "MGA / coverholder" },
  { value: "tpa", label: "Third-party administrator" },
];

export function OrganisationSettings({ canManage }: { canManage: boolean }) {
  const { toast } = useUi();
  const { data, error, loading, reload } = useApi(() => api.getOrg());
  const [draft, setDraft] = useState<{ name: string; org_type: OrgType; require_2fa: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  if (loading && !data) return <Panel title="Organisation"><LoadingState label="Loading organisation" rows={3} /></Panel>;
  if (error || !data) return <ErrorState title="Organisation settings could not be loaded" message={error} onRetry={reload} />;
  const form = draft ?? { name: data.name, org_type: data.org_type, require_2fa: data.require_2fa };
  const dirty = form.name !== data.name || form.org_type !== data.org_type || form.require_2fa !== data.require_2fa;
  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.updateOrg(form);
      setDraft(null);
      reload();
      toast("Organisation updated · recorded in the audit trail", "ok");
    } catch (x) {
      toast(err(x), "err");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel title="Organisation" sub="Who you are in TrueBind, and the rules every member signs in under.">
      <form className="flex max-w-[720px] flex-col gap-5" onSubmit={save}>
        <div className="grid gap-4 sm:grid-cols-2">
          <F label="Name" id="org-name">
            <input id="org-name" className="tb-input" value={form.name} maxLength={200} required disabled={!canManage} onChange={(e) => setDraft({ ...form, name: e.target.value })} />
          </F>
          <F label="Organisation type" id="org-type">
            <select id="org-type" className="tb-input" value={form.org_type} disabled={!canManage} onChange={(e) => setDraft({ ...form, org_type: e.target.value as OrgType })}>
              {ORG_TYPES.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </F>
        </div>
        <Check on={form.require_2fa} disabled={!canManage} onChange={(v) => setDraft({ ...form, require_2fa: v })} label="Require two-step verification for every member" help="Members without it are asked to set it up before they can continue. Single sign-on users rely on your identity provider’s MFA. Turn it on for your own account first." />
        <span className="text-[12.5px]" style={{ color: "var(--faint)" }}>Data retention: {data.retention_days} days.</span>
        {canManage && (
          <div className="flex gap-2">
            <button type="submit" className="tb-btn tb-btn-solid" disabled={busy || !dirty}>{busy ? "Saving…" : "Save changes"}</button>
            {dirty && <button type="button" className="tb-btn tb-btn-ghost" onClick={() => setDraft(null)}>Discard</button>}
          </div>
        )}
      </form>
    </Panel>
  );
}

/* ── Members ───────────────────────────────────────────────────────────── */

const ROLES: Role[] = ["OWNER", "ADMIN", "ANALYST", "VIEWER", "SENDER"];

export function MembersSettings({ canManage, myRole, myUserId }: { canManage: boolean; myRole: string; myUserId: string }) {
  const { toast } = useUi();
  const [ask, confirmEl] = useConfirm();
  const members = useApi(() => api.listMembers());
  const invitations = useApi(() => (canManage ? api.listInvitations() : Promise.resolve([])), [canManage]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("ANALYST");
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState<InvitationCreated | null>(null);
  const assignable = myRole === "OWNER" ? ROLES : ROLES.filter((r) => r !== "OWNER");
  const link = created ? `${window.location.origin}/invite?token=${encodeURIComponent(created.accept_token)}` : "";

  const invite = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      setCreated(await api.invite(email.trim(), role));
      setEmail("");
      invitations.reload();
    } catch (x) {
      toast(`Invitation not created: ${err(x)}`, "err");
    } finally {
      setBusy(false);
    }
  };
  const changeRole = async (id: string, next: Role) => {
    try {
      await api.changeRole(id, next);
      members.reload();
      toast(`Role changed to ${ROLE_LABEL[next]} · recorded in the audit trail`, "ok");
    } catch (x) {
      toast(`Role not changed: ${err(x)}`, "err");
    }
  };
  const remove = async (id: string, who: string) => {
    if (!(await ask("Remove this member?", `Remove ${who} from the organisation? They are signed out immediately.`, "Remove"))) return;
    try {
      await api.removeMember(id);
      members.reload();
      toast(`${who} removed`, "ok");
    } catch (x) {
      toast(`Member not removed: ${err(x)}`, "err");
    }
  };
  const revoke = async (id: string) => {
    try {
      await api.revokeInvitation(id);
      invitations.reload();
      toast("Invitation revoked", "ok");
    } catch (x) {
      toast(`Invitation not revoked: ${err(x)}`, "err");
    }
  };

  return (
    <div className="flex flex-col gap-4">
      {canManage && (
        <Panel title="Invite someone" sub="Invitations expire after 7 days. Until email delivery is configured on your server, copy the link and send it yourself.">
          <form className="flex max-w-[720px] flex-col gap-3" onSubmit={invite}>
            <div className="grid gap-3 sm:grid-cols-[1fr_200px_auto] sm:items-end">
              <F label="Work email" id="inv-email">
                <input id="inv-email" className="tb-input" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="off" />
              </F>
              <F label="Role" id="inv-role">
                <select id="inv-role" className="tb-input" value={role} onChange={(e) => setRole(e.target.value as Role)}>
                  {assignable.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
                </select>
              </F>
              <button type="submit" className="tb-btn tb-btn-solid" disabled={busy}>{busy ? "Creating…" : "Create invitation"}</button>
            </div>
            <span className="text-[12.5px]" style={{ color: "var(--faint)" }}>{ROLE_HELP[role]}</span>
          </form>
        </Panel>
      )}
      <Panel title="Members" sub="Roles decide what each person can see and do; every change is audited.">
        {members.error ? (
          <ErrorState title="Members could not be loaded" message={members.error} onRetry={members.reload} />
        ) : !members.data ? (
          <LoadingState label="Loading members" rows={3} />
        ) : (
          <>
          <ul className="m-0 flex list-none flex-col p-0 sm:hidden" aria-label="Members">
            {members.data.map((m) => {
              const locked = !canManage || (m.role === "OWNER" && myRole !== "OWNER");
              return (
                <li key={m.membership_id} className="flex flex-col gap-2.5 py-3.5" style={{ boxShadow: "0 1px 0 var(--line)" }}>
                  <div className="min-w-0">
                    <div className="break-words font-medium">{m.display_name}{m.user_id === myUserId ? " (you)" : ""}</div>
                    <div className="break-all text-[12.5px]" style={{ color: "var(--faint)" }}>{m.email} · joined {formatDate(m.created_at)}</div>
                  </div>
                  <div className="flex items-center gap-2">
                    {locked ? (
                      <StatusPill tone={m.role === "OWNER" ? "med" : "muted"}>{ROLE_LABEL[m.role] ?? m.role}</StatusPill>
                    ) : (
                      <select className="tb-input flex-1" value={m.role} aria-label={`Role for ${m.email}`} onChange={(e) => void changeRole(m.membership_id, e.target.value as Role)}>
                        {assignable.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
                      </select>
                    )}
                    {canManage && !locked && <button type="button" className="tb-btn tb-btn-ghost" onClick={() => void remove(m.membership_id, m.email)}>Remove</button>}
                  </div>
                </li>
              );
            })}
          </ul>
          <div className="hidden sm:block">
          <Table head={["Person", "Role", "Joined", ""]}>
            {members.data.map((m) => {
              const locked = !canManage || (m.role === "OWNER" && myRole !== "OWNER");
              return (
                <Tr key={m.membership_id}>
                  <Td>
                    <div className="font-medium">{m.display_name}{m.user_id === myUserId ? " (you)" : ""}</div>
                    <div className="text-[12px]" style={{ color: "var(--faint)" }}>{m.email}</div>
                  </Td>
                  <Td>
                    {locked ? (
                      <StatusPill tone={m.role === "OWNER" ? "med" : "muted"}>{ROLE_LABEL[m.role] ?? m.role}</StatusPill>
                    ) : (
                      <select className="tb-input !min-h-[32px] !w-[160px] !py-1 text-[13px]" value={m.role} aria-label={`Role for ${m.email}`} onChange={(e) => void changeRole(m.membership_id, e.target.value as Role)}>
                        {assignable.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
                      </select>
                    )}
                  </Td>
                  <Td className="tnum">{formatDate(m.created_at)}</Td>
                  <Td className="text-right">{canManage && !locked && <button type="button" className="tb-btn tb-btn-ghost !px-2 !py-1 text-[12.5px]" onClick={() => void remove(m.membership_id, m.email)}>Remove</button>}</Td>
                </Tr>
              );
            })}
          </Table>
          </div>
          </>
        )}
      </Panel>
      {canManage && invitations.data && invitations.data.length > 0 && (
        <Panel title="Pending invitations">
          <Table head={["Email", "Role", "Expires", ""]}>
            {invitations.data.map((i) => (
              <Tr key={i.id}>
                <Td>{i.email}</Td>
                <Td>{ROLE_LABEL[i.role]}</Td>
                <Td className="tnum">{formatDate(i.expires_at)}</Td>
                <Td className="text-right"><button type="button" className="tb-btn tb-btn-ghost !px-2 !py-1 text-[12.5px]" onClick={() => void revoke(i.id)}>Revoke</button></Td>
              </Tr>
            ))}
          </Table>
        </Panel>
      )}
      <Modal
        open={created !== null}
        onClose={() => setCreated(null)}
        title="Invitation created"
        actions={
          <button className="tb-btn tb-btn-primary" onClick={() => { void navigator.clipboard?.writeText(link); toast("Link copied", "ok"); }}>
            <Copy />
            Copy link
          </button>
        }
      >
        <div className="flex flex-col gap-3">
          <span>Send this link to {created?.email}. It works once and expires on {created ? formatDate(created.expires_at) : ""}. It is shown only now.</span>
          <span data-testid="invite-link"><Mono>{link}</Mono></span>
        </div>
      </Modal>
      {confirmEl}
    </div>
  );
}

/* ── Security (two-step verification) ──────────────────────────────────── */

function QrCode({ value }: { value: string }) {
  const [svg, setSvg] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    QRCode.toString(value, { type: "svg", margin: 0, errorCorrectionLevel: "M" })
      .then((s) => live && setSvg(s))
      .catch(() => live && setSvg(null));
    return () => {
      live = false;
    };
  }, [value]);
  // Generated locally from our own otpauth URI (no user HTML).
  return <div className="h-[168px] w-[168px] flex-none rounded-lg bg-white p-3" role="img" aria-label="QR code for your authenticator app" dangerouslySetInnerHTML={svg ? { __html: svg } : undefined} />;
}

export function SecuritySettings({ required }: { required: boolean }) {
  const { toast } = useUi();
  const status = useApi(() => api.mfaStatus());
  const [setup, setSetup] = useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [code, setCode] = useState("");
  const [codes, setCodes] = useState<string[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (x) {
      setError(err(x));
    } finally {
      setBusy(false);
    }
  };
  if (status.error) return <ErrorState title="Security settings could not be loaded" message={status.error} onRetry={status.reload} />;
  if (!status.data) return <Panel title="Two-step verification"><LoadingState label="Loading security" rows={3} /></Panel>;
  const s = status.data;
  return (
    <Panel title="Two-step verification" sub="A code from an authenticator app (Microsoft Authenticator, Google Authenticator, 1Password…) in addition to your password." status={<StatusPill tone={s.enabled ? "ok" : "warn"}>{s.enabled ? "On" : "Off"}</StatusPill>}>
      <div className="flex max-w-[720px] flex-col gap-4">
        {required && s.setup_required && <div className="rounded-lg px-3.5 py-2.5 text-[13px]" style={{ background: "var(--warnT)", color: "var(--warn)" }}>Your organisation requires two-step verification. Set it up to continue using TrueBind.</div>}
        {error && <div className="rounded-lg px-3.5 py-2.5 text-[13px]" style={{ background: "var(--errT)", color: "var(--err)" }}>{error}</div>}
        {codes && (
          <>
            <div className="rounded-lg px-3.5 py-2.5 text-[13px]" style={{ background: "var(--okT)", color: "var(--ok)" }}>Two-step verification is on. Your other sessions were signed out. Save these recovery codes somewhere safe: each works once, and they are shown only now.</div>
            <ul className="tnum m-0 grid list-none grid-cols-2 gap-2 p-0 sm:grid-cols-4" data-testid="recovery-codes">
              {codes.map((c) => <li key={c}><Mono>{c}</Mono></li>)}
            </ul>
            <div className="flex gap-2">
              <button type="button" className="tb-btn" onClick={() => { void navigator.clipboard?.writeText(codes.join("\n")); toast("Recovery codes copied", "info"); }}><Copy />Copy codes</button>
              <button type="button" className="tb-btn tb-btn-solid" onClick={() => { setCodes(null); status.reload(); }}>I have saved them</button>
            </div>
          </>
        )}
        {!codes && !s.enabled && !setup && (
          <button type="button" className="tb-btn tb-btn-solid self-start" disabled={busy} onClick={() => void run(async () => setSetup(await api.mfaSetup()))}>{busy ? "Starting…" : "Set up two-step verification"}</button>
        )}
        {!codes && !s.enabled && setup && (
          <form
            className="flex flex-wrap gap-6"
            onSubmit={(e) => {
              e.preventDefault();
              void run(async () => {
                setCodes((await api.mfaEnable(code.replace(/\s/g, ""))).recovery_codes);
                setSetup(null);
                setCode("");
              });
            }}
          >
            <QrCode value={setup.otpauth_uri} />
            <div className="flex min-w-[260px] flex-1 flex-col gap-3">
              <span className="text-[13px]" style={{ color: "var(--muted)" }}>1. Scan the code with your authenticator app, or enter this key:</span>
              <span data-testid="totp-secret"><Mono>{setup.secret}</Mono></span>
              <F label="2. Enter the 6-digit code it shows" id="mfa-code">
                <input id="mfa-code" className="tb-input tnum !w-[200px]" value={code} onChange={(e) => setCode(e.target.value)} inputMode="numeric" autoComplete="one-time-code" required pattern="[0-9 ]{6,8}" />
              </F>
              <div className="flex gap-2">
                <button type="submit" className="tb-btn tb-btn-solid" disabled={busy}>{busy ? "Checking…" : "Turn on"}</button>
                <button type="button" className="tb-btn tb-btn-ghost" onClick={() => setSetup(null)}>Cancel</button>
              </div>
            </div>
          </form>
        )}
        {!codes &&
          s.enabled &&
          (s.required ? (
            <span className="text-[13px]" style={{ color: "var(--muted)" }}>Your organisation requires two-step verification, so it can’t be turned off.</span>
          ) : (
            <form
              className="flex flex-wrap items-end gap-3"
              onSubmit={(e) => {
                e.preventDefault();
                void run(async () => {
                  await api.mfaDisable(code.replace(/\s/g, ""));
                  setCode("");
                  status.reload();
                  toast("Two-step verification is off", "info");
                });
              }}
            >
              <F label="To turn it off, enter a current code or a recovery code" id="mfa-off">
                <input id="mfa-off" className="tb-input !w-[260px]" value={code} onChange={(e) => setCode(e.target.value)} required autoComplete="one-time-code" />
              </F>
              <button type="submit" className="tb-btn" disabled={busy}>{busy ? "Turning off…" : "Turn off"}</button>
            </form>
          ))}
      </div>
    </Panel>
  );
}

/* ── Single sign-on ────────────────────────────────────────────────────── */

function toInput(c: SsoConfig): SsoConfigInput {
  return {
    issuer: c.issuer ?? "",
    client_id: c.client_id ?? "",
    client_secret: null,
    token_auth_method: c.token_auth_method ?? "client_secret_post",
    domains: c.domains,
    jit_provisioning: c.jit_provisioning,
    default_role: (c.default_role ?? "VIEWER") as Role,
    enabled: c.configured ? c.enabled : true,
  };
}

export function SsoSettings({ canManage }: { canManage: boolean }) {
  const { toast } = useUi();
  const [ask, confirmEl] = useConfirm();
  const { data, error, loading, reload } = useApi(() => api.getSso());
  const [form, setForm] = useState<SsoConfigInput | null>(null);
  const [domains, setDomains] = useState("");
  const [busy, setBusy] = useState(false);
  if (loading && !data) return <Panel title="Single sign-on"><LoadingState label="Loading single sign-on" rows={4} /></Panel>;
  if (error || !data) return <ErrorState title="Single sign-on settings could not be loaded" message={error} onRetry={reload} />;
  const f = form ?? toInput(data);
  const domainText = form ? domains : data.domains.join(", ");
  const edit = (patch: Partial<SsoConfigInput>) => {
    if (!form) setDomains(domainText);
    setForm({ ...f, ...patch });
  };
  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const list = domainText.split(/[\s,;]+/).map((d) => d.trim()).filter(Boolean);
      await api.saveSso({ ...f, domains: list, client_secret: f.client_secret || null });
      setForm(null);
      reload();
      toast("Single sign-on saved · people with these email domains can now use it", "ok");
    } catch (x) {
      toast(`Not saved: ${err(x)}`, "err");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel title="Single sign-on (OIDC)" sub="Microsoft Entra ID, WorkOS or any OpenID Connect provider. People sign in with their work email and are sent to your identity provider." status={<StatusPill tone={data.configured && data.enabled ? "ok" : "muted"}>{data.configured ? (data.enabled ? "Active" : "Disabled") : "Not configured"}</StatusPill>}>
      <div className="flex max-w-[760px] flex-col gap-4">
        <KV items={[["Redirect (callback) URL", <Mono key="cb">{data.callback_url}</Mono>]]} />
        <span className="text-[12.5px]" style={{ color: "var(--faint)" }}>Register this URL in your identity provider and grant the <code>openid email profile</code> scopes.</span>
        {canManage ? (
          <form className="flex flex-col gap-4" onSubmit={save}>
            <F label="Issuer URL" id="sso-issuer">
              <input id="sso-issuer" className="tb-input" value={f.issuer} required placeholder="https://login.microsoftonline.com/<tenant-id>/v2.0" onChange={(e) => edit({ issuer: e.target.value })} />
            </F>
            <div className="grid gap-4 sm:grid-cols-2">
              <F label="Client ID" id="sso-cid">
                <input id="sso-cid" className="tb-input" value={f.client_id} required onChange={(e) => edit({ client_id: e.target.value })} />
              </F>
              <F label="Client secret" id="sso-secret">
                <input id="sso-secret" className="tb-input" type="password" value={f.client_secret ?? ""} autoComplete="off" placeholder={data.has_client_secret ? "Saved — leave blank to keep" : ""} onChange={(e) => edit({ client_secret: e.target.value })} />
              </F>
            </div>
            <F label="Email domains" id="sso-domains" hint="Only domains your organisation owns. Each domain can belong to one organisation.">
              <input id="sso-domains" className="tb-input" value={domainText} required placeholder="example.com, example.co.uk" onChange={(e) => { if (!form) setForm(f); setDomains(e.target.value); }} />
            </F>
            <div className="grid gap-4 sm:grid-cols-2">
              <F label="Role for new people" id="sso-role">
                <select id="sso-role" className="tb-input" value={f.default_role} onChange={(e) => edit({ default_role: e.target.value as Role })}>
                  {(["VIEWER", "ANALYST", "ADMIN", "SENDER"] as Role[]).map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
                </select>
              </F>
              <F label="Client authentication" id="sso-auth">
                <select id="sso-auth" className="tb-input" value={f.token_auth_method} onChange={(e) => edit({ token_auth_method: e.target.value })}>
                  <option value="client_secret_post">client_secret_post</option>
                  <option value="client_secret_basic">client_secret_basic</option>
                </select>
              </F>
            </div>
            <Check on={f.jit_provisioning} onChange={(v) => edit({ jit_provisioning: v })} label="Create accounts on first sign-in" help="Off: only people you have invited can sign in with SSO. Existing accounts from other organisations are never added automatically." />
            <Check on={f.enabled} onChange={(v) => edit({ enabled: v })} label="Enabled" />
            <div className="flex flex-wrap gap-2">
              <button type="submit" className="tb-btn tb-btn-solid" disabled={busy || !form}>{busy ? "Saving…" : "Save"}</button>
              {form && <button type="button" className="tb-btn tb-btn-ghost" onClick={() => setForm(null)}>Discard</button>}
              {data.configured && !form && (
                <button
                  type="button"
                  className="tb-btn tb-btn-danger"
                  onClick={async () => {
                    if (!(await ask("Remove single sign-on?", "Members will need a password or an invitation to sign in.", "Remove"))) return;
                    try {
                      await api.removeSso();
                      reload();
                      toast("Single sign-on removed", "ok");
                    } catch (x) {
                      toast(`Not removed: ${err(x)}`, "err");
                    }
                  }}
                >
                  Remove
                </button>
              )}
            </div>
          </form>
        ) : (
          <span className="text-[13px]" style={{ color: "var(--muted)" }}>Only owners and admins can change single sign-on.</span>
        )}
      </div>
      {confirmEl}
    </Panel>
  );
}

/* ── Channels ──────────────────────────────────────────────────────────── */

const EVENTS: { value: WebhookEvent; label: string }[] = [
  { value: "report.completed", label: "Report completed" },
  { value: "report.failed", label: "Report failed" },
  { value: "report.waiting_for_review", label: "Mapping ready for review" },
];
const chTone = (s: string) => (s === "active" ? ({ tone: "ok", label: "Live" } as const) : s === "not_set_up" ? ({ tone: "med", label: "Ready to set up" } as const) : s === "planned" ? ({ tone: "muted", label: "Planned" } as const) : ({ tone: "warn", label: "Not configured on the server" } as const));

function InboundEmail({ canManage }: { canManage: boolean }) {
  const { toast } = useUi();
  const [ask, confirmEl] = useConfirm();
  const { data, error, loading, reload } = useApi(() => api.getInbound());
  const [busy, setBusy] = useState(false);
  if (loading && !data) return <Panel title="Email intake"><LoadingState label="Loading" rows={2} /></Panel>;
  if (error || !data) return <ErrorState title="Email intake could not be loaded" message={error} onRetry={reload} />;
  const st = chTone(!data.configured ? "not_configured" : data.address ? "active" : "not_set_up");
  const rotate = async () => {
    if (data.address && !(await ask("Create a new address?", "The current address stops accepting mail immediately.", "Replace address"))) return;
    setBusy(true);
    try {
      await api.rotateInbound();
      reload();
      toast("Intake address ready · senders can email bordereaux to it", "ok");
    } catch (x) {
      toast(`Not changed: ${err(x)}`, "err");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel title="Email intake" sub="Bordereaux emailed to this address are checked and ingested like uploads. Each attachment becomes a report." status={<StatusPill tone={st.tone}>{st.label}</StatusPill>}>
      {!data.configured && <span className="text-[13px]" style={{ color: "var(--muted)" }}>Email intake isn’t configured on this server yet (it needs an inbound email domain and a Postmark or Amazon SES connection).</span>}
      {data.configured && (data.address ? <KV items={[["Intake address", <Mono key="a">{data.address}</Mono>]]} /> : <span className="text-[13px]" style={{ color: "var(--muted)" }}>No address yet.</span>)}
      {data.configured && canManage && (
        <button type="button" className="tb-btn tb-btn-primary self-start" disabled={busy} onClick={() => void rotate()}>{busy ? "Working…" : data.address ? "Replace address" : "Create address"}</button>
      )}
      {confirmEl}
    </Panel>
  );
}

function Deliveries({ endpointId, canManage }: { endpointId: string; canManage: boolean }) {
  const { toast } = useUi();
  const { data, error, loading, reload } = useApi(() => api.webhookDeliveries(endpointId));
  if (loading && !data) return <LoadingState label="Loading deliveries" rows={2} />;
  if (error || !data) return <span className="text-[12.5px]" style={{ color: "var(--err)" }}>Deliveries could not be loaded.</span>;
  if (!data.length) return <span className="text-[12.5px]" style={{ color: "var(--faint)" }}>No deliveries yet.</span>;
  const tone = (d: WebhookDelivery) => (d.status === "DELIVERED" ? "ok" : d.status === "PENDING" ? "muted" : "err");
  return (
    <Table head={["Event", "Status", "Attempts", "When", ""]}>
      {data.slice(0, 10).map((d) => (
        <Tr key={d.id}>
          <Td>{d.event_type}</Td>
          <Td>
            <StatusPill tone={tone(d)}>{d.status.toLowerCase()}</StatusPill>
            {d.last_error && <div className="mt-1 text-[12px]" style={{ color: "var(--muted)" }}>{d.last_error}</div>}
          </Td>
          <Td className="tnum">{d.attempts}</Td>
          <Td className="tnum">{formatDateTime(d.created_at)}</Td>
          <Td className="text-right">
            {canManage && d.status !== "PENDING" && (
              <button
                type="button"
                className="tb-btn tb-btn-ghost !px-2 !py-1 text-[12.5px]"
                onClick={async () => {
                  try {
                    await api.replayWebhook(d.id);
                    reload();
                    toast("Queued to send again", "ok");
                  } catch (x) {
                    toast(`Not queued: ${err(x)}`, "err");
                  }
                }}
              >
                Send again
              </button>
            )}
          </Td>
        </Tr>
      ))}
    </Table>
  );
}

function Webhooks({ canManage }: { canManage: boolean }) {
  const { toast } = useUi();
  const [ask, confirmEl] = useConfirm();
  const { data, error, loading, reload } = useApi(() => api.listWebhooks());
  const [url, setUrl] = useState("");
  const [events, setEvents] = useState<WebhookEvent[]>(["report.completed"]);
  const [secret, setSecret] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  if (loading && !data) return <Panel title="Webhooks"><LoadingState label="Loading webhooks" rows={3} /></Panel>;
  if (error || !data) return <ErrorState title="Webhooks could not be loaded" message={error} onRetry={reload} />;
  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const created = await api.createWebhook(url.trim(), events);
      setSecret(created.secret);
      setUrl("");
      reload();
    } catch (x) {
      toast(`Endpoint not added: ${err(x)}`, "err");
    } finally {
      setBusy(false);
    }
  };
  const st = chTone(data.length ? "active" : "not_set_up");
  return (
    <Panel title="Webhooks" sub="Report events are posted to your systems, signed (webhook-id, webhook-timestamp, webhook-signature: HMAC-SHA256). Failed deliveries are retried with backoff." status={<StatusPill tone={st.tone}>{st.label}</StatusPill>}>
      {secret && (
        <div role="status" className="flex flex-col gap-2 rounded-lg px-3.5 py-3" style={{ background: "var(--warnT)" }}>
          <span className="text-[13px] font-medium" style={{ color: "var(--warn)" }}>Signing secret — copy it now, it won’t be shown again.</span>
          <Mono>{secret}</Mono>
          <div className="flex gap-2">
            <button type="button" className="tb-btn !py-1.5 text-[12.5px]" onClick={() => { void navigator.clipboard?.writeText(secret); toast("Secret copied", "info"); }}><Copy />Copy</button>
            <button type="button" className="tb-btn tb-btn-ghost !py-1.5 text-[12.5px]" onClick={() => setSecret(null)}>I have stored it</button>
          </div>
        </div>
      )}
      {data.length === 0 && <span className="text-[13px]" style={{ color: "var(--faint)" }}>No endpoints yet.</span>}
      {data.map((ep) => (
        <div key={ep.id} className="flex flex-col gap-3 rounded-[10px] p-4" style={{ boxShadow: "inset 0 0 0 1px var(--line)" }}>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="flex min-w-0 flex-col gap-1">
              <code className="break-all text-[13px]">{ep.url}</code>
              <span className="text-[12px]" style={{ color: "var(--faint)" }}>{ep.events.join(", ")}</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              <button type="button" className="tb-btn tb-btn-ghost !px-2 !py-1 text-[12.5px]" onClick={() => setOpen(open === ep.id ? null : ep.id)} aria-expanded={open === ep.id}>Deliveries</button>
              {canManage && (
                <button
                  type="button"
                  className="tb-btn tb-btn-ghost !px-2 !py-1 text-[12.5px]"
                  onClick={async () => {
                    try {
                      await api.testWebhook(ep.id);
                      toast("Test event queued · sent within a few seconds", "ok");
                    } catch (x) {
                      toast(`Not queued: ${err(x)}`, "err");
                    }
                  }}
                >
                  Send test
                </button>
              )}
              {canManage && (
                <button
                  type="button"
                  className="tb-btn tb-btn-ghost !px-2 !py-1 text-[12.5px]"
                  onClick={async () => {
                    if (!(await ask("Remove this endpoint?", "It stops receiving events.", "Remove"))) return;
                    try {
                      await api.deleteWebhook(ep.id);
                      reload();
                      toast("Endpoint removed", "ok");
                    } catch (x) {
                      toast(`Not removed: ${err(x)}`, "err");
                    }
                  }}
                >
                  Remove
                </button>
              )}
            </div>
          </div>
          {open === ep.id && <Deliveries endpointId={ep.id} canManage={canManage} />}
        </div>
      ))}
      {canManage ? (
        <form className="flex max-w-[720px] flex-col gap-3" onSubmit={add}>
          <F label="Endpoint URL" id="hook-url" hint="Must be https and reachable on the public internet.">
            <input id="hook-url" className="tb-input" type="url" required value={url} placeholder="https://example.com/truebind-events" onChange={(e) => setUrl(e.target.value)} />
          </F>
          <fieldset className="m-0 flex flex-wrap gap-4 border-0 p-0">
            <legend className="tb-label">Events</legend>
            {EVENTS.map((ev) => (
              <label key={ev.value} className="flex cursor-pointer items-center gap-2 text-[13.5px]">
                <input type="checkbox" className="h-4 w-4 accent-[var(--accent)]" checked={events.includes(ev.value)} onChange={(e) => setEvents(e.target.checked ? [...events, ev.value] : events.filter((x) => x !== ev.value))} />
                {ev.label}
              </label>
            ))}
          </fieldset>
          <button type="submit" className="tb-btn tb-btn-primary self-start" disabled={busy || !url || events.length === 0}>{busy ? "Adding…" : "Add endpoint"}</button>
        </form>
      ) : (
        <span className="text-[13px]" style={{ color: "var(--muted)" }}>Only owners and admins can change webhooks.</span>
      )}
      {confirmEl}
    </Panel>
  );
}

const EMPTY_SFTP: SftpInput = { host: "", port: 22, username: "", password: "", private_key: null, host_key_fingerprint: "", remote_dir: "/", auto_deliver: false, enabled: true };

function Sftp({ canManage }: { canManage: boolean }) {
  const { toast } = useUi();
  const [ask, confirmEl] = useConfirm();
  const { data, error, loading, reload } = useApi(() => api.getSftp());
  const [form, setForm] = useState<SftpInput | null>(null);
  const [useKey, setUseKey] = useState(false);
  const [busy, setBusy] = useState(false);
  if (loading && data === null && !error) return <Panel title="SFTP delivery"><LoadingState label="Loading SFTP" rows={3} /></Panel>;
  if (error) return <ErrorState title="SFTP settings could not be loaded" message={error} onRetry={reload} />;
  const current = data ?? null;
  const f = form ?? (current ? { ...EMPTY_SFTP, ...current, password: "", private_key: null } : EMPTY_SFTP);
  const edit = (patch: Partial<SftpInput>) => setForm({ ...f, ...patch });
  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.saveSftp({ ...f, password: useKey ? null : f.password || null, private_key: useKey ? f.private_key || null : null });
      setForm(null);
      reload();
      toast("SFTP destination saved · use Test connection to check it", "ok");
    } catch (x) {
      toast(`Not saved: ${err(x)}`, "err");
    } finally {
      setBusy(false);
    }
  };
  const st = chTone(current?.enabled ? "active" : "not_set_up");
  return (
    <Panel title="SFTP delivery" sub="Outputs are written to your partner’s SFTP server. The server’s host key is pinned: if it changes, nothing is sent." status={<StatusPill tone={st.tone}>{st.label}</StatusPill>}>
      {current && (
        <KV
          items={[
            ["Server", `${current.username}@${current.host}:${current.port}`],
            ["Folder", current.remote_dir],
            ["Host key", <Mono key="fp">{current.host_key_fingerprint}</Mono>],
            ["Sign-in", current.auth === "private_key" ? "Private key (stored encrypted)" : "Password (stored encrypted)"],
            ["Automatic", current.auto_deliver ? "Claims and exceptions sent when a report completes" : "Off — send from a report"],
          ]}
        />
      )}
      {canManage ? (
        <form className="flex max-w-[760px] flex-col gap-4" onSubmit={save}>
          <div className="grid gap-4 sm:grid-cols-[1fr_120px]">
            <F label="Host" id="sftp-host"><input id="sftp-host" className="tb-input" required value={f.host} onChange={(e) => edit({ host: e.target.value })} /></F>
            <F label="Port" id="sftp-port"><input id="sftp-port" className="tb-input tnum" type="number" min={1} max={65535} required value={f.port} onChange={(e) => edit({ port: Number(e.target.value) })} /></F>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <F label="Username" id="sftp-user"><input id="sftp-user" className="tb-input" required value={f.username} onChange={(e) => edit({ username: e.target.value })} /></F>
            <F label="Folder" id="sftp-dir"><input id="sftp-dir" className="tb-input" required value={f.remote_dir} onChange={(e) => edit({ remote_dir: e.target.value })} /></F>
          </div>
          <F label="Host key fingerprint" id="sftp-fp" hint={<>Ask your partner, or run <code>ssh-keyscan host | ssh-keygen -lf -</code> and check it with them.</>}>
            <input id="sftp-fp" className="tb-input" required value={f.host_key_fingerprint} placeholder="SHA256:…" onChange={(e) => edit({ host_key_fingerprint: e.target.value })} />
          </F>
          <Check on={useKey} onChange={setUseKey} label="Sign in with a private key instead of a password" />
          {useKey ? (
            <F label="Private key (PEM)" id="sftp-key"><textarea id="sftp-key" className="tb-input min-h-[96px]" autoComplete="off" value={f.private_key ?? ""} onChange={(e) => edit({ private_key: e.target.value })} /></F>
          ) : (
            <F label="Password" id="sftp-pw"><input id="sftp-pw" className="tb-input" type="password" autoComplete="off" required value={f.password ?? ""} placeholder={current ? "Enter it again to save changes" : ""} onChange={(e) => edit({ password: e.target.value })} /></F>
          )}
          <Check on={f.auto_deliver} onChange={(v) => edit({ auto_deliver: v })} label="Send claims and exceptions automatically when a report completes" />
          <div className="flex flex-wrap gap-2">
            <button type="submit" className="tb-btn tb-btn-solid" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
            {current && (
              <button
                type="button"
                className="tb-btn"
                onClick={async () => {
                  try {
                    const r = await api.testSftp();
                    toast(`${r.ok ? "Connection works" : "Connection failed"} · ${r.message}`, r.ok ? "ok" : "err");
                  } catch (x) {
                    toast(`Test failed: ${err(x)}`, "err");
                  }
                }}
              >
                Test connection
              </button>
            )}
            {current && (
              <button
                type="button"
                className="tb-btn tb-btn-danger"
                onClick={async () => {
                  if (!(await ask("Remove the SFTP destination?", "Outputs will no longer be sent to this server.", "Remove"))) return;
                  try {
                    await api.removeSftp();
                    setForm(null);
                    reload();
                    toast("SFTP destination removed", "ok");
                  } catch (x) {
                    toast(`Not removed: ${err(x)}`, "err");
                  }
                }}
              >
                Remove
              </button>
            )}
          </div>
        </form>
      ) : (
        <span className="text-[13px]" style={{ color: "var(--muted)" }}>Only owners and admins can change SFTP delivery.</span>
      )}
      {confirmEl}
    </Panel>
  );
}

function Services({ canManage }: { canManage: boolean }) {
  const { toast } = useUi();
  const { data, error, loading, reload } = useApi(() => api.channels());
  if (loading && !data) return <Panel title="AI and exchange rates"><LoadingState label="Loading services" rows={2} /></Panel>;
  if (error || !data?.services) return <ErrorState title="Service status could not be loaded" message={error} onRetry={reload} />;
  const { ai, fx } = data.services;
  const st = chTone(ai.configured ? "active" : "not_configured");
  return (
    <Panel title="AI and exchange rates" sub="AI suggests column mappings (never applied without your confirmation). Exchange rates come from the ECB; conversions always state the rate date." status={<StatusPill tone={st.tone}>{ai.configured ? "AI live" : "AI not configured"}</StatusPill>}>
      <KV
        items={[
          ["AI provider", ai.configured ? `${ai.provider} · ${ai.model}` : "Not configured — columns the alias rules don’t recognise stay unmapped for you to map"],
          ["AI region", ai.configured ? ai.region ?? "—" : "—"],
          ["What is sent", ai.configured ? "Column headers and up to 3 masked sample shapes per column. Never cell values." : "Nothing"],
          ["ECB rates", fx.latest_rate_date ? `Latest fixing ${fx.latest_rate_date}${fx.auto_refresh ? " · refreshed automatically" : ""}` : "Not loaded yet"],
        ]}
      />
      {canManage && (
        <button
          type="button"
          className="tb-btn self-start"
          onClick={async () => {
            try {
              const r = await api.refreshFx();
              reload();
              toast(`Rates loaded · latest fixing ${r.latest_rate_date ?? "—"}`, "ok");
            } catch (x) {
              toast(`Rates not loaded: ${err(x)}`, "err");
            }
          }}
        >
          Load ECB rates now
        </button>
      )}
    </Panel>
  );
}

export function ChannelsSettings({ canManage }: { canManage: boolean }) {
  return (
    <div className="flex flex-col gap-4">
      <InboundEmail canManage={canManage} />
      <Webhooks canManage={canManage} />
      <Sftp canManage={canManage} />
      <Services canManage={canManage} />
    </div>
  );
}

/* ── Binders ───────────────────────────────────────────────────────────── */

const EMPTY_BINDER: BinderInput = { name: "", umr: null, coverholder: null, inception_date: "", expiry_date: "", currencies: [], limit_currency: "GBP", claims_authority: null, aggregate_limit: null };

export function BindersSettings({ canManage }: { canManage: boolean }) {
  const { toast } = useUi();
  const [ask, confirmEl] = useConfirm();
  const { data, error, loading, reload } = useApi(() => api.listBinders());
  const [f, setF] = useState<BinderInput>(EMPTY_BINDER);
  const [ccys, setCcys] = useState("");
  const [busy, setBusy] = useState(false);
  if (loading && !data) return <Panel title="Binders"><LoadingState label="Loading binders" rows={3} /></Panel>;
  if (error || !data) return <ErrorState title="Binders could not be loaded" message={error} onRetry={reload} />;
  const edit = (patch: Partial<BinderInput>) => setF({ ...f, ...patch });
  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.createBinder({ ...f, currencies: ccys.split(/[\s,]+/).filter(Boolean), claims_authority: f.claims_authority || null, aggregate_limit: f.aggregate_limit || null, umr: f.umr || null, coverholder: f.coverholder || null });
      setF(EMPTY_BINDER);
      setCcys("");
      reload();
      toast("Binder added · assign it to a report in the report’s Checks section", "ok");
    } catch (x) {
      toast(`Binder not added: ${err(x)}`, "err");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel title="Binders" sub="The binding authorities your bordereaux are checked against: period, permitted currencies, claims settlement authority and aggregate limit. Rules a binder doesn’t set are reported as not assessed.">
      {data.length === 0 ? (
        <span className="text-[13px]" style={{ color: "var(--faint)" }}>No binders yet.</span>
      ) : (
        <Table head={["Binder", "Period", "Currencies", "Authority", "Aggregate", ""]}>
          {data.map((b) => (
            <Tr key={b.id}>
              <Td>
                <div className="font-medium">{b.name}</div>
                <div className="text-[12px]" style={{ color: "var(--faint)" }}>{[b.umr, b.coverholder].filter(Boolean).join(" · ") || "—"}</div>
              </Td>
              <Td className="tnum">{b.inception_date} to {b.expiry_date}</Td>
              <Td>{b.currencies.join(", ") || "Not set"}</Td>
              <Td className="tnum">{b.claims_authority ? decimalMoney(b.claims_authority, b.limit_currency) : "Not set"}</Td>
              <Td className="tnum">{b.aggregate_limit ? decimalMoney(b.aggregate_limit, b.limit_currency) : "Not set"}</Td>
              <Td className="text-right">
                {canManage && (
                  <button
                    type="button"
                    className="tb-btn tb-btn-ghost !px-2 !py-1 text-[12.5px]"
                    onClick={async () => {
                      if (!(await ask(`Remove binder “${b.name}”?`, "Reports assigned to it will no longer be checked against it.", "Remove"))) return;
                      try {
                        await api.deleteBinder(b.id);
                        reload();
                        toast("Binder removed", "ok");
                      } catch (x) {
                        toast(`Not removed: ${err(x)}`, "err");
                      }
                    }}
                  >
                    Remove
                  </button>
                )}
              </Td>
            </Tr>
          ))}
        </Table>
      )}
      {canManage ? (
        <form className="grid max-w-[760px] gap-4 sm:grid-cols-2" onSubmit={add} aria-label="Add a binder">
          <span className="text-[14px] font-medium sm:col-span-2">Add a binder</span>
          <F label="Name" id="b-name"><input id="b-name" className="tb-input" required maxLength={200} value={f.name} onChange={(e) => edit({ name: e.target.value })} /></F>
          <F label="UMR (optional)" id="b-umr"><input id="b-umr" className="tb-input" maxLength={64} value={f.umr ?? ""} onChange={(e) => edit({ umr: e.target.value })} /></F>
          <div className="sm:col-span-2"><F label="Coverholder (optional)" id="b-ch"><input id="b-ch" className="tb-input" maxLength={200} value={f.coverholder ?? ""} onChange={(e) => edit({ coverholder: e.target.value })} /></F></div>
          <F label="Inception date" id="b-inc"><input id="b-inc" type="date" className="tb-input" required value={f.inception_date} onChange={(e) => edit({ inception_date: e.target.value })} /></F>
          <F label="Expiry date (inclusive)" id="b-exp"><input id="b-exp" type="date" className="tb-input" required value={f.expiry_date} onChange={(e) => edit({ expiry_date: e.target.value })} /></F>
          <div className="sm:col-span-2"><F label="Permitted settlement currencies" id="b-ccys" hint="ISO 4217 codes separated by commas. Leave empty to skip the currency rule."><input id="b-ccys" className="tb-input" value={ccys} placeholder="GBP, EUR" onChange={(e) => setCcys(e.target.value)} /></F></div>
          <F label="Limit currency" id="b-lccy"><input id="b-lccy" className="tb-input" required maxLength={3} value={f.limit_currency} onChange={(e) => edit({ limit_currency: e.target.value.toUpperCase() })} /></F>
          <F label="Claims settlement authority (per claim, optional)" id="b-auth"><input id="b-auth" className="tb-input tnum" inputMode="decimal" pattern="\d+(\.\d{1,2})?" value={f.claims_authority ?? ""} onChange={(e) => edit({ claims_authority: e.target.value })} /></F>
          <div className="sm:col-span-2"><F label="Aggregate limit (indemnity paid across the report, optional)" id="b-agg"><input id="b-agg" className="tb-input tnum" inputMode="decimal" pattern="\d+(\.\d{1,2})?" value={f.aggregate_limit ?? ""} onChange={(e) => edit({ aggregate_limit: e.target.value })} /></F></div>
          <button type="submit" className="tb-btn tb-btn-solid self-start" disabled={busy}>{busy ? "Adding…" : "Add binder"}</button>
        </form>
      ) : (
        <span className="text-[13px]" style={{ color: "var(--muted)" }}>Only people who can edit data can add binders.</span>
      )}
      {confirmEl}
    </Panel>
  );
}

/* ── Sanctions lists ───────────────────────────────────────────────────── */

const SOURCE_LABEL: Record<string, string> = { OFSI: "UK OFSI consolidated list", OFAC: "US OFAC SDN list", EU: "EU financial sanctions file", UN: "UN Security Council consolidated list", CUSTOM: "Own watch list" };

export function SanctionsSettings({ canManage }: { canManage: boolean }) {
  const { toast } = useUi();
  const [ask, confirmEl] = useConfirm();
  const { data, error, loading, reload } = useApi(() => api.listSanctionsLists());
  const [name, setName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);
  if (loading && !data) return <Panel title="Sanctions lists"><LoadingState label="Loading lists" rows={3} /></Panel>;
  if (error || !data) return <ErrorState title="Sanctions lists could not be loaded" message={error} onRetry={reload} />;
  const load = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    try {
      const loaded = await api.loadSanctionsList(name.trim(), file);
      setName("");
      setFile(null);
      formRef.current?.reset();
      reload();
      toast(`List loaded · ${loaded.entry_count.toLocaleString("en-GB")} names. Run the sanctions check again on a report to screen it.`, "ok");
    } catch (x) {
      toast(`List not loaded: ${err(x)}`, "err");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel title="Sanctions lists" sub="Insured names are screened against every list loaded here. A match is a potential match for a person to review — never a verdict. Download the current official lists from their publishers and load them here; the format is recognised from the file.">
      {data.length === 0 ? (
        <span className="text-[13px]" style={{ color: "var(--warn)" }}>No list loaded yet, so sanctions screening reports “not assessed” on every report.</span>
      ) : (
        <Table head={["List", "Names", "Loaded", "SHA-256", ""]}>
          {data.map((l) => (
            <Tr key={l.id}>
              <Td>
                <div className="font-medium">{l.name}</div>
                <div className="text-[12px]" style={{ color: "var(--faint)" }}>{SOURCE_LABEL[l.source] ?? l.source} · {l.file_name}</div>
              </Td>
              <Td className="tnum">{l.entry_count.toLocaleString("en-GB")}</Td>
              <Td className="tnum">
                <div>{formatDateTime(l.uploaded_at)}</div>
                <div className="text-[12px]" style={{ color: "var(--faint)" }}>{l.uploaded_by}</div>
              </Td>
              <Td><code title={l.sha256}>{l.sha256.slice(0, 12)}…</code></Td>
              <Td className="text-right">
                {canManage && (
                  <button
                    type="button"
                    className="tb-btn tb-btn-ghost !px-2 !py-1 text-[12.5px]"
                    onClick={async () => {
                      if (!(await ask(`Remove “${l.name}”?`, "Reports screened later won’t be checked against it.", "Remove"))) return;
                      try {
                        await api.deleteSanctionsList(l.id);
                        reload();
                        toast("List removed", "ok");
                      } catch (x) {
                        toast(`Not removed: ${err(x)}`, "err");
                      }
                    }}
                  >
                    Remove
                  </button>
                )}
              </Td>
            </Tr>
          ))}
        </Table>
      )}
      {canManage ? (
        <form ref={formRef} className="flex max-w-[720px] flex-col gap-4" onSubmit={load} aria-label="Load a sanctions list">
          <span className="text-[14px] font-medium">Load a sanctions list</span>
          <F label="List name" id="sl-name"><input id="sl-name" className="tb-input" required maxLength={200} value={name} placeholder="OFSI consolidated list, 1 September" onChange={(e) => setName(e.target.value)} /></F>
          <F label="List file" id="sl-file" hint="UK OFSI CSV, US OFAC sdn.csv, EU sanctions CSV, UN consolidated XML, or a CSV with a “name” column. Up to 50 MB.">
            <input id="sl-file" className="tb-input" type="file" required accept=".csv,.xml,text/csv,application/xml,text/xml" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </F>
          <button type="submit" className="tb-btn tb-btn-solid self-start" disabled={busy || !file || !name.trim()}>{busy ? "Loading…" : "Load list"}</button>
        </form>
      ) : (
        <span className="text-[13px]" style={{ color: "var(--muted)" }}>Only people who can edit data can load lists.</span>
      )}
      {confirmEl}
    </Panel>
  );
}

/* ── Billing ───────────────────────────────────────────────────────────── */

const MODULE_LABEL: Record<string, string> = { binder: "Binder compliance", leakage: "Leakage & overpayment", sanctions: "Sanctions screening" };
const limit = (n: number | null, unit: string) => (n == null ? `Unlimited${unit ? ` ${unit}` : ""}` : `${n.toLocaleString("en-GB")}${unit ? ` ${unit}` : ""}`);

export function BillingSettings() {
  const { toast } = useUi();
  const { data, error, loading, reload } = useApi(() => api.getBilling());
  const [busy, setBusy] = useState<string | null>(null);
  if (loading && !data) return <Panel title="Billing"><LoadingState label="Loading billing" rows={3} /></Panel>;
  if (error || !data) return <ErrorState title="Billing could not be loaded" message={error} onRetry={reload} />;
  const go = async (kind: "checkout" | "portal", plan?: string) => {
    setBusy(plan ?? kind);
    try {
      const { url } = kind === "checkout" ? await api.billingCheckout(plan!) : await api.billingPortal();
      window.location.href = url;
    } catch (x) {
      toast(`Could not open billing: ${err(x)}`, "err");
      setBusy(null);
    }
  };
  if (!data.enforced)
    return (
      <Panel title="Billing" status={<StatusPill tone="muted">Not enforced</StatusPill>}>
        <span className="text-[13px]" style={{ color: "var(--muted)" }}>Billing isn’t enforced on this server: every check module is available and nothing is limited.</span>
      </Panel>
    );
  return (
    <Panel title="Billing" sub="Subscriptions are handled by Stripe; card and invoice details never reach TrueBind." actions={data.customer ? <button type="button" className="tb-btn" disabled={busy === "portal"} onClick={() => void go("portal")}>{busy === "portal" ? "Opening…" : "Manage billing"}</button> : undefined}>
      <KV
        items={[
          ["Plan", data.plan ? <b key="p" className="font-medium">{data.plans.find((p) => p.name === data.plan)?.label ?? data.plan}</b> : "No active plan"],
          ["Status", data.status ? <StatusPill key="s" tone={["active", "trialing"].includes(data.status) ? "ok" : "warn"}>{data.status}</StatusPill> : "—"],
          ["Renews", data.period_end ? formatDate(data.period_end) : "—"],
          ["Rows processed this month", `${data.rows_this_month.toLocaleString("en-GB")} of ${limit(data.monthly_rows, "rows")}`],
          ["Seats", `${data.seats_used} of ${limit(data.seats, "seats")}`],
          ["Check modules", data.modules && data.modules.length ? data.modules.map((m) => MODULE_LABEL[m] ?? m).join(", ") : "None included"],
        ]}
      />
      <Table head={["Plan", "Check modules", "Rows a month", "Seats", ""]}>
        {data.plans.map((p) => (
          <Tr key={p.name}>
            <Td><b className="font-medium">{p.label}</b></Td>
            <Td>{p.modules.map((m) => MODULE_LABEL[m] ?? m).join(", ") || "—"}</Td>
            <Td className="tnum">{limit(p.monthly_rows, "")}</Td>
            <Td className="tnum">{limit(p.seats, "")}</Td>
            <Td className="text-right">
              {p.name === data.plan ? <StatusPill tone="ok">Current</StatusPill> : p.purchasable ? <button type="button" className="tb-btn tb-btn-primary !px-2.5 !py-1 text-[12.5px]" disabled={busy === p.name} onClick={() => void go("checkout", p.name)}>{busy === p.name ? "Opening…" : "Choose"}</button> : <span className="text-[12.5px]" style={{ color: "var(--faint)" }}>Contact us</span>}
            </Td>
          </Tr>
        ))}
      </Table>
      <span className="text-[12.5px]" style={{ color: "var(--faint)" }}>Prices are shown by Stripe at checkout.</span>
    </Panel>
  );
}
