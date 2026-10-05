"use client";

import { useMe } from "@/components/auth/AuthGate";
import { ShellProvider } from "@/components/layout/ShellContext";
import { AppShell } from "@/components/layout/AppShell";
import { SenderShell } from "./sender-shell";

/** Senders only reach /settings inside this group (for their own security);
 * they get the narrow portal shell, which never polls the workspace APIs. */
export function DashboardShell({ children }: { children: React.ReactNode }) {
  const me = useMe();
  if (me?.role === "SENDER") return <SenderShell>{children}</SenderShell>;
  return (
    <ShellProvider>
      <AppShell>{children}</AppShell>
    </ShellProvider>
  );
}
