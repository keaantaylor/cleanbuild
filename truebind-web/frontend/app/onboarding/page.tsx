"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { ArrowLeft, ArrowRight, CalendarBlank, Check, CheckCircle, Copy, EnvelopeSimple, Lightning, Plugs, Plus, UploadSimple, X } from "@phosphor-icons/react";
import { api, ApiError, IN_PROGRESS, mayHaveSession } from "@/lib/api";
import { ROLE_HELP, ROLE_LABEL } from "@/lib/auth";
import type { Binder, Channels, Invitation, Me, OrgType, Report, Role } from "@/lib/types";
import { useUi } from "@/lib/ui";
import { AuthShell, Field, FormError } from "@/components/nocturne/auth-shell";
import { Modal, StatusPill, Toggle } from "@/components/nocturne/ui";
import { Dropzone, FileGlyph, MappingReview, ProcessingPanel, useIntake } from "@/components/nocturne/intake";
import { formatNumber } from "@/lib/formatters";

const STEPS = [
  { key: "account", label: "Create account" },
  { key: "company", label: "Company details" },
  { key: "team", label: "Invite team" },
  { key: "senders", label: "Invite senders" },
  { key: "binders", label: "Binders & ruleset" },
  { key: "channels", label: "Intake channels" },
  { key: "upload", label: "First bordereau" },
  { key: "done", label: "All set" },
];

const ORG_TYPES: { v: OrgType; label: string; help: string }[] = [
  { v: "mga", label: "MGA / coverholder", help: "You receive claims bordereaux from TPAs and report to carriers." },
  { v: "tpa", label: "TPA", help: "You produce claims bordereaux for MGAs and carriers." },
  { v: "capacity_provider", label: "Carrier / capacity provider", help: "You receive bordereaux from the coverholders and TPAs you give capacity to." },
];

type Draft = { step: number; name: string; email: string; terms: boolean; company: string; orgType: OrgType; require2fa: boolean };
const EMPTY: Draft = { step: 0, name: "", email: "", terms: false, company: "", orgType: "mga", require2fa: false };
const DKEY = "tb-onboarding-draft";

export default function OnboardingPage() {
  return (
    <Suspense>
      <Onboarding />
    </Suspense>
  );
}

