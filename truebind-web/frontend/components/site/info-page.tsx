"use client";

import Link from "next/link";
import { SiteFooter, SiteNav } from "./chrome";

export function InfoPage({ kicker, title, intro, sections }: { kicker: string; title: string; intro: string; sections: { h: string; p: string[] }[] }) {
  return (
    <div className="min-h-screen" style={{ background: "var(--chrome)", color: "var(--chromeStrong)" }}>
      <SiteNav />
      <main className="mx-auto flex max-w-[760px] flex-col gap-10 px-4 pb-20 pt-[140px] sm:px-6">
        <div className="flex flex-col gap-3">
          <span className="text-[12px] font-medium uppercase tracking-[.1em]" style={{ color: "var(--kicker)" }}>{kicker}</span>
          <h1 className="m-0 text-[40px] font-medium leading-[1.08] tracking-[-0.03em]">{title}</h1>
          <p className="m-0 text-[17px] leading-[1.6]" style={{ color: "var(--chromeMuted)" }}>{intro}</p>
        </div>
        {sections.map((s) => (
          <section key={s.h} className="flex flex-col gap-3">
            <h2 className="m-0 text-[20px] font-medium tracking-[-0.015em]">{s.h}</h2>
            {s.p.map((p, i) => (
              <p key={i} className="m-0 text-[15px] leading-[1.65]" style={{ color: "var(--chromeText)" }}>{p}</p>
            ))}
          </section>
        ))}
        <div className="flex flex-wrap gap-3 pt-2">
          <Link href="/onboarding" className="tb-btn tb-btn-primary">Book a demo</Link>
          <a href="mailto:hello@truebind.ie" className="tb-btn">Email hello@truebind.ie</a>
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}
