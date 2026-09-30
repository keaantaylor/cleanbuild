"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Key, SignIn } from "@phosphor-icons/react";
import { api, ApiError, isMfaChallenge } from "@/lib/api";
import { safeNext, ssoErrorMessage } from "@/lib/auth";
import { AuthShell, Field, FormError } from "@/components/nocturne/auth-shell";
import { Modal } from "@/components/nocturne/ui";

export default function LoginPage() {
  return (
    <Suspense>
      <Login />
    </Suspense>
  );
}

function Login() {
  const router = useRouter();
  const params = useSearchParams();
  const [mode, setMode] = useState<"login" | "mfa" | "sso">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(ssoErrorMessage(params.get("sso_error")));
  const [busy, setBusy] = useState(false);
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [useRecovery, setUseRecovery] = useState(false);
  const [forgot, setForgot] = useState(false);

  // Old sign-up links (?mode=signup) now start the guided set-up.
  useEffect(() => {
    if (params.get("mode") === "signup") router.replace("/onboarding");
  }, [params, router]);

  const done = () => router.replace(safeNext(params.get("next")));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "sso") {
        window.location.assign(api.ssoStartUrl(email));
        return;
      }
      if (mode === "mfa" && mfaToken) {
        await api.verifyMfa(mfaToken, useRecovery ? { recovery_code: code } : { code: code.replace(/\s/g, "") });
        done();
        return;
      }
      const res = await api.login(email, password);
      if (isMfaChallenge(res)) {
        setMfaToken(res.mfa_token);
        setCode("");
        setMode("mfa");
        return;
      }
      done();
    } catch (err) {
      if (mode === "mfa" && err instanceof ApiError && err.status === 401 && /expired/i.test(err.message)) {
        setMode("login");
        setMfaToken(null);
      }
      setError(err instanceof ApiError ? err.message : "Could not sign in.");
    } finally {
      setBusy(false);
    }
  }

  const TITLES = {
    login: ["Welcome back to TrueBind", "Sign in to your organisation’s workspace."],
    mfa: ["Two-step verification", useRecovery ? "Enter one of your recovery codes." : "Enter the 6-digit code from your authenticator app."],
    sso: ["Single sign-on", "Continue with your organisation’s identity provider (Microsoft Entra ID or any OpenID Connect provider)."],
  } as const;
  const [title, sub] = TITLES[mode];

  return (
    <AuthShell intro={{ kicker: "Welcome back", body: "Every file, from any sender, runs the same audited path: map, validate, reconcile, audit." }} headerRight={<Link href="/" className="tb-btn tb-btn-ghost">Back to site</Link>}>
      <div className="mb-8 flex flex-col gap-2">
        <span className="kicker">{mode === "mfa" ? "Sign in · step 2" : "Sign in"}</span>
        <h1 className="m-0 text-[30px] font-medium tracking-[-0.02em]">{title}</h1>
        <p className="m-0 text-[15px]" style={{ color: "var(--muted)" }}>{sub}</p>
      </div>
      <form className="flex flex-col gap-5" onSubmit={submit}>
        {error && <FormError>{error}</FormError>}
        {mode === "mfa" ? (
          <Field label={useRecovery ? "Recovery code" : "Authentication code"} id="li-code">
            <input
              id="li-code"
              className="tb-input tnum"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              required
              autoFocus
              inputMode={useRecovery ? "text" : "numeric"}
              autoComplete="one-time-code"
              maxLength={useRecovery ? 32 : 8}
              pattern={useRecovery ? undefined : "[0-9 ]{6,8}"}
            />
          </Field>
        ) : (
          <Field label="Work email" id="li-email">
            <input id="li-email" type="email" className="tb-input" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" autoFocus />
          </Field>
        )}
        {mode === "login" && (
          <Field label="Password" id="li-pw">
            <input id="li-pw" type="password" className="tb-input" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password" />
          </Field>
        )}
        <div className="flex flex-wrap items-center gap-3">
          <button type="submit" className="tb-btn tb-btn-solid" disabled={busy}>
            {mode === "sso" ? <Key size={15} /> : <SignIn size={15} />}
            {busy ? "Please wait…" : { login: "Sign in", mfa: "Verify", sso: "Continue" }[mode]}
          </button>
          {mode === "login" && (
            <button type="button" className="tb-btn" onClick={() => { setMode("sso"); setError(null); }}>
              <Key size={15} />
              Sign in with single sign-on
            </button>
          )}
          {mode === "login" && (
            <button type="button" className="tb-hit ml-auto cursor-pointer text-[13px] underline" style={{ color: "var(--accentText)" }} onClick={() => setForgot(true)}>
              Forgot password?
            </button>
          )}
          {mode === "mfa" && (
            <button type="button" className="cursor-pointer text-[13px] underline" style={{ color: "var(--accentText)" }} onClick={() => { setUseRecovery(!useRecovery); setCode(""); setError(null); }}>
              {useRecovery ? "Use an authentication code instead" : "Lost your device? Use a recovery code"}
            </button>
          )}
          {mode !== "login" && (
            <button type="button" className="cursor-pointer text-[13px] underline" style={{ color: "var(--accentText)" }} onClick={() => { setMode("login"); setMfaToken(null); setError(null); }}>
              Back to password sign-in
            </button>
          )}
        </div>
      </form>
      <p className="mt-8 text-[13.5px]" style={{ color: "var(--muted)" }}>
        New to TrueBind?{" "}
        <Link href="/onboarding" className="underline" style={{ color: "var(--accentText)" }}>
          Set up your company
        </Link>
      </p>
      <Modal open={forgot} onClose={() => setForgot(false)} title="Forgot your password?" actions={<button className="tb-btn tb-btn-primary" onClick={() => setForgot(false)}>Got it</button>}>
        TrueBind doesn’t send password-reset emails yet. Ask an owner or admin in your organisation to remove you and send a new invitation from Settings → Members. If your organisation uses single sign-on, choose “Sign in with single sign-on” instead.
      </Modal>
    </AuthShell>
  );
}
