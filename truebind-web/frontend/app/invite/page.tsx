"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { AlertBanner } from "@/components/ui/Alert";
import { BrandMark } from "@/components/layout/BrandMark";
import styles from "../login/login.module.css";

/** Accept an invitation. New people choose a name and password; people who
 * already have a TrueBind account confirm with their existing password. */
function AcceptForm() {
  const router = useRouter();
  const params = useSearchParams();
  const token = params.get("token") ?? "";
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(token ? null : "This link has no invitation token. Ask for a new invitation.");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const me = await api.acceptInvitation(token, name || "New member", password);
      router.replace(me.role === "SENDER" ? "/sender" : "/overview");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The invitation could not be accepted.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className={styles.wrap}>
      <section className={styles.brand} aria-label="About TrueBind">
        <div className={styles.logo}><BrandMark size={32} />TrueBind</div>
        <h1 className={styles.headline}>You&rsquo;ve been invited.</h1>
        <p className={styles.lede}>Join your organisation&rsquo;s TrueBind workspace. Your role was chosen by the person who invited you and can be changed by an administrator.</p>
      </section>
      <section className={styles.formSide}>
        <div className={styles.card}>
          <h2 className={styles.title}>Accept invitation</h2>
          <p className={styles.sub}>Already have a TrueBind account? Use your existing password; your name is kept.</p>
          {error && <AlertBanner tone="error" title="Could not join">{error}</AlertBanner>}
          <form onSubmit={submit} className={styles.form}>
            <label className={styles.label}>Your name<input className={styles.input} value={name} onChange={(e) => setName(e.target.value)} maxLength={200} autoComplete="name" autoFocus /></label>
            <label className={styles.label}>Password<input className={styles.input} type="password" value={password} onChange={(e) => setPassword(e.target.value)} required
              autoComplete="new-password" aria-describedby="pw-hint" /></label>
            <small id="pw-hint" className={styles.hint}>New accounts need at least 12 characters.</small>
            <Button type="submit" loading={busy} disabled={!token} style={{ width: "100%", minHeight: 42 }}>Join workspace</Button>
          </form>
        </div>
      </section>
    </main>
  );
}

export default function InvitePage() {
  return <Suspense fallback={null}><AcceptForm /></Suspense>;
}