function Onboarding() {
  const router = useRouter();
  const { toast } = useUi();
  const [d, setD] = useState<Draft>(EMPTY);
  const [password, setPassword] = useState("");
  const [me, setMe] = useState<Me | null>(null);
  const [ready, setReady] = useState(false);
  const [exitOpen, setExitOpen] = useState(false);
  const [firstReport, setFirstReport] = useState<Report | null>(null);

  // Restore the saved draft (never the password) and pick up an existing session.
  useEffect(() => {
    let draft = EMPTY;
    try {
      const raw = localStorage.getItem(DKEY);
      if (raw) draft = { ...EMPTY, ...JSON.parse(raw) };
    } catch {
      // ignore a corrupt draft
    }
    // Only ask the API when this browser may be signed in: no 401 for new visitors.
    (mayHaveSession() ? api.me() : Promise.reject(new Error("signed out")))
      .then((m) => {
        setMe(m);
        setD({ ...draft, name: m.user.display_name, email: m.user.email, company: m.tenant.name, orgType: m.tenant.org_type ?? draft.orgType, step: Math.max(2, draft.step) });
      })
      .catch(() => setD({ ...draft, step: Math.min(draft.step, 1) }))
      .finally(() => setReady(true));
  }, []);
  useEffect(() => {
    if (!ready) return;
    try {
      localStorage.setItem(DKEY, JSON.stringify(d));
    } catch {
      // storage unavailable: progress simply isn't saved
    }
  }, [d, ready]);

  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setD((p) => ({ ...p, [k]: v }));
  const go = (step: number) => {
    setD((p) => ({ ...p, step }));
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const finish = async () => {
    try {
      if (d.require2fa) await api.updateOrg({ require_2fa: true });
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Two-step verification could not be switched on. Do it from Settings.", "warn");
    }
    try {
      localStorage.removeItem(DKEY);
    } catch {
      // nothing to clean up
    }
    toast(`Welcome to TrueBind, ${d.name.split(" ")[0] || "there"}.`, "ok");
    router.push(d.require2fa ? "/settings?tab=security&required=1" : firstReport ? `/reports/${firstReport.id}` : "/overview");
  };

  if (!ready) return <AuthShell steps={STEPS} step={0}><div className="h-40" /></AuthShell>;

  const s = d.step;
  const signedIn = !!me;
  return (
    <AuthShell
      steps={STEPS}
      step={s}
      onJump={(i) => i < s && (i >= 2 || !signedIn) && go(i)}
      headerRight={
        <button type="button" onClick={() => (signedIn ? router.push("/overview") : setExitOpen(true))} className="tb-btn tb-btn-ghost">
          <X size={14} />
          {signedIn ? "Finish later" : "Save & exit"}
        </button>
      }
    >
      <div key={s} className="anim-rise">
        {s === 0 && <AccountStep d={d} set={set} password={password} setPassword={setPassword} next={() => go(1)} />}
        {s === 1 && (
          <CompanyStep
            d={d}
            set={set}
            password={password}
            back={() => go(0)}
            done={(m) => {
              setMe(m);
              setPassword("");
              go(2);
            }}
          />
        )}
        {s === 2 && <InviteStep kind="team" back={undefined} next={() => go(3)} />}
        {s === 3 && <InviteStep kind="senders" back={() => go(2)} next={() => go(4)} />}
        {s === 4 && <BindersStep back={() => go(3)} next={() => go(5)} />}
        {s === 5 && <ChannelsStep back={() => go(4)} next={() => go(6)} />}
        {s === 6 && <FirstFileStep back={() => go(5)} next={() => go(7)} onComplete={setFirstReport} report={firstReport} />}
        {s === 7 && <DoneStep d={d} me={me} report={firstReport} finish={finish} jump={go} />}
      </div>
      <Modal
        open={exitOpen}
        onClose={() => setExitOpen(false)}
        title="Leave setup for now?"
        actions={
          <>
            <button className="tb-btn" onClick={() => setExitOpen(false)}>Keep going</button>
            <button className="tb-btn tb-btn-primary" onClick={() => router.push("/")}>Save and exit</button>
          </>
        }
      >
        Your name, email and company are saved on this device (never your password). Your account isn’t created until you finish the Company details step.
      </Modal>
    </AuthShell>
  );
}

function StepHead({ n, title, sub }: { n: number; title: string; sub: string }) {
  return (
    <div className="mb-8 flex flex-col gap-2">
      <span className="kicker">Setup · {n} of {STEPS.length}</span>
      <h1 className="m-0 text-[30px] font-medium leading-[1.12] tracking-[-0.02em] [text-wrap:balance]">{title}</h1>
      <p className="m-0 max-w-[560px] text-[15px] leading-[1.6]" style={{ color: "var(--muted)" }}>{sub}</p>
    </div>
  );
}

function Nav({ back, next, nextLabel = "Continue", disabled, skip, hint, busy }: { back?: () => void; next: () => void; nextLabel?: string; disabled?: boolean; skip?: () => void; hint?: string; busy?: boolean }) {
  return (
    <div className="mt-10 flex flex-wrap items-center gap-3 pt-6" style={{ boxShadow: "0 -1px 0 var(--line)" }}>
      {back && (
        <button type="button" className="tb-btn tb-btn-ghost" onClick={back}>
          <ArrowLeft size={14} />
          Back
        </button>
      )}
      <div className="flex-1 text-[12.5px]" style={{ color: "var(--faint)" }}>{hint}</div>
      {skip && (
        <button type="button" className="tb-btn tb-btn-ghost" onClick={skip}>
          Skip for now
        </button>
      )}
      <button type="button" className="tb-btn tb-btn-solid" onClick={next} disabled={disabled || busy}>
        {busy ? "Please wait…" : nextLabel}
        {!busy && <ArrowRight size={14} />}
      </button>
    </div>
  );
}

type SetFn = <K extends keyof Draft>(k: K, v: Draft[K]) => void;

function AccountStep({ d, set, password, setPassword, next }: { d: Draft; set: SetFn; password: string; setPassword: (v: string) => void; next: () => void }) {
  const emailOk = /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(d.email);
  const personal = /@(gmail|yahoo|hotmail|outlook|icloud|live)\./i.test(d.email);
  const score = [password.length >= 12, /[A-Z]/.test(password), /\d/.test(password), /[^A-Za-z0-9]/.test(password)].filter(Boolean).length;
  const valid = d.name.trim().length > 1 && emailOk && password.length >= 12 && d.terms;
  return (
    <>
      <StepHead n={1} title="Set up TrueBind for your team" sub="Takes about five minutes. You’ll finish by running your first bordereau through the same checks your carriers expect." />
      <form
        className="flex flex-col gap-5"
        onSubmit={(e) => {
          e.preventDefault();
          if (valid) next();
        }}
      >
        <Field label="Full name" id="ob-name">
          <input id="ob-name" className="tb-input" autoComplete="name" value={d.name} onChange={(e) => set("name", e.target.value)} maxLength={200} />
        </Field>
        <Field label="Work email" id="ob-email" hint={personal ? "That looks like a personal address. A work email lets your team join the same workspace and use single sign-on." : undefined}>
          <input id="ob-email" type="email" autoComplete="email" className="tb-input" value={d.email} onChange={(e) => set("email", e.target.value)} />
        </Field>
        <Field label="Password" id="ob-pw" hint="At least 12 characters.">
          <input id="ob-pw" type="password" autoComplete="new-password" className="tb-input" value={password} onChange={(e) => setPassword(e.target.value)} />
          <div className="mt-2 flex gap-1" aria-hidden="true">
            {[0, 1, 2, 3].map((i) => (
              <span key={i} className="h-1 flex-1 rounded-full transition-colors" style={{ background: i < score ? (score < 2 ? "var(--err)" : score < 4 ? "var(--warn)" : "var(--ok)") : "var(--line)" }} />
            ))}
          </div>
        </Field>
        <label className="flex cursor-pointer items-start gap-2.5 text-[13.5px]" style={{ color: "var(--muted)" }}>
          <input type="checkbox" checked={d.terms} onChange={(e) => set("terms", e.target.checked)} className="mt-0.5 h-4 w-4 accent-[var(--accent)]" />
          <span>
            I agree to the TrueBind terms and the{" "}
            <Link href="/privacy" target="_blank" className="underline" style={{ color: "var(--accentText)" }}>privacy notice</Link>.
          </span>
        </label>
        <Nav next={next} disabled={!valid} nextLabel="Continue" hint={password && password.length < 12 ? `${12 - password.length} more character${12 - password.length === 1 ? "" : "s"}` : undefined} />
      </form>
      <p className="mt-5 text-[13.5px]" style={{ color: "var(--muted)" }}>
        Already have an account?{" "}
        <Link href="/login" className="underline" style={{ color: "var(--accentText)" }}>Sign in</Link>
      </p>
    </>
  );
}

function CompanyStep({ d, set, password, back, done }: { d: Draft; set: SetFn; password: string; back: () => void; done: (m: Me) => void }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const t = ORG_TYPES.find((x) => x.v === d.orgType) ?? ORG_TYPES[0];
  const slug = d.company.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
  const create = async () => {
    if (!password) {
      setErr("For your security the password isn’t saved between visits. Go back one step and enter it again.");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const me = await api.signup({ email: d.email.trim(), password, display_name: d.name.trim(), organisation: d.company.trim() });
      if (me.tenant.org_type !== d.orgType) await api.updateOrg({ org_type: d.orgType });
      done({ ...me, tenant: { ...me.tenant, org_type: d.orgType } });
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Your account could not be created.");
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <StepHead n={2} title="Tell us about your company" sub="This names your workspace and tunes the checks to how you work. Your account is created when you continue." />
      <div className="flex flex-col gap-6">
        {err && <FormError>{err}</FormError>}
        <Field label="Company name" id="co-name" hint={slug ? `Your workspace: ${d.company.trim()}` : undefined}>
          <input id="co-name" className="tb-input" autoComplete="organization" value={d.company} onChange={(e) => set("company", e.target.value)} maxLength={200} />
        </Field>
        <div>
          <span className="tb-label">What kind of business are you?</span>
          <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Company type">
            {ORG_TYPES.map((o) => (
              <button
                key={o.v}
                type="button"
                role="radio"
                aria-checked={d.orgType === o.v}
                onClick={() => set("orgType", o.v)}
                className="cursor-pointer rounded-md px-3.5 py-2 text-[13.5px] transition-colors"
                style={{ boxShadow: `inset 0 0 0 1px ${d.orgType === o.v ? "var(--accent)" : "var(--line2)"}`, background: d.orgType === o.v ? "var(--accentTint)" : "transparent", color: d.orgType === o.v ? "var(--accentText)" : "var(--text)" }}
              >
                {o.label}
              </button>
            ))}
          </div>
          <span className="mt-2 block text-[12px]" style={{ color: "var(--faint)" }}>{t.help}</span>
        </div>
        <label className="flex items-start gap-3">
          <Toggle on={d.require2fa} onChange={(v) => set("require2fa", v)} label="Require two-step verification" />
          <span className="flex flex-col text-[13.5px]">
            <span className="font-medium">Require two-step verification for every member</span>
            <span className="text-[12px]" style={{ color: "var(--faint)" }}>Switched on when you finish setup; you’ll be asked to set up your authenticator app first.</span>
          </span>
        </label>
      </div>
      <Nav back={back} next={create} busy={busy} disabled={d.company.trim().length < 2} nextLabel="Create my workspace" />
    </>
  );
}

function InviteStep({ kind, back, next }: { kind: "team" | "senders"; back?: () => void; next: () => void }) {
  const { toast } = useUi();
  const roles: Role[] = kind === "team" ? ["ADMIN", "ANALYST", "VIEWER"] : ["SENDER"];
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>(roles[kind === "team" ? 1 : 0]);
  const [invites, setInvites] = useState<(Invitation & { link?: string })[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const load = useCallback(() => {
    api
      .listInvitations()
      .then((l) => setInvites((prev) => l.map((i) => ({ ...i, link: prev.find((p) => p.id === i.id)?.link }))))
      .catch(() => undefined);
  }, []);
  useEffect(() => {
    load();
  }, [load]);
  const mine = invites.filter((i) => (kind === "senders" ? i.role === "SENDER" : i.role !== "SENDER"));
  const ok = /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email);
  const add = async () => {
    setBusy(true);
    setErr(null);
    try {
      const created = await api.invite(email.trim(), role);
      const link = `${window.location.origin}/invite?token=${encodeURIComponent(created.accept_token)}`;
      setInvites((l) => [{ ...created, link }, ...l.filter((x) => x.id !== created.id)]);
      setEmail("");
      toast(`Invitation created for ${created.email}`, "ok");
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "The invitation could not be created.");
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <StepHead
        n={kind === "team" ? 3 : 4}
        title={kind === "team" ? "Invite your team" : "Invite your senders"}
        sub={
          kind === "team"
            ? "Everyone who reviews findings or confirms mappings should have their own login, so every decision in the audit trail has a name on it."
            : "Give each TPA or coverholder a sender login. They get their own portal to check a bordereau before sending it and to submit it to you. They never see your data."
        }
      />
      <div className="flex flex-col gap-4">
        {err && <FormError>{err}</FormError>}
        <form
          className="flex flex-wrap items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (ok && !busy) void add();
          }}
        >
          <input aria-label="Email to invite" className="tb-input min-w-[220px] flex-1" type="email" placeholder={kind === "team" ? "colleague@company.ie" : "bordereaux@sender.com"} value={email} onChange={(e) => setEmail(e.target.value)} />
          {kind === "team" && (
            <select aria-label="Role" className="tb-input !w-auto" value={role} onChange={(e) => setRole(e.target.value as Role)}>
              {roles.map((r) => (
                <option key={r} value={r}>{ROLE_LABEL[r]}</option>
              ))}
            </select>
          )}
          <button type="submit" className="tb-btn tb-btn-primary" disabled={!ok || busy}>
            <Plus size={14} />
            {busy ? "Inviting…" : "Invite"}
          </button>
        </form>
        <div className="tb-card overflow-hidden">
          {mine.length === 0 && <div className="px-4 py-6 text-center text-[13.5px]" style={{ color: "var(--faint)" }}>No invitations yet.</div>}
          {mine.map((i) => (
            <div key={i.id} className="anim-rise flex flex-wrap items-center gap-3 px-4 py-3" style={{ boxShadow: "0 1px 0 var(--line)" }}>
              <span className="grid h-8 w-8 flex-none place-items-center rounded-full text-[12px] font-semibold" style={{ background: "var(--accentTint)", color: "var(--accentText)" }}>{i.email[0]?.toUpperCase()}</span>
              <span className="flex min-w-[180px] flex-1 flex-col text-[13.5px]">
                <span className="truncate font-medium">{i.email}</span>
                <span className="text-[12px]" style={{ color: "var(--faint)" }}>{ROLE_LABEL[i.role]} · expires {new Date(i.expires_at).toLocaleDateString("en-IE", { day: "numeric", month: "short" })}</span>
              </span>
              {i.link ? (
                <button
                  type="button"
                  className="tb-btn !py-1.5 text-[12.5px]"
                  onClick={() => {
                    void navigator.clipboard?.writeText(i.link!);
                    toast("Invitation link copied", "info");
                  }}
                >
                  <Copy size={13} />
                  Copy link
                </button>
              ) : (
                <StatusPill tone="muted">Pending</StatusPill>
              )}
            </div>
          ))}
        </div>
        <span className="text-[12.5px]" style={{ color: "var(--faint)" }}>
          Invitations expire after 7 days. Until email delivery is set up on your server, copy each link and send it yourself.
        </span>
        {kind === "team" && (
          <dl className="m-0 grid gap-x-4 gap-y-1.5 text-[12.5px] sm:grid-cols-[90px_1fr]">
            {(["OWNER", ...roles] as Role[]).map((r) => (
              <div key={r} className="contents">
                <dt className="font-medium">{ROLE_LABEL[r]}</dt>
                <dd className="m-0" style={{ color: "var(--muted)" }}>{ROLE_HELP[r]}</dd>
              </div>
            ))}
          </dl>
        )}
      </div>
      <Nav back={back} next={next} skip={mine.length ? undefined : next} />
    </>
  );
}

