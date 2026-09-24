"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { AlertBanner } from "@/components/ui/Alert";
import styles from "./login.module.css";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [org, setOrg] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "login") await api.login(email, password);
      else await api.signup({ email, password, display_name: name, organisation: org });
      const next = params.get("next");
      router.replace(next && next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/login") ? next : "/overview");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not sign in.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className={styles.wrap}>
      <section className={styles.brand} aria-label="About TrueBind">
        <div className={styles.logo}><span className={styles.mark}>TB</span>TrueBind</div>
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
          <h2 className={styles.title}>{mode === "login" ? "Sign in" : "Create your workspace"}</h2>
          <p className={styles.sub}>{mode === "login" ? "Welcome back." : "Your organisation gets its own isolated workspace."}</p>
          {error && <AlertBanner tone="error" title={mode === "login" ? "Sign-in failed" : "Sign-up failed"}>{error}</AlertBanner>}
          <form onSubmit={submit} className={styles.form} noValidate={false}>
            {mode === "signup" && (
              <>
                <label className={styles.label}>Your name<input className={styles.input} value={name} onChange={(e) => setName(e.target.value)} required maxLength={200} autoComplete="name" /></label>
                <label className={styles.label}>Organisation<input className={styles.input} value={org} onChange={(e) => setOrg(e.target.value)} required maxLength={200} autoComplete="organization" /></label>
              </>
            )}
            <label className={styles.label}>Work e-mail<input className={styles.input} type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" autoFocus /></label>
            <label className={styles.label}>Password<input className={styles.input} type="password" value={password} onChange={(e) => setPassword(e.target.value)} required
              minLength={mode === "signup" ? 12 : 1} autoComplete={mode === "login" ? "current-password" : "new-password"} aria-describedby={mode === "signup" ? "pw-hint" : undefined} /></label>
            {mode === "signup" && <small id="pw-hint" className={styles.hint}>At least 12 characters.</small>}
            <Button type="submit" loading={busy} style={{ width: "100%", minHeight: 42 }}>{mode === "login" ? "Sign in" : "Create account"}</Button>
          </form>
          <p className={styles.switch}>
            <button type="button" className={styles.link} onClick={() => { setMode(mode === "login" ? "signup" : "login"); setError(null); }}>
              {mode === "login" ? "Need an account? Sign up" : "Have an account? Sign in"}
            </button>
          </p>
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
