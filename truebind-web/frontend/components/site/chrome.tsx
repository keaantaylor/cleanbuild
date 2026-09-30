"use client";

import Link from "next/link";
import { useState } from "react";
import { List, X } from "@phosphor-icons/react";
import { Brand, Mark, ThemeToggle } from "@/components/nocturne/ui";

const LINKS = [
  ["Why", "/#problem"],
  ["How it works", "/#how"],
  ["Product", "/#product"],
  ["Health Check", "/#health"],
];

/** The prototype's floating glass pill nav. */
export function SiteNav() {
  const [open, setOpen] = useState(false);
  return (
    // The wrapper is zero-height so the pill floats over the hero; items-start stops
    // the pill being stretched to that zero height (the pill sizes to its content).
    <div className="no-print sticky top-[calc(20px+env(safe-area-inset-top))] z-20 flex h-0 items-start justify-center px-3 sm:px-5">
      <nav
        className="flex h-[52px] w-full max-w-max flex-none items-center gap-2 whitespace-nowrap rounded-full pl-4 pr-2 min-[375px]:gap-3 min-[375px]:pl-5 lg:gap-8"
        style={{
          background: "var(--glass)",
          backdropFilter: "blur(24px) saturate(170%)",
          WebkitBackdropFilter: "blur(24px) saturate(170%)",
          boxShadow: "inset 0 1px 0 rgba(255,255,255,.12), 0 0 0 1px var(--glassRing), 0 12px 32px rgba(0,0,0,.28)",
          color: "var(--chromeStrong)",
        }}
      >
        <Link href="/" className="flex h-9 items-center text-[15px]" aria-label="TrueBind home">
          <Brand />
        </Link>
        <div className="hidden items-center gap-6 text-[13.5px] lg:flex" style={{ color: "var(--chromeMuted)" }}>
          {LINKS.map(([l, h]) => (
            <a key={h} href={h} className="flex h-9 items-center transition-colors hover:text-[var(--chromeStrong)]">
              {l}
            </a>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-1">
          <span className="contents max-[359px]:hidden"><ThemeToggle className="!h-9 !w-9 !rounded-full" style={{ color: "var(--chromeMuted)" }} /></span>
          <Link href="/login" className="hidden h-9 items-center rounded-full px-3 text-[13.5px] transition-colors hover:text-[var(--chromeStrong)] sm:flex" style={{ color: "var(--chromeMuted)" }}>
            Sign in
          </Link>
          <Link
            href="/onboarding"
            className="flex h-9 items-center rounded-full px-4 text-[13.5px] font-medium transition-colors hover:bg-[rgba(145,132,217,.16)]"
            style={{ color: "var(--accentText)", boxShadow: "inset 0 0 0 1px var(--accent)" }}
          >
            Book a demo
          </Link>
          <button type="button" className="grid h-9 w-9 place-items-center rounded-full lg:hidden" aria-label={open ? "Close menu" : "Open menu"} aria-expanded={open} onClick={() => setOpen((o) => !o)} style={{ color: "var(--chromeMuted)" }}>
            {open ? <X size={17} /> : <List size={17} />}
          </button>
        </div>
      </nav>
      {open && (
        <div
          className="anim-pop absolute left-4 right-4 top-[62px] flex flex-col rounded-2xl p-2 lg:hidden"
          style={{ background: "var(--popover)", backdropFilter: "blur(24px)", boxShadow: "0 0 0 1px var(--glassRing), 0 16px 40px rgba(0,0,0,.35)" }}
        >
          {[...LINKS, ["Sign in", "/login"]].map(([l, h]) => (
            <a key={h} href={h} onClick={() => setOpen(false)} className="rounded-lg px-3 py-2.5 text-[14px] hover:bg-[var(--accentTint)]" style={{ color: "var(--chromeStrong)" }}>
              {l}
            </a>
          ))}
        </div>
      )}
    </div>
  );
}

export function SiteFooter() {
  return (
    <footer className="mx-auto flex max-w-[1320px] flex-wrap justify-between gap-5 px-4 pb-12 pt-9 text-[12.5px] sm:px-12" style={{ color: "var(--faint)" }}>
      <Link href="/" className="flex items-center gap-[9px] font-medium" style={{ color: "var(--chromeMuted)" }}>
        <Mark size={20} radius={5} />
        TrueBind
      </Link>
      <div className="flex flex-wrap gap-x-6 gap-y-2">
        <Link href="/security" className="hover:text-[var(--chromeStrong)]">Security</Link>
        <Link href="/crs" className="hover:text-[var(--chromeStrong)]">Lloyd’s CRS v5.2</Link>
        <Link href="/privacy" className="hover:text-[var(--chromeStrong)]">Privacy</Link>
        <a href="mailto:hello@truebind.ie" className="hover:text-[var(--chromeStrong)]">hello@truebind.ie</a>
        <span>© 2026 TrueBind</span>
      </div>
    </footer>
  );
}
