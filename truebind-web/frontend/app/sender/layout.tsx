"use client";

import { AuthGate, useMe } from "@/components/auth/AuthGate";
import { ToastProvider } from "@/components/ds/overlays";
import { BrandMark } from "@/components/layout/BrandMark";
import { api } from "@/lib/api";
import styles from "./sender.module.css";

/** The sender portal has its own, narrow shell: a coverholder or TPA user
 * sees their pre-flight checks and submissions, nothing of the provider's. */
function signOut() {
  // Full navigation on sign-out so no signed-in state survives in memory.
  // eslint-disable-next-line @next/next/no-location-assign-relative-destination
  api.logout().finally(() => window.location.assign("/login"));
}

function SenderShell({ children }: { children: React.ReactNode }) {
  const me = useMe();
  return (
    <ToastProvider>
      <header className={styles.bar}>
        <span className={styles.brand}><BrandMark /> TrueBind · sender portal</span>
        <span className={styles.who}>{me?.user.email} · sending to {me?.tenant.name}</span>
        <a className={styles.link} href="/settings?tab=security">Security</a>
        <button type="button" className={styles.link} onClick={signOut}>Sign out</button>
      </header>
      <main className={styles.main}>{children}</main>
    </ToastProvider>
  );
}

export default function SenderLayout({ children }: { children: React.ReactNode }) {
  return <AuthGate><SenderShell>{children}</SenderShell></AuthGate>;
}
