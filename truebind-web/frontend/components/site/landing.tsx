"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowCounterClockwise, ArrowRight } from "@phosphor-icons/react";
import { HeroSheet, STAGES, useHeroStage } from "./hero-sheet";
import { SiteFooter, SiteNav } from "./chrome";
import { LeadButton } from "./lead-form";

type Cell = { t: string; k?: "r" | "a" };
const RED = { bg: "oklch(0.94 0.045 25)", fg: "oklch(0.48 0.17 25)" };
const AMB = { bg: "oklch(0.95 0.06 85)", fg: "oklch(0.46 0.1 70)" };
const c = (t: string, k?: "r" | "a"): Cell => ({ t, k });

const SENDERS3 = [
  { name: "Harbour MGA", fmt: "Claims_Aug26_FINAL_v3.xlsx", rot: -1.2, h: ["Clm No.", "DOL", "Paid £", "Total Inc"], rows: [[c("HBR-0004"), c("12/05/2026"), c("18,400.00"), c("24,500.00")], [c("HBR-0008"), c("04/06/2026"), c("9,800.00"), c("15,000.00", "r")], [c("HBR-0011"), c("", "r"), c("1,120.00"), c("2,000.00")]], issue: "Incurred doesn’t add up · loss date missing" },
  { name: "Kestrel TPA", fmt: "bdx_0826.csv", rot: 0.8, h: ["CLAIM_ID", "LOSS_DT", "PAID_TD", "INC_TOT"], rows: [[c("KT-22817"), c("2026-05-19"), c("12812"), c("49898")], [c("KT-22817", "a"), c("2026-05-19", "a"), c("12812", "a"), c("49898", "a")], [c("KT-22840"), c("2026-06-02"), c("640"), c("2000")]], issue: "Same row sent twice · no reporting period" },
  { name: "Norland Claims", fmt: "Norland Aug.xlsx · 3 sheets", rot: -0.5, h: ["Claim Reference", "Date of Loss", "Paid to Date", "Incurred"], rows: [[c("NC/3391"), c("06/28/2026", "a"), c("£2,480"), c("£38,980")], [c("NC/3392"), c("28 Jun 26"), c("£0"), c("£132.50")], [c("NC/3395"), c("01.07.2026", "a"), c("£410"), c("£500")]], issue: "Three date formats in one column" },
];
const LOOP = ["Excel", "E-mail", "Manual review", "Carrier query", "Rework"];
const OK = "var(--ok)", WN = "var(--warn)", ER = "var(--err)", NA = "var(--faint)";
const STEPS = [
  { n: "01", name: "Map", d: "Columns matched to Lloyd’s CRS v5.2 by alias rules first. AI only proposes headers the rules can’t place — never cell values. You confirm before anything is validated.", ev: [["Clm No. → claim_reference", OK], ["LOSS_DT → date_of_loss", OK], ["Adj Notes → unmapped", NA]] },
  { n: "02", name: "Validate", d: "Arithmetic, required data, dates and formats checked on every row. Each finding cites its sheet, row, field and rule.", ev: [["row 5 · incurred 39,171.00 ≠ 37,671.00", ER], ["row 9 · insured name missing", ER], ["row 26 · 03/04/2026 ambiguous", WN]] },
  { n: "03", name: "Reconcile", d: "Exact resubmissions kept apart from legitimate claim development. Nothing is merged or removed automatically.", ev: [["HBR-0006 · rows 7 & 22 · exact", ER], ["HBR-0019 · Jul → Aug · development", OK]] },
  { n: "04", name: "Audit", d: "Every action, by a person or the system, is hash-chained. Any later edit or deletion breaks the chain and is detected.", ev: [["#112 workbook read · mapping proposed", OK], ["#113 mapping v3 confirmed by molly", OK], ["chain intact · 116 entries", OK]] },
];
const SHOTS = [
  ["Intake", "Any sender’s layout. Every sheet read, header rows found.", "/assets/app-intake.png", "/upload"],
  ["Work queue", "Everything waiting on a person, most urgent first.", "/assets/app-workqueue.png", "/todo"],
  ["Exceptions", "Each finding with evidence and the next step.", "/assets/app-exceptions.png", "/exceptions"],
  ["Duplicates", "Resubmissions separated from development.", "/assets/app-duplicates.png", "/duplicates"],
  ["Automations", "Live channels shown as live; planned as planned.", "/assets/app-automations.png", "/automations"],
  ["Audit trail", "Hash-chained. Nothing changed without a record.", "/assets/app-audit.png", "/audit"],
];

