"use client";

import { useEffect, useState } from "react";
import QRCode from "qrcode";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { AlertBanner } from "@/components/ui/Alert";
import { ErrorState, Panel, Pill, SkeletonRows, useToast } from "@/components/ds";
import { Button } from "@/components/ui/Button";
import styles from "./settings.module.css";

function QrCode({ value }: { value: string }) {
  const [svg, setSvg] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    QRCode.toString(value, { type: "svg", margin: 0, errorCorrectionLevel: "M" })
      .then((s) => { if (live) setSvg(s); })
      .catch(() => { if (live) setSvg(null); });
    return () => { live = false; };
  }, [value]);
  // The SVG is generated locally from our own otpauth URI (no user HTML).
  return <div className={styles.qr} role="img" aria-label="QR code for your authenticator app" dangerouslySetInnerHTML={svg ? { __html: svg } : undefined} />;
}

export function SecuritySettings({ required }: { required: boolean }) {
  const toast = useToast();
  const status = useApi(() => api.mfaStatus());
  const [setup, setSetup] = useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [code, setCode] = useState("");
  const [codes, setCodes] = useState<string[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setErr(null);
    try {
      await fn();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  if (status.error) return <ErrorState title="Security settings could not be loaded" message={status.error} onRetry={status.reload} />;
  if (!status.data) return <Panel title="Two-step verification"><SkeletonRows rows={3} /></Panel>;
  const s = status.data;

  return (
    <Panel title="Two-step verification" icon="shield"
      subtitle="A code from an authenticator app (Microsoft Authenticator, Google Authenticator, 1Password…) in addition to your password."
      actions={<Pill tone={s.enabled ? "good" : "warn"}>{s.enabled ? "On" : "Off"}</Pill>}>
      <div className={styles.form}>
        {required && s.setup_required && (
          <AlertBanner tone="warning" title="Your organisation requires two-step verification">Set it up to continue using TrueBind.</AlertBanner>
        )}
        {err && <AlertBanner tone="error" title="Not done">{err}</AlertBanner>}

        {codes && (
          <>
            <AlertBanner tone="success" title="Two-step verification is on">Your other sessions were signed out. Save these recovery codes somewhere safe: each works once, and they are shown only now.</AlertBanner>
            <ul className={styles.codes} data-testid="recovery-codes">{codes.map((c) => <li key={c} className={styles.codeBox}>{c}</li>)}</ul>
            <div className={styles.actions}><Button onClick={() => { setCodes(null); status.reload(); }}>I have saved them</Button></div>
          </>
        )}

        {!codes && !s.enabled && !setup && (
          <div className={styles.actions}>
            <Button loading={busy} onClick={() => run(async () => { setSetup(await api.mfaSetup()); })}>Set up two-step verification</Button>
          </div>
        )}

        {!codes && !s.enabled && setup && (
          <form onSubmit={(e) => { e.preventDefault(); void run(async () => { setCodes((await api.mfaEnable(code.replace(/\s/g, ""))).recovery_codes); setSetup(null); setCode(""); }); }}>
            <div className={styles.setup}>
              <QrCode value={setup.otpauth_uri} />
              <div className={styles.form}>
                <p className={styles.muted}>1. Scan the code with your authenticator app, or enter this key:</p>
                <p className={styles.codeBox} data-testid="totp-secret">{setup.secret}</p>
                <label className={styles.field}>2. Enter the 6-digit code it shows
                  <input className={styles.input} value={code} onChange={(e) => setCode(e.target.value)} inputMode="numeric" autoComplete="one-time-code" required pattern="[0-9 ]{6,8}" />
                </label>
                <div className={styles.actions}><Button type="submit" loading={busy}>Turn on</Button><Button type="button" variant="ghost" onClick={() => setSetup(null)}>Cancel</Button></div>
              </div>
            </div>
          </form>
        )}

        {!codes && s.enabled && (
          s.required ? <p className={styles.muted}>Your organisation requires two-step verification, so it cannot be turned off.</p> : (
            <form className={styles.form} onSubmit={(e) => { e.preventDefault(); void run(async () => { await api.mfaDisable(code.replace(/\s/g, "")); setCode(""); status.reload(); toast({ tone: "info", title: "Two-step verification is off" }); }); }}>
              <label className={styles.field}>To turn it off, enter a current code or a recovery code
                <input className={styles.input} value={code} onChange={(e) => setCode(e.target.value)} required autoComplete="one-time-code" />
              </label>
              <div className={styles.actions}><Button type="submit" variant="secondary" loading={busy}>Turn off</Button></div>
            </form>
          )
        )}
      </div>
    </Panel>
  );
}
