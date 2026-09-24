"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { AlertBanner } from "@/components/ui/Alert";

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
      router.replace(next && next.startsWith("/") && !next.startsWith("//") ? next : "/upload");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not sign in.");
    } finally {
      setBusy(false);
    }
  }

  const field = { display: "block", width: "100%", padding: "10px 12px", marginTop: 6, borderRadius: 8, border: "1px solid #c9ced6", font: "inherit" } as const;
  return (
    <main style={{ maxWidth: 400, margin: "10vh auto", padding: 24 }}>
      <h1 style={{ marginBottom: 4 }}>TrueBind</h1>
      <p style={{ marginTop: 0, opacity: 0.7 }}>{mode === "login" ? "Sign in to continue" : "Create an account"}</p>
      {error && <AlertBanner tone="error" title={mode === "login" ? "Sign-in failed" : "Sign-up failed"}>{error}</AlertBanner>}
      <form onSubmit={submit} style={{ display: "grid", gap: 14, marginTop: 16 }}>
        {mode === "signup" && (
          <>
            <label>Your name<input style={field} value={name} onChange={(e) => setName(e.target.value)} required maxLength={200} autoComplete="name" /></label>
            <label>Organisation<input style={field} value={org} onChange={(e) => setOrg(e.target.value)} required maxLength={200} autoComplete="organization" /></label>
          </>
        )}
        <label>Email<input style={field} type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" /></label>
        <label>Password<input style={field} type="password" value={password} onChange={(e) => setPassword(e.target.value)} required
          minLength={mode === "signup" ? 12 : 1} autoComplete={mode === "login" ? "current-password" : "new-password"} /></label>
        {mode === "signup" && <small style={{ opacity: 0.7 }}>At least 12 characters.</small>}
        <Button type="submit" disabled={busy}>{busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}</Button>
      </form>
      <p style={{ marginTop: 16 }}>
        <button type="button" onClick={() => { setMode(mode === "login" ? "signup" : "login"); setError(null); }}
          style={{ background: "none", border: 0, color: "inherit", textDecoration: "underline", cursor: "pointer", padding: 0 }}>
          {mode === "login" ? "Need an account? Sign up" : "Have an account? Sign in"}
        </button>
      </p>
    </main>
  );
}

export default function LoginPage() {
  return <Suspense fallback={null}><LoginForm /></Suspense>;
}