function BindersStep({ back, next }: { back: () => void; next: () => void }) {
  const { toast } = useUi();
  const [binders, setBinders] = useState<Binder[] | null>(null);
  const [f, setF] = useState({ name: "", umr: "", coverholder: "", inception_date: "", expiry_date: "", currencies: "GBP, EUR", limit_currency: "GBP", claims_authority: "", aggregate_limit: "" });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api.listBinders().then(setBinders).catch(() => setBinders([]));
  }, []);
  const valid = f.name.trim() && f.inception_date && f.expiry_date && f.limit_currency.trim().length === 3;
  const add = async () => {
    setBusy(true);
    setErr(null);
    try {
      const b = await api.createBinder({
        name: f.name.trim(),
        umr: f.umr.trim() || null,
        coverholder: f.coverholder.trim() || null,
        inception_date: f.inception_date,
        expiry_date: f.expiry_date,
        currencies: f.currencies.split(",").map((c) => c.trim()).filter(Boolean),
        limit_currency: f.limit_currency.trim().toUpperCase(),
        claims_authority: f.claims_authority.trim() || null,
        aggregate_limit: f.aggregate_limit.trim() || null,
      });
      setBinders((l) => [...(l ?? []), b]);
      setF({ ...f, name: "", umr: "", coverholder: "" });
      toast(`Binder “${b.name}” added`, "ok");
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "The binder could not be saved.");
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <StepHead n={5} title="Binders and the ruleset" sub="Every bordereau is validated against Lloyd’s CRS v5.2. Add the binding authorities you report under and TrueBind also checks period, currencies, claims settlement authority and aggregate limit." />
      <div className="flex flex-col gap-5">
        <div className="flex items-center gap-3 rounded-md px-4 py-3" style={{ background: "var(--accentTint)", boxShadow: "inset 0 0 0 1px color-mix(in srgb, var(--accent) 40%, transparent)" }}>
          <CheckCircle size={18} weight="fill" style={{ color: "var(--accentText)" }} />
          <span className="text-[13.5px]"><b>Lloyd’s CRS v5.2</b> ruleset · required data, arithmetic, dates, currencies, status, duplicates vs development</span>
        </div>
        <div className="tb-card overflow-hidden">
          {binders === null && <div className="px-4 py-5 text-[13px]" style={{ color: "var(--faint)" }}>Loading binders…</div>}
          {binders?.length === 0 && <div className="px-4 py-5 text-center text-[13.5px]" style={{ color: "var(--faint)" }}>No binders yet. Rules a binder would set are reported as “not assessed” until you add one.</div>}
          {binders?.map((b) => (
            <div key={b.id} className="flex items-center gap-3 px-4 py-3" style={{ boxShadow: "0 1px 0 var(--line)" }}>
              <CalendarBlank size={18} style={{ color: "var(--accentText)" }} />
              <span className="flex min-w-0 flex-1 flex-col text-[13.5px]">
                <span className="font-medium">{b.name}</span>
                <span className="text-[12px]" style={{ color: "var(--faint)" }}>
                  {b.umr || "No UMR"} · {b.inception_date} → {b.expiry_date} · {b.currencies.join(", ") || "any currency"}
                </span>
              </span>
            </div>
          ))}
        </div>
        {err && <FormError>{err}</FormError>}
        <form
          className="grid gap-3 sm:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (valid && !busy) void add();
          }}
        >
          <Field label="Binder name" id="bi-name"><input id="bi-name" className="tb-input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="Property binder 2026" /></Field>
          <Field label="UMR (optional)" id="bi-umr"><input id="bi-umr" className="tb-input" value={f.umr} onChange={(e) => setF({ ...f, umr: e.target.value })} /></Field>
          <Field label="Inception date" id="bi-inc"><input id="bi-inc" type="date" className="tb-input" value={f.inception_date} onChange={(e) => setF({ ...f, inception_date: e.target.value })} /></Field>
          <Field label="Expiry date" id="bi-exp"><input id="bi-exp" type="date" className="tb-input" value={f.expiry_date} onChange={(e) => setF({ ...f, expiry_date: e.target.value })} /></Field>
          <Field label="Permitted settlement currencies" id="bi-ccy" hint="ISO codes, comma-separated. Leave empty to skip the currency rule."><input id="bi-ccy" className="tb-input" value={f.currencies} onChange={(e) => setF({ ...f, currencies: e.target.value })} /></Field>
          <Field label="Limit currency" id="bi-lccy"><input id="bi-lccy" className="tb-input" value={f.limit_currency} onChange={(e) => setF({ ...f, limit_currency: e.target.value })} maxLength={3} /></Field>
          <Field label="Claims settlement authority (optional)" id="bi-auth"><input id="bi-auth" className="tb-input tnum" inputMode="decimal" value={f.claims_authority} onChange={(e) => setF({ ...f, claims_authority: e.target.value })} placeholder="Per claim" /></Field>
          <Field label="Aggregate limit (optional)" id="bi-agg"><input id="bi-agg" className="tb-input tnum" inputMode="decimal" value={f.aggregate_limit} onChange={(e) => setF({ ...f, aggregate_limit: e.target.value })} /></Field>
          <div className="sm:col-span-2">
            <button type="submit" className="tb-btn tb-btn-primary" disabled={!valid || busy}>
              <Plus size={14} />
              {busy ? "Saving…" : "Add binder"}
            </button>
          </div>
        </form>
      </div>
      <Nav back={back} next={next} skip={binders?.length ? undefined : next} />
    </>
  );
}

