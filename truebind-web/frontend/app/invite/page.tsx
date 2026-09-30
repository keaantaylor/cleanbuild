"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { SignIn } from "@phosphor-icons/react";
import { api, ApiError } from "@/lib/api";
import { AuthShell, Field, FormError } from "@/components/nocturne/auth-shell";

export default function InvitePage() {
  return (
    <Suspense>
      <AcceptInvitation />
    </Suspense>
  );
}

/** New people choose a name and password; people who already have a TrueBind
 * account confirm with their existing password (their name is kept). */
function AcceptInvitation() {
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
      const me = await api.acceptInvitation(token, name.trim() || "New member", password);
      router.replace(me.role === "SENDER" ? "/sender" : "/overview");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The invitation could not be accepted.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell intro={{ kicker: "You’ve been invited", body: "Join your organisation’s TrueBind workspace. Your role was chosen by the person who invited you and can be changed by an administrator." }}>
      <div className="mb-8 flex flex-col gap-2">
        <span className="kicker">Invitation</span>
        <h1 className="m-0 text-[30px] font-medium tracking-[-0.02em]">Join your team on TrueBind</h1>
        <p className="m-0 text-[15px]" style={{ color: "var(--muted)" }}>Already have a TrueBind account? Enter your existing password; your name is kept.</p>
      </div>
      <form className="flex flex-col gap-5" onSubmit={submit}>
        {error && <FormError>{error}</FormError>}
        <Field label="Your name" id="iv-name">
          <input id="iv-name" className="tb-input" value={name} onChange={(e) => setName(e.target.value)} maxLength={200} autoComplete="name" autoFocus />
        </Field>
        <Field label="Password" id="iv-pw" hint="New accounts need at least 12 characters.">
          <input id="iv-pw" type="password" className="tb-input" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="new-password" />
        </Field>
        <div className="flex flex-wrap items-center gap-3">
          <button type="submit" className="tb-btn tb-btn-solid" disabled={busy || !token || !password}>
            <SignIn size={15} />
            {busy ? "Joining…" : "Join workspace"}
          </button>
          <Link href="/login" className="text-[13px] underline" style={{ color: "var(--accentText)" }}>
            Sign in instead
          </Link>
        </div>
      </form>
    </AuthShell>
  );
}
