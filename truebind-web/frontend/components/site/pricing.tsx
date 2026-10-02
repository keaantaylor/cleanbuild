"use client";

import Link from "next/link";
import { Check } from "@phosphor-icons/react";
import { SiteFooter, SiteNav } from "./chrome";
import { LeadButton } from "./lead-form";
import { ContactLine } from "./contact";

// [PRICE] placeholders are deliberate: prices are set after the first pilots.
const PLANS = [
  {
    name: "Founding pilot",
    price: "Free",
    per: "first file",
    lead: "Send us one real bordereau. We return everything below within one working day.",
    items: ["Health Check report with a clear verdict", "Your workbook, annotated cell by cell", "Corrected copy of the safe fixes, with a change log", "Query letter for the sender", "A 30-minute walkthrough"],
    cta: "health" as const,
    label: "Get a free Health Check",
    highlight: true,
  },
  {
    name: "Per file",
    price: "[PRICE]",
    per: "per bordereau",
    lead: "For firms sending a handful of bordereaux a month.",
    items: ["Everything in the Health Check, on demand", "Month-on-month check against last month’s file", "Up to [N] rows per file", "Files deleted after 30 days (you choose)"],
    cta: "demo" as const,
    label: "Talk to us",
  },
  {
    name: "Monthly",
    price: "[PRICE]",
    per: "per month",
    lead: "For coverholders, MGAs and TPAs with several binders or senders.",
    items: ["Unlimited files up to [N] rows a month", "Team accounts with roles and two-step verification", "Binder, leakage and sanctions checks", "Audit pack for every file"],
    cta: "demo" as const,
    label: "Talk to us",
  },
];

export function PricingPage() {
  return (
    <div className="min-h-screen" style={{ background: "var(--chrome)", color: "var(--chromeStrong)" }}>
      <SiteNav />
      <main id="main" className="mx-auto flex max-w-[1100px] flex-col gap-10 px-4 pb-20 pt-[130px] sm:px-6">
        <div className="flex max-w-[720px] flex-col gap-3">
          <span className="text-[12px] font-medium uppercase tracking-[.1em]" style={{ color: "var(--kicker)" }}>Pricing</span>
          <h1 className="m-0 text-[36px] font-medium leading-[1.1] tracking-[-0.03em] sm:text-[44px]">Priced for small teams. First file free.</h1>
          <p className="m-0 text-[16.5px] leading-[1.6]" style={{ color: "var(--chromeMuted)" }}>No integration project and no long contract: upload the file as it is. Prices below are being set with our founding pilots.</p>
        </div>
        <div className="grid gap-5 md:grid-cols-3">
          {PLANS.map((p) => (
            <div key={p.name} className="flex flex-col gap-4 rounded-xl p-6" style={{ background: p.highlight ? "var(--section)" : "transparent", boxShadow: p.highlight ? "inset 0 0 0 1px var(--accent)" : "inset 0 0 0 1px var(--line2)" }}>
              <span className="text-[15px] font-medium" style={{ color: p.highlight ? "var(--accentText)" : "var(--chromeStrong)" }}>{p.name}</span>
              <div className="flex items-baseline gap-2">
                <span className="tnum text-[34px] font-medium tracking-[-0.02em]">{p.price}</span>
                <span className="text-[13.5px]" style={{ color: "var(--chromeMuted)" }}>{p.per}</span>
              </div>
              <span className="text-[14px] leading-[1.55]" style={{ color: "var(--chromeText)" }}>{p.lead}</span>
              <ul className="m-0 flex flex-1 list-none flex-col gap-2 p-0 text-[14px]">
                {p.items.map((i) => (
                  <li key={i} className="flex gap-2" style={{ color: "var(--chromeText)" }}><Check size={16} className="mt-[3px] flex-none" style={{ color: "var(--ok)" }} />{i}</li>
                ))}
              </ul>
              <LeadButton kind={p.cta} className={p.highlight ? "tb-btn tb-btn-primary" : "tb-btn"}>{p.label}</LeadButton>
            </div>
          ))}
        </div>
        <ContactLine />
        <p className="m-0 text-[14px]" style={{ color: "var(--chromeMuted)" }}>
          Not sure yet? <Link href="/demo" className="underline" style={{ color: "var(--accentText)" }}>See a sample Health Check</Link> or read how we handle your data on the <Link href="/security" className="underline" style={{ color: "var(--accentText)" }}>security page</Link>.
        </p>
      </main>
      <SiteFooter />
    </div>
  );
}