const kicker = "text-[12px] font-medium uppercase tracking-[.1em]";
const h2 = "m-0 text-[32px] font-medium leading-[1.1] tracking-[-0.025em] [text-wrap:balance] sm:text-[40px]";
const rule = "linear-gradient(to right, transparent, var(--line2) 48px, var(--line2) calc(100% - 48px), transparent)";

export function Landing() {
  const { stage, setStage } = useHeroStage();
  const [shot, setShot] = useState(0);

  return (
    <div className="min-h-screen overflow-hidden" style={{ background: "var(--chrome)", color: "var(--chromeStrong)" }}>
      <SiteNav />

      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      {/* Side by side from 1024px; the headline and the workbook both scale with
          the viewport (clamp + HeroSheet's own fit-to-width), stacking only below lg. */}
      <section className="relative mx-auto grid max-w-[1320px] items-start gap-10 px-4 pb-[72px] pt-[120px] sm:px-8 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-[clamp(24px,3vw,48px)] lg:px-[clamp(32px,3.5vw,48px)] lg:pt-[clamp(110px,11vh,150px)]">
        <div className="pointer-events-none absolute inset-y-0 -left-[50vw] -right-[50vw]" style={{ background: "radial-gradient(760px 520px at 60% 40%, var(--heroGlowA), transparent 70%), radial-gradient(640px 420px at 31% 0%, var(--heroGlowB), transparent 70%)" }} />
        <div className="relative flex max-w-[560px] flex-col gap-[clamp(16px,2vw,24px)] lg:max-w-[460px] lg:pt-[clamp(8px,3vh,40px)]">
          <span className={kicker} style={{ color: "var(--kicker)" }}>Claims bordereaux integrity</span>
          <h1 className="m-0 text-[clamp(38px,4.1vw,58px)] font-medium leading-[1.04] tracking-[-0.035em] [text-wrap:balance]">Clean claims data. Before it becomes a problem.</h1>
          <p className="m-0 text-[clamp(15.5px,1.2vw,17px)] leading-[1.6] [text-wrap:pretty]" style={{ color: "var(--chromeMuted)" }}>
            TrueBind maps, validates and reconciles claims bordereaux before they reach carriers, giving teams clear evidence of what was checked and what was not.
          </p>
          <div className="flex flex-wrap gap-2.5">
            <a href="#health" className="whitespace-nowrap rounded-lg px-[18px] py-[13px] text-[14.5px] font-medium transition-colors hover:bg-[rgba(145,132,217,.22)]" style={{ color: "var(--accentText)", background: "rgba(145,132,217,.12)", boxShadow: "inset 0 0 0 1px var(--accent), 0 0 24px rgba(145,132,217,.18)" }}>
              Run a Bordereau Health Check
            </a>
            <Link href="/overview" className="whitespace-nowrap rounded-lg px-4 py-[13px] text-[14.5px] font-medium transition-colors hover:bg-[rgba(233,233,237,.06)]" style={{ boxShadow: "inset 0 0 0 1px var(--line2)" }}>
              See TrueBind in action
            </Link>
          </div>
          <div className="flex flex-col gap-2 pt-4 text-[13px] leading-[1.5]" style={{ color: "var(--muted)", background: `${rule} top / 100% 1px no-repeat` }}>
            <span>Works alongside your existing TPA files, inboxes and carrier templates.</span>
            <span>Source values are never rewritten. Unmapped and unassessed data is reported, not hidden.</span>
          </div>
        </div>

        <div className="relative flex min-w-0 flex-col gap-5">
          <HeroSheet stage={stage} />
          <div className="flex min-h-[22px] flex-wrap items-baseline gap-x-3.5 gap-y-1 px-1" aria-live="polite">
            <span className={`${kicker} whitespace-nowrap`} style={{ color: "var(--kicker)" }}>{STAGES[stage][0]}</span>
            <span className="text-[14.5px]" style={{ color: "var(--chromeText)" }}>{STAGES[stage][1]}</span>
          </div>
          <div className="grid grid-cols-3 gap-1 rounded-xl p-[5px] xl:grid-cols-6" style={{ background: "var(--glass)", backdropFilter: "blur(20px) saturate(160%)", boxShadow: "inset 0 1px 0 rgba(255,255,255,.1), 0 0 0 1px var(--glassRing)" }}>
            {STAGES.map(([label], i) => (
              <button
                key={label}
                type="button"
                onClick={() => setStage(i)}
                aria-pressed={i === stage}
                className="flex min-w-0 cursor-pointer items-center gap-2 whitespace-nowrap rounded-lg px-3 py-2.5 text-[13px] font-medium"
                style={{
                  background: i === stage ? "rgba(145,132,217,.16)" : "transparent",
                  boxShadow: i === stage ? "inset 0 0 0 1px rgba(145,132,217,.5)" : "none",
                  color: i === stage ? "var(--chromeStrong)" : i < stage ? "var(--chromeMuted)" : "var(--faint)",
                  transition: "background .5s, color .5s, box-shadow .5s",
                }}
              >
                <span className="tnum text-[10.5px] opacity-60">0{i}</span>
                {label}
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* ── Problem ──────────────────────────────────────────────────────── */}
      <section id="problem" className="mx-auto flex max-w-[1320px] scroll-mt-20 flex-col gap-10 px-4 py-[88px] sm:px-12">
        <div className="flex max-w-[700px] flex-col gap-3">
          <span className={kicker} style={{ color: "var(--kicker)" }}>The problem</span>
          <h2 className={h2}>Every sender has a format. Every format has its own mistakes.</h2>
        </div>
        <div className="grid gap-6" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(280px,1fr))" }}>
          {SENDERS3.map((s) => (
            <div key={s.name} className="flex flex-col gap-3" style={{ transform: `rotate(${s.rot}deg)` }}>
              <div className="flex justify-between text-[12.5px]">
                <span className="font-medium">{s.name}</span>
                <span style={{ color: "var(--faint)" }}>{s.fmt}</span>
              </div>
              <div className="overflow-hidden rounded-lg" style={{ background: "#f7f8f6", color: "#2a2f36", boxShadow: "0 20px 40px rgba(0,0,0,.3)" }}>
                <div className="grid" style={{ gridTemplateColumns: "repeat(4,minmax(0,1fr))", background: "oklch(0.96 0.02 150)", borderBottom: "1px solid #d5d9d3" }}>
                  {s.h.map((hh) => (
                    <div key={hh} className="overflow-hidden whitespace-nowrap px-2 py-[7px] text-[10.5px] font-semibold" style={{ borderRight: "1px solid #e1e4df" }}>{hh}</div>
                  ))}
                </div>
                {s.rows.map((r, i) => (
                  <div key={i} className="grid" style={{ gridTemplateColumns: "repeat(4,minmax(0,1fr))", borderBottom: "1px solid #e6e8e4" }}>
                    {r.map((cc, j) => (
                      <div key={j} className="tnum h-[29px] overflow-hidden whitespace-nowrap px-2 py-1.5 text-[10.5px]" style={{ borderRight: "1px solid #e6e8e4", background: cc.k === "r" ? RED.bg : cc.k === "a" ? AMB.bg : "transparent", color: cc.k === "r" ? RED.fg : cc.k === "a" ? AMB.fg : "#2a2f36" }}>{cc.t}</div>
                    ))}
                  </div>
                ))}
              </div>
              <span className="text-[12.5px]" style={{ color: "var(--muted)" }}>{s.issue}</span>
            </div>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2.5 pt-3">
          {LOOP.map((t, i) => (
            <div key={t} className="flex items-center gap-2.5">
              <span className="whitespace-nowrap rounded-lg px-3 py-2 text-[13.5px]" style={{ boxShadow: "inset 0 0 0 1px var(--line2)", color: "var(--chromeText)" }}>{t}</span>
              {i < LOOP.length - 1 && <ArrowRight size={14} style={{ color: "var(--chromeFaint)" }} />}
            </div>
          ))}
          <span className="flex items-center gap-1.5 text-[13.5px]" style={{ color: "var(--warn)" }}>
            <ArrowCounterClockwise />
            and back to the sender
          </span>
        </div>
        <p className="m-0 max-w-[640px] text-[15px]" style={{ color: "var(--muted)" }}>
          Today the first person to find the error is often the carrier — after the deadline, in a query, weeks after the file was sent.
        </p>
      </section>

      <div className="mx-auto h-px max-w-[1224px]" style={{ background: rule }} />

      {/* ── How it works ─────────────────────────────────────────────────── */}
      <section id="how" className="mx-auto flex max-w-[1320px] scroll-mt-20 flex-col gap-11 px-4 py-[88px] sm:px-12">
        <div className="flex max-w-[700px] flex-col gap-3">
          <span className={kicker} style={{ color: "var(--kicker)" }}>TrueBind</span>
          <h2 className={h2}>The same files. One audited path.</h2>
          <p className="m-0 text-[16px] leading-[1.6]" style={{ color: "var(--chromeMuted)" }}>Every file, from any sender or channel, runs the same steps. Each step leaves evidence.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {["Harbour MGA · xlsx", "Kestrel TPA · csv", "Norland Claims · 3 sheets"].map((t) => (
            <span key={t} className="rounded-md px-2.5 py-1.5 text-[12px]" style={{ background: "var(--surface)", color: "var(--chromeText)" }}>{t}</span>
          ))}
        </div>
        <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(250px,1fr))", borderTop: "1px solid var(--accent)" }}>
          {STEPS.map((p) => (
            <div key={p.n} className="flex flex-col gap-3 pb-6 pr-6 pt-6">
              <span className="-mt-[29px] mb-2 h-[9px] w-[9px] rounded-full" style={{ background: "var(--accent)", boxShadow: "0 0 12px rgba(145,132,217,.6)" }} />
              <div className="flex items-baseline gap-2.5">
                <span className="tnum text-[12px]" style={{ color: "var(--faint)" }}>{p.n}</span>
                <span className="text-[22px] font-medium tracking-[-0.015em]">{p.name}</span>
              </div>
              <p className="m-0 text-[14px] leading-[1.6] [text-wrap:pretty]" style={{ color: "var(--chromeMuted)" }}>{p.d}</p>
              <div className="flex flex-col gap-1.5 rounded-lg px-3.5 py-3" style={{ background: "var(--bg2)", boxShadow: "0 0 0 1px var(--line)" }}>
                {p.ev.map(([t, col]) => (
                  <div key={t} className="tnum flex items-center gap-2 text-[12px]" style={{ color: "var(--chromeText)" }}>
                    <span className="h-1.5 w-1.5 flex-none rounded-full" style={{ background: col }} />
                    {t}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      <div className="mx-auto h-px max-w-[1224px]" style={{ background: rule }} />

      {/* ── Product ──────────────────────────────────────────────────────── */}
      <section id="product" className="mx-auto flex max-w-[1320px] scroll-mt-20 flex-col gap-9 px-4 py-[88px] sm:px-12">
        <div className="flex flex-wrap items-end justify-between gap-5">
          <div className="flex max-w-[640px] flex-col gap-3">
            <span className={kicker} style={{ color: "var(--kicker)" }}>Product</span>
            <h2 className={h2}>The application, not an illustration of it.</h2>
          </div>
          <Link href="/overview" className="whitespace-nowrap rounded-lg px-4 py-[11px] text-[14px] font-medium transition-colors hover:bg-[rgba(145,132,217,.16)]" style={{ color: "var(--accentText)", boxShadow: "inset 0 0 0 1px var(--accent)" }}>
            Open the product →
          </Link>
        </div>
        <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-8 lg:grid-cols-[minmax(200px,260px)_minmax(0,1fr)]">
          <div className="-mx-4 flex snap-x snap-mandatory scroll-px-4 gap-0.5 overflow-x-auto px-4 [scrollbar-width:none] lg:mx-0 lg:snap-none lg:flex-col lg:px-0" role="tablist" aria-label="Product screens">
            {SHOTS.map(([label, d], i) => (
              <button
                key={label}
                role="tab"
                aria-selected={i === shot}
                type="button"
                onClick={() => setShot(i)}
                className="flex min-w-[min(240px,72vw)] snap-start cursor-pointer flex-col gap-[3px] rounded-lg px-3.5 py-3 text-left lg:min-w-0"
                style={{ background: i === shot ? "rgba(145,132,217,.10)" : "transparent", boxShadow: i === shot ? "inset 2px 0 0 var(--accent)" : "none" }}
              >
                <span className="text-[14.5px] font-medium" style={{ color: i === shot ? "var(--chromeStrong)" : "var(--chromeText)" }}>{label}</span>
                <span className="text-[12.5px] leading-[1.45]" style={{ color: "var(--muted)" }}>{d}</span>
              </button>
            ))}
          </div>
          <Link
            href={SHOTS[shot][3]}
            className="group block rounded-[14px] p-2.5"
            style={{ background: "var(--glass)", boxShadow: "inset 0 1px 0 rgba(255,255,255,.08), 0 0 0 1px var(--glassRing), 0 40px 80px rgba(0,0,0,.35)" }}
            aria-label={`Open ${SHOTS[shot][0]} in the product`}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img key={shot} src={SHOTS[shot][2]} alt={`TrueBind ${SHOTS[shot][0]}`} className="anim-fade w-full rounded-lg transition-opacity group-hover:opacity-95" />
          </Link>
        </div>
        <span className="text-[12px]" style={{ color: "var(--faint)" }}>Current TrueBind build, captured September 2026. Sign in to open it.</span>
      </section>

      {/* ── Health Check ─────────────────────────────────────────────────── */}
      <section id="health" className="scroll-mt-16" style={{ background: "var(--section)", backgroundImage: "radial-gradient(800px 400px at 80% 0%, var(--sectionGlow), transparent 70%)" }}>
        <div className="mx-auto flex max-w-[1320px] flex-wrap items-center justify-between gap-12 px-4 py-20 sm:px-12">
          <div className="flex max-w-[560px] flex-[1_1_420px] flex-col gap-[18px]">
            <span className={kicker} style={{ color: "var(--accentText)" }}>Bordereau Health Check</span>
            <h2 className={h2}>Send one bordereau. Get back a report you can forward.</h2>
            <p className="m-0 text-[16px] leading-[1.6]" style={{ color: "var(--chromeText)" }}>
              What was checked, what was flagged, what couldn’t be mapped and what wasn’t assessed — with the evidence. Ready for your COO, Head of Claims, carrier or auditor.
            </p>
            <div className="flex flex-wrap gap-2.5">
              <LeadButton kind="health" className="whitespace-nowrap rounded-lg px-[18px] py-[13px] text-[14.5px] font-medium transition-colors hover:bg-[rgba(245,244,255,.08)]" style={{ boxShadow: "inset 0 0 0 1px var(--accentText)" }}>
                Run a Bordereau Health Check
              </LeadButton>
              <Link href="/sample-report" className="whitespace-nowrap px-1.5 py-[13px] text-[14.5px]" style={{ color: "var(--accentText)" }}>
                See a sample report →
              </Link>
            </div>
          </div>
          <div className="flex max-w-[520px] flex-[1_1_420px] flex-col gap-[18px]">
            <div className="flex h-2.5 gap-0.5 overflow-hidden rounded-[3px]">
              <div style={{ width: "92%", background: "oklch(0.76 0.12 155)" }} />
              <div style={{ width: "4%", background: "oklch(0.81 0.12 75)" }} />
              <div style={{ width: "2%", background: "repeating-linear-gradient(45deg,var(--chromeText) 0 2px,transparent 2px 4px)" }} />
              <div style={{ width: "2%", background: "var(--chromeFaint)" }} />
            </div>
            <div className="grid grid-cols-4 gap-3">
              {[["1,259", "Checked"], ["23", "Flagged"], ["1", "Unmapped"], ["2", "Not assessed"]].map(([v, l]) => (
                <div key={l} className="flex flex-col gap-1">
                  <span className="tnum text-[24px] font-medium sm:text-[30px]">{v}</span>
                  <span className="text-[12.5px]" style={{ color: "var(--chromeText)" }}>{l}</span>
                </div>
              ))}
            </div>
            <span className="text-[12px]" style={{ color: "var(--accentText)" }}>Sample: Harbour MGA · Claims Aug-26 · 1,284 rows · 3m 12s</span>
          </div>
        </div>
      </section>

      <SiteFooter />
    </div>
  );
}
