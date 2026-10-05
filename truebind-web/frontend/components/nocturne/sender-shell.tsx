"use client";

import Link from "next/link";
import { SignOut } from "@phosphor-icons/react";
import { useMe } from "@/components/auth/AuthGate";
import { api } from "@/lib/api";
import { Brand } from "./ui";

function signOut() {
  // Full navigation on sign-out so no signed-in state survives in memory.
  // eslint-disable-next-line @next/next/no-location-assign-relative-destination
  api.logout().finally(() => window.location.assign("/login"));
}

/** The sender portal's own, narrow shell: a coverholder or TPA user sees their
 * pre-flight checks, submissions and security settings, nothing of the provider's. */
export function SenderShell({ children }: { children: React.ReactNode }) {
  const me = useMe();
  return (
    <div className="min-h-screen" style={{ background: "var(--bg)", color: "var(--text)" }}>
      <header
        className="sticky top-0 z-20 flex flex-wrap items-center gap-x-3 gap-y-1 px-4 pb-2.5 pt-[max(10px,env(safe-area-inset-top))] sm:flex-nowrap sm:gap-x-5 sm:px-6"
        style={{ background: "color-mix(in srgb, var(--bg) 85%, transparent)", boxShadow: "0 1px 0 var(--line)" }}
      >
        <Link href="/sender" className="flex flex-none items-center gap-2 text-[14px]">
          <Brand size={24} />
          <span className="hidden min-[400px]:inline" style={{ color: "var(--faint)" }}>· sender portal</span>
        </Link>
        <span className="order-last min-w-0 basis-full truncate text-[12.5px] sm:order-none sm:flex-1 sm:basis-auto" style={{ color: "var(--muted)" }}>
          {me?.user.email} · sending to {me?.tenant.name}
        </span>
        <span className="flex-1 sm:hidden" />
        <Link href="/settings?tab=security" className="tb-btn tb-btn-ghost !px-2 !py-1.5 text-[13px]">Security</Link>
        <button type="button" className="tb-btn !px-2.5 !py-1.5 text-[13px]" onClick={signOut} aria-label="Sign out">
          <SignOut size={16} />
          <span className="hidden min-[400px]:inline">Sign out</span>
        </button>
      </header>
      <main>{children}</main>
    </div>
  );
}
