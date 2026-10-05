"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, mayHaveSession } from "@/lib/api";
import { List, X } from "@phosphor-icons/react";
import { Brand } from "@/components/nocturne/ui";
import { CONTACT_EMAIL } from "@/lib/constants";
import { LeadButton } from "./lead-form";

const LINKS = [
  ["How it works", "/#how"],
  ["Sample report", "/demo"],
  ["Pricing", "/pricing"],
  ["Security", "/security"],
];

/** True once /auth/me confirms this browser holds a live session. Public
 * pages only read the session; they never end it. */
export function useSignedIn(): boolean {
  const [signedIn, setSignedIn] = useState(false);
  useEffect(() => {
    if (!mayHaveSession()) return;
    let live = true;
    api.me().then(() => live && setSignedIn(true)).catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);
  return signedIn;
}

/** Public site header: a plain bar with a bottom border. */
export function SiteNav() {
  const [open, setOpen] = useState(false);
  const signedIn = useSignedIn();
  const session: [string, string] = signedIn ? ["Open TrueBind", "/overview"] : ["Sign in", "/login"];
  return (
    <>
      <a href="#main" className="sr-only z-[70] text-[13px] focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:px-3 focus:py-2" style={{ background: "var(--surface)", color: "var(--text)", outline: "2px solid var(--accent)" }}>Skip to content</a>
      <header className="no-print sticky top-0 z-20 border-b" style={{ background: "var(--surface)", borderColor: "var(--line)" }}>
        <nav className="mx-auto flex h-12 max-w-[1120px] items-center gap-6 px-4" aria-label="Main">
          <Link href={signedIn ? "/overview" : "/"} className="flex items-center text-[15px]" aria-label={signedIn ? "TrueBind overview" : "TrueBind home"}>
            <Brand size={22} />
          </Link>
          <div className="hidden items-center gap-5 text-[13.5px] md:flex" style={{ color: "var(--muted)" }}>
            {LINKS.map(([l, h]) => (
              <a key={h} href={h} className="hover:text-[var(--text)]">{l}</a>
            ))}
          </div>
          <div className="ml-auto flex items-center gap-2">
            <Link href={session[1]} className="hidden text-[13.5px] hover:text-[var(--text)] sm:block" style={{ color: "var(--muted)" }}>{session[0]}</Link>
            <LeadButton kind="demo" className="tb-btn tb-btn-solid">Book a demo</LeadButton>
            <button type="button" className="tb-btn !px-2 md:hidden" aria-label={open ? "Close menu" : "Open menu"} aria-expanded={open} onClick={() => setOpen((o) => !o)}>
              {open ? <X size={16} /> : <List size={16} />}
            </button>
          </div>
        </nav>
        {open && (
          <div className="flex flex-col border-t px-2 py-1 md:hidden" style={{ borderColor: "var(--line)", background: "var(--surface)" }}>
            {[...LINKS, session].map(([l, h]) => (
              <a key={h} href={h} onClick={() => setOpen(false)} className="px-2 py-2.5 text-[14px]" style={{ color: "var(--text)" }}>{l}</a>
            ))}
          </div>
        )}
      </header>
    </>
  );
}

export function SiteFooter() {
  return (
    <footer className="border-t" style={{ borderColor: "var(--line)", background: "var(--surface)" }}>
      <div className="mx-auto flex max-w-[1120px] flex-wrap items-center justify-between gap-4 px-4 py-6 text-[12.5px]" style={{ color: "var(--muted)" }}>
        <span>© 2026 TrueBind</span>
        <div className="flex flex-wrap gap-x-5 gap-y-2">
          <Link href="/security" className="hover:text-[var(--text)]">Security</Link>
          <Link href="/privacy" className="hover:text-[var(--text)]">Privacy</Link>
          <Link href="/crs" className="hover:text-[var(--text)]">Lloyd’s CRS v5.2</Link>
          <a href={`mailto:${CONTACT_EMAIL}`} className="hover:text-[var(--text)]">{CONTACT_EMAIL}</a>
        </div>
      </div>
    </footer>
  );
}
