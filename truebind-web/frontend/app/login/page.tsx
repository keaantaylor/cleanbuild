"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api, ApiError, isMfaChallenge } from "@/lib/api";
import { safeNext, ssoErrorMessage } from "@/lib/auth";
import { Button } from "@/components/ui/Button";
import { AlertBanner } from "@/components/ui/Alert";
import { BrandMark } from "@/components/layout/BrandMark";
import styles from "./login.module.css";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [mode, setMode] = useState<"login" | "signup" | "mfa" | "sso">(params.get("mode") === "signup" ? "signup" : "login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [org, setOrg] = useState("");
  const [error, setError] = useState<string | null>(ssoErrorMessage(params.get("sso_error")));
  const [busy, setBusy] = useState(false);
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [useRecovery, setUseRecovery] = useState(false);

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
      if (mode === "login") {
        const res = await api.login(email, password);
        if (isMfaChallenge(res)) {
          setMfaToken(res.mfa_token);
          setCode("");
          setMode("mfa");
          return;
        }
      } else {
        await api.signup({ email, password, display_name: name, organisation: org });
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
    login: ["Sign in", "Welcome back."],
    signup: ["Create your workspace", "Your organisation gets its own isolated workspace."],
    mfa: ["Two-step verification", useRecovery ? "Enter one of your recovery codes." : "Enter the 6-digit code from your authenticator app."],
    sso: ["Single sign-on", "Continue with your organisation's identity provider."],
  } as const;
  const [title, sub] = TITLES[mode];

  return (
    <main className={styles.wrap}>
      <section className={styles.brand} aria-label="About TrueBind">
        <div className={styles.logo}><BrandMark size={32} />TrueBind</div>
        <h1 className={styles.headline}>Bordereaux, understood.</h1>
        <p className={styles.lede}>Receive, map, validate and reconcile claims bordereaux from any sender, with an audit trail behind every number.</p>
        <ul className={styles.points}>
          <li>Every source row accounted for: claims, exclusions and reasons</li>
          <li>Lloyd&rsquo;s CRS v5.2 arithmetic, duplicates vs development</li>
          <li>Hash-chained audit trail; nothing changed without a record</li>
        </ul>
      </section>
      <section className={styles.formSide}>
        <div className={styles.card}>
          <h2 className={styles.title}>{title}</h2>
          <p className={styles.sub}>{sub}</p>
          {error && <AlertBanner tone="error" title={mode === "signup" ? "Sign-up failed" : "Sign-in failed"}>{error}</AlertBanner>}
          <form onSubmit={submit} className={styles.form} noValidate={false}>
            {mode === "signup" && (
              <>
                <label className={styles.label}>Your name<input className={styles.input} value={name} onChange={(e) => setName(e.target.value)} required maxLength={200} autoComplete="name" /></label>
                <label className={styles.label}>Organisation<input className={styles.input} value={org} onChange={(e) => setOrg(e.target.value)} required maxLength={200} autoComplete="organization" /></label>
              </>
            )}
            {mode === "mfa" ? (
              <label className={styles.label}>{useRecovery ? "Recovery code" : "Authentication code"}
                <input className={styles.input} value={code} onChange={(e) => setCode(e.target.value)} required autoFocus
                  inputMode={useRecovery ? "text" : "numeric"} autoComplete="one-time-code" maxLength={useRecovery ? 32 : 8}
                  pattern={useRecovery ? undefined : "[0-9 ]{6,8}"} />
              </label>
            ) : (
              <label className={styles.label}>Work e-mail<input className={styles.input} type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" autoFocus /></label>
            )}
            {(mode === "login" || mode === "signup") && (
              <label className={styles.label}>Password<input className={styles.input} type="password" value={password} onChange={(e) => setPassword(e.target.value)} required
                minLength={mode === "signup" ? 12 : 1} autoComplete={mode === "login" ? "current-password" : "new-password"} aria-describedby={mode === "signup" ? "pw-hint" : undefined} /></label>
            )}
            {mode === "signup" && <small id="pw-hint" className={styles.hint}>At least 12 characters.</small>}
            <Button type="submit" loading={busy} style={{ width: "100%", minHeight: 42 }}>
              {{ login: "Sign in", signup: "Create account", mfa: "Verify", sso: "Continue" }[mode]}
            </Button>
          </form>
          <p className={styles.switch}>
            {mode === "mfa" ? (
              <button type="button" className={styles.link} onClick={() => { setUseRecovery(!useRecovery); setCode(""); setError(null); }}>
                {useRecovery ? "Use an authentication code instead" : "Lost your device? Use a recovery code"}
              </button>
            ) : (
              <button type="button" className={styles.link} onClick={() => { setMode(mode === "login" ? "signup" : "login"); setError(null); }}>
                {mode === "login" ? "Need an account? Sign up" : "Have an account? Sign in"}
              </button>
            )}
          </p>
          {mode === "login" && (
            <p className={styles.switch}>
              <button type="button" className={styles.link} onClick={() => { setMode("sso"); setError(null); }}>Sign in with single sign-on</button>
            </p>
          )}
        </div>
      </section>
    </main>
  );
}

function LoginSkeleton() {
  return <main className={styles.wrap}><section className={styles.brand} /><section className={styles.formSide}><div className={styles.card} aria-busy="true" /></section></main>;
}

export default function LoginPage() {
  return <Suspense fallback={<LoginSkeleton />}><LoginForm /></Suspense>;
}