const CH_ICON: Record<string, React.ElementType> = { upload: UploadSimple, api: Lightning, email: EnvelopeSimple, sftp: Plugs };
const CH_STATUS: Record<string, { label: string; tone: "ok" | "warn" | "muted" | "med" }> = {
  active: { label: "Live", tone: "ok" },
  not_set_up: { label: "Ready to set up", tone: "med" },
  not_configured: { label: "Not configured on the server", tone: "warn" },
  planned: { label: "Planned", tone: "muted" },
};

function ChannelsStep({ back, next }: { back: () => void; next: () => void }) {
  const { toast } = useUi();
  const [ch, setCh] = useState<Channels | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => {
    api.channels().then(setCh).catch((e) => setErr(e instanceof ApiError ? e.message : "Channels could not be loaded."));
  }, []);
  useEffect(() => {
    load();
  }, [load]);
  const email = ch?.inbound.find((c) => c.id === "email");
  const createAddress = async () => {
    setBusy(true);
    try {
      const r = await api.rotateInbound();
      toast(r.address ? `Your intake address: ${r.address}` : "Email intake isn’t configured on this server", r.address ? "ok" : "warn");
      load();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Could not create the address.", "err");
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <StepHead n={6} title="How will files reach TrueBind?" sub="These statuses come from your server. Live channels work today; anything not built yet is shown as planned, never as working." />
      {err && <FormError>{err}</FormError>}
      {!ch && !err && <div className="h-40 animate-pulse rounded-md" style={{ background: "var(--line)" }} />}
      {ch && (
        <div className="grid gap-3 sm:grid-cols-2">
          {ch.inbound.map((c) => {
            const Icon = CH_ICON[c.id] ?? Plugs;
            const st = CH_STATUS[c.status] ?? CH_STATUS.planned;
            const live = c.status === "active";
            return (
              <div key={c.id} className="flex flex-col gap-3 rounded-md p-4" style={{ background: live ? "color-mix(in srgb, var(--ok) 6%, var(--surface))" : "var(--surface)", boxShadow: live ? "var(--shadow), inset 0 0 0 1px color-mix(in srgb, var(--ok) 40%, transparent)" : "var(--shadow)" }}>
                <div className="flex items-center justify-between">
                  <span className="grid h-9 w-9 place-items-center rounded-md text-[17px]" style={{ background: "var(--accentTint)", color: "var(--accentText)" }}>
                    <Icon />
                  </span>
                  <StatusPill tone={st.tone}>{st.label}</StatusPill>
                </div>
                <span className="text-[15px] font-medium">{c.name}</span>
                <span className="flex-1 text-[13px] leading-[1.5]" style={{ color: "var(--muted)" }}>{c.detail}</span>
                {c.id === "email" && c.status === "not_set_up" && (
                  <button type="button" className="tb-btn self-start !py-1.5 text-[12.5px]" onClick={createAddress} disabled={busy}>
                    {busy ? "Creating…" : "Create my intake address"}
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}
      {email?.address && (
        <p className="mt-4 text-[13.5px]">
          Forward bordereaux to <b className="tnum">{email.address}</b>.
        </p>
      )}
      <p className="mt-4 text-[12.5px]" style={{ color: "var(--faint)" }}>
        Outbound delivery (email, signed webhooks and SFTP) is set up per organisation in Settings → Channels.
      </p>
      <Nav back={back} next={next} />
    </>
  );
}

function FirstFileStep({ back, next, onComplete, report: done }: { back: () => void; next: () => void; onComplete: (r: Report) => void; report: Report | null }) {
  const flow = useIntake({ onComplete });
  const { report, sheets, setSheets, error, upload, start, process, cancel, retry } = flow;
  const r = report ?? done;
  return (
    <>
      <StepHead n={7} title="Run your first bordereau" sub="Upload a real claims bordereau. TrueBind finds the header rows, proposes a mapping by alias rules, and waits for you to confirm before validating anything." />
      <div className="flex flex-col gap-5">
        {!r && <Dropzone upload={upload} onFile={(f) => void start(f, {})} compact />}
        {error && <FormError>{error}</FormError>}
        {r && (IN_PROGRESS.has(r.status) || r.status === "FAILED" || r.status === "CANCELLED") && (
          <ProcessingPanel report={r} system={null} onCancel={IN_PROGRESS.has(r.status) ? cancel : undefined} onRetry={retry} />
        )}
        {r?.status === "WAITING_FOR_REVIEW" && sheets.length > 0 && <MappingReview report={r} sheets={sheets} onSheetsChange={setSheets} onProcess={process} processLabel="Validate every row" />}
        {r?.status === "COMPLETE" && (
          <div className="anim-rise tb-card flex flex-col gap-4 p-5">
            <span className="flex items-center gap-2 text-[15px] font-medium">
              <CheckCircle size={18} style={{ color: "var(--ok)" }} weight="fill" />
              Validation complete
            </span>
            <div className="flex items-center gap-3">
              <FileGlyph name={r.file_name} />
              <span className="truncate text-[13.5px]">{r.file_name}</span>
            </div>
            <div className="tnum grid grid-cols-2 gap-3 sm:grid-cols-4">
              {[
                [formatNumber(r.rows_processed), "Rows assessed"],
                [formatNumber(r.issues_found ?? 0), "Findings"],
                [r.score != null ? `${Math.round(r.score)}/100` : "—", "Health score"],
                [String(r.sheet_count_total), "Sheets"],
              ].map(([v, l]) => (
                <div key={l} className="flex flex-col gap-0.5">
                  <span className="text-[22px] font-medium">{v}</span>
                  <span className="text-[12px]" style={{ color: "var(--muted)" }}>{l}</span>
                </div>
              ))}
            </div>
            <span className="text-[12.5px]" style={{ color: "var(--muted)" }}>The full Health Check report and every finding are waiting in your workspace.</span>
          </div>
        )}
      </div>
      <Nav back={r ? undefined : back} next={next} disabled={!!r && r.status !== "COMPLETE" && r.status !== "FAILED" && r.status !== "CANCELLED"} skip={!r ? next : undefined} hint={r && r.status === "WAITING_FOR_REVIEW" ? "Confirm the mapping to continue" : undefined} />
    </>
  );
}

function DoneStep({ d, me, report, finish, jump }: { d: Draft; me: Me | null; report: Report | null; finish: () => void; jump: (i: number) => void }) {
  const [busy, setBusy] = useState(false);
  const items: [string, string, number][] = [
    ["Account", `${me?.user.display_name ?? d.name} · ${me?.user.email ?? d.email}`, -1],
    ["Company", `${me?.tenant.name ?? d.company} · ${ORG_TYPES.find((o) => o.v === (me?.tenant.org_type ?? d.orgType))?.label ?? ""}`, -1],
    ["Team", "Invitations are listed under Settings → Members", 2],
    ["Senders", "Sender logins use their own pre-flight portal", 3],
    ["Ruleset", "Lloyd’s CRS v5.2 · binders under Settings → Binders", 4],
    ["Intake", "Web upload and API live · email per your server", 5],
    ["First bordereau", report ? `${report.file_name} · ${formatNumber(report.issues_found ?? 0)} findings` : "Skipped — upload from Intake any time", 6],
  ];
  return (
    <>
      <div className="mb-8 flex flex-col gap-2">
        <span className="grid h-12 w-12 place-items-center rounded-full text-[24px]" style={{ background: "var(--okT)", color: "var(--ok)" }}>
          <Check weight="bold" />
        </span>
        <span className="kicker mt-3">Setup complete</span>
        <h1 className="m-0 text-[30px] font-medium tracking-[-0.02em]">{me?.tenant.name ?? d.company} is ready.</h1>
        <p className="m-0 text-[15px]" style={{ color: "var(--muted)" }}>Here’s what’s set up. You can change any of it later in Settings.</p>
      </div>
      <div className="tb-card flex flex-col">
        {items.map(([t, v, step]) => (
          <div key={t} className="grid grid-cols-[120px_1fr_auto] items-center gap-3 px-4 py-3 text-[13.5px]" style={{ boxShadow: "0 1px 0 var(--line)" }}>
            <span style={{ color: "var(--faint)" }}>{t}</span>
            <span className="min-w-0 truncate">{v}</span>
            {step >= 0 ? (
              <button type="button" className="cursor-pointer text-[12.5px]" style={{ color: "var(--accentText)" }} onClick={() => jump(step)}>
                Edit
              </button>
            ) : (
              <span />
            )}
          </div>
        ))}
      </div>
      {d.require2fa && <p className="mt-4 text-[13px]" style={{ color: "var(--warn)" }}>Two-step verification will be required for everyone. You’ll set up your authenticator app next.</p>}
      <div className="mt-8 flex flex-wrap items-center gap-3">
        <button
          type="button"
          className="tb-btn tb-btn-solid !px-5 !py-3"
          disabled={busy}
          onClick={() => {
            setBusy(true);
            void finish();
          }}
        >
          {report ? "Open my Health Check" : "Go to your Overview"}
          <ArrowRight size={14} />
        </button>
      </div>
    </>
  );
}
