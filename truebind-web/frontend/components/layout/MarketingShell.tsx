"use client";

import { List, X } from "@phosphor-icons/react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Button, ButtonLink, buttonClass, Logo } from "@/components/ds";
import { useSignedIn } from "@/components/site/chrome";
import { LeadButton } from "@/components/site/lead-form";
import s from "./MarketingShell.module.css";

const LINKS = [
  ["Why", "/#problem"],
  ["How it works", "/#how"],
  ["Product", "/#product"],
  ["Health Check", "/health-check"],
] as const;

const DEMO_URL = process.env.NEXT_PUBLIC_DEMO_URL;

/** Book a demo: the calendar link when configured, otherwise the on-page request form. */
function DemoButton({ className, block = false }: { className?: string; block?: boolean }) {
  if (DEMO_URL) {
    return (
      <ButtonLink href={DEMO_URL} variant="outline" size={40} className={className} style={block ? { width: "100%" } : undefined}>
        Book a demo
      </ButtonLink>
    );
  }
  return (
    <LeadButton kind="demo" className={buttonClass({ variant: "outline", size: 40, className })} style={block ? { width: "100%" } : undefined}>
      Book a demo
    </LeadButton>
  );
}

/** Dark marketing chrome from the landing mockup: floating pill nav and a one-line footer. */
export function MarketingShell({ children }: { children: React.ReactNode }) {
  const [scrolled, setScrolled] = useState(false);
  const sheet = useRef<HTMLDialogElement>(null);
  const path = usePathname();
  const signedIn = useSignedIn();
  const session = signedIn ? { label: "Open TrueBind", href: "/overview" } : { label: "Sign in", href: "/login" };

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  useEffect(() => {
    if (sheet.current?.open) sheet.current.close();
  }, [path]);

  return (
    <div className={s.root} data-theme="dark" data-marketing="">
      <a href="#main" className="sr-only-ds" onFocus={(e) => e.currentTarget.classList.remove("sr-only-ds")} onBlur={(e) => e.currentTarget.classList.add("sr-only-ds")}>
        Skip to content
      </a>
      <header className={`${s.header} ${scrolled ? s.scrolled : ""}`}>
        <nav className={s.bar} aria-label="Main">
          <Link href="/" className={s.brandLink} aria-label="TrueBind home">
            <Logo size={26} />
          </Link>
          <ul className={s.links}>
            {LINKS.map(([label, href]) => (
              <li key={href}>
                <Link href={href} className={s.link}>{label}</Link>
              </li>
            ))}
          </ul>
          <div className={s.grow} />
          <Link href={session.href} className={`${s.link} ${s.signIn}`}>{session.label}</Link>
          <DemoButton className={s.demo} />
          <Button variant="ghost" size={40} iconOnly className={s.menuBtn} aria-label="Open menu" onClick={() => sheet.current?.showModal()}>
            <List size={20} />
          </Button>
        </nav>
      </header>

      <dialog ref={sheet} className={s.sheet} aria-label="Menu">
        <div className={s.sheetHead}>
          <Logo size={26} />
          <Button variant="ghost" size={40} iconOnly aria-label="Close menu" onClick={() => sheet.current?.close()}>
            <X size={20} />
          </Button>
        </div>
        <ul className={s.sheetLinks}>
          {LINKS.map(([label, href]) => (
            <li key={href}>
              <Link href={href} onClick={() => sheet.current?.close()}>{label}</Link>
            </li>
          ))}
          <li>
            <Link href={session.href}>{session.label}</Link>
          </li>
        </ul>
        <div className={s.sheetActions}>
          <DemoButton block />
        </div>
      </dialog>

      <main id="main" tabIndex={-1} className={s.main}>
        {children}
      </main>

      <footer className={s.footer}>
        <div className={s.footInner}>
          <Logo size={22} />
          <ul className={s.footLinks}>
            <li><Link href="/security">Security</Link></li>
            <li><Link href="/crs">Lloyd&rsquo;s CRS v5.2</Link></li>
            <li><Link href="/privacy">Privacy</Link></li>
            <li>© 2026 TrueBind</li>
          </ul>
        </div>
      </footer>
    </div>
  );
}
