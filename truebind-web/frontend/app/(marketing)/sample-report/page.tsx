import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft } from "@phosphor-icons/react/dist/ssr";
import { Mark } from "@/components/nocturne/ui";
import { SiteFooter, SiteNav } from "@/components/site/chrome";

export const metadata: Metadata = { title: "Sample Health Check · TrueBind" };

/* A static, clearly labelled example of the Health Check document for the
   marketing site. It is not customer data and is never presented as such. */

const FINDINGS = [
  { sev: "Critical", c: "oklch(0.54 0.17 25)", check: "Required field missing", n: "4", ex: "HBR-0008 · insured name (CR0035M)", imp: "£38,980" },
  { sev: "High", c: "oklch(0.54 0.12 65)", check: "Total incurred does not reconcile", n: "2", ex: "HBR-0004 · 39,171.00 vs 37,671.00", imp: "£1,751" },
  { sev: "Medium", c: "oklch(0.5 0.1 255)", check: "Exact resubmission", n: "3", ex: "HBR-0006 · rows 7 & 22", imp: "£49,898" },
  { sev: "Medium", c: "oklch(0.5 0.1 255)", check: "Dates out of order", n: "2", ex: "HBR-0016 · loss after notified", imp: "—" },
  { sev: "Medium", c: "oklch(0.5 0.1 255)", check: "Ambiguous date format", n: "11", ex: "HBR-0021 · 03/04/2026", imp: "—" },
  { sev: "Medium", c: "oklch(0.5 0.1 255)", check: "Negative reserve", n: "1", ex: "HBR-0033 · −120.00", imp: "—" },
  { sev: "Info", c: "#676b7e", check: "Claim development (not duplicates)", n: "4", ex: "HBR-0019 · Jul → Aug", imp: "—" },
];

export default function SampleReportPage() {
  return (
    <div className="min-h-screen" style={{ background: "var(--chrome)", color: "var(--chromeStrong)" }}>
      <SiteNav />
      <main className="mx-auto flex max-w-[944px] flex-col items-center gap-6 px-4 pb-16 pt-[120px] sm:px-8">
        <div className="flex w-full flex-wrap items-center justify-between gap-3">
          <Link href="/#health" className="flex items-center gap-1.5 text-[13px] hover:text-[var(--chromeStrong)]" style={{ color: "var(--muted)" }}>
            <ArrowLeft />
            Back
          </Link>
          <span className="rounded-full px-3 py-1 text-[12px] font-medium" style={{ background: "var(--accentTint)", color: "var(--accentText)" }}>
            Sample report · illustrative data, not a customer file
          </span>
          <Link href="/onboarding" className="tb-btn tb-btn-primary">Run a Health Check on your file</Link>
        </div>

        <article className="flex w-full flex-col gap-9 rounded-md px-6 pb-[52px] pt-[60px] sm:px-[68px]" style={{ background: "#fbfbfd", color: "#1c1e2a", boxShadow: "0 0 0 1px rgba(28,30,42,.08), 0 20px 50px rgba(0,0,0,.25)" }}>
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-center gap-[9px] text-[15px] font-semibold">
              <Mark size={24} radius={6} />
              TrueBind
            </div>
            <div className="tnum text-right text-[11px] leading-[1.6]" style={{ color: "#595d6c" }}>
              HC-SAMPLE-7F3A
              <br />
              Prepared for a sample organisation
              <br />
              28 September 2026
            </div>
          </div>
          <div className="flex flex-col gap-3">
            <span className="text-[11.5px] font-medium uppercase tracking-[.1em]" style={{ color: "#5d5294" }}>Bordereau Health Check</span>
            <h1 className="m-0 text-[26px] font-medium leading-[1.15] tracking-[-0.025em] [text-wrap:balance] sm:text-[32px]">
              1,284 rows checked. 23 need attention before submission. 2 checks could not be assessed.
            </h1>
            <p className="m-0 text-[14px] leading-[1.6]" style={{ color: "#3f424d" }}>
              Harbour MGA · Claims bordereau Aug-26 · Harbour_MGA_Claims_Aug26.xlsx · 3 sheets · processed in 3m 12s
            </p>
          </div>
          <div className="flex flex-col gap-3">
            <div className="flex h-3 gap-0.5 overflow-hidden rounded-[3px]">
              <div style={{ width: "92%", background: "oklch(0.58 0.12 155)" }} />
              <div style={{ width: "4%", background: "oklch(0.75 0.14 75)" }} />
              <div style={{ width: "2%", boxShadow: "inset 0 0 0 1px #676b7e", background: "repeating-linear-gradient(45deg,#676b7e 0 2px,transparent 2px 4px)" }} />
              <div style={{ width: "2%", background: "#b2b6ca" }} />
            </div>
            <div className="grid grid-cols-2 gap-4 text-[12.5px] sm:grid-cols-4">
              {[
                ["Checked", "1,259 rows"],
                ["Flagged", "23 rows"],
                ["Unmapped", "1 of 12 columns"],
                ["Not assessed", "2 checks"],
              ].map(([l, v]) => (
                <div key={l} className="flex flex-col gap-[3px]">
                  <span style={{ color: "#595d6c" }}>{l}</span>
                  <span className="text-[15px] font-medium">{v}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="flex flex-col gap-2.5">
            <span className="text-[15px] font-semibold">Findings</span>
            <div className="overflow-x-auto">
              <div className="min-w-[600px]">
                <div className="grid gap-x-3.5 pb-2 text-[11px] font-medium uppercase tracking-[.06em]" style={{ gridTemplateColumns: "84px minmax(0,1.5fr) 44px minmax(0,1.5fr) 88px", boxShadow: "0 1px 0 rgba(28,30,42,.12)", color: "#676b7e" }}>
                  <span>Severity</span>
                  <span>Check</span>
                  <span className="text-right">Count</span>
                  <span>Example</span>
                  <span className="text-right">Impact</span>
                </div>
                {FINDINGS.map((f) => (
                  <div key={f.check} className="tnum grid items-baseline gap-x-3.5 py-2.5 text-[13px]" style={{ gridTemplateColumns: "84px minmax(0,1.5fr) 44px minmax(0,1.5fr) 88px", boxShadow: "0 1px 0 rgba(28,30,42,.06)" }}>
                    <span className="flex items-center gap-[7px] text-[12px]" style={{ color: f.c }}>
                      <span className="h-[7px] w-[7px] rounded-full" style={{ background: f.c }} />
                      {f.sev}
                    </span>
                    <span>{f.check}</span>
                    <span className="text-right">{f.n}</span>
                    <span className="text-[12px]" style={{ color: "#3f424d" }}>{f.ex}</span>
                    <span className="text-right">{f.imp}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
          <div className="grid gap-9" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(260px,1fr))" }}>
            <div className="flex flex-col gap-2.5">
              <span className="text-[15px] font-semibold">What was not checked</span>
              <div className="flex flex-col gap-2 text-[13px] leading-[1.5]" style={{ color: "#3f424d" }}>
                <span>“Adj Notes” column — unmapped. Free text with no CRS field; not interpreted.</span>
                <span>Reserve adequacy — not assessed. Outside this ruleset.</span>
                <span>Sanctions screening — not assessed. No sanctions list loaded.</span>
              </div>
            </div>
            <div className="flex flex-col gap-2.5">
              <span className="text-[15px] font-semibold">Evidence</span>
              <div className="tnum grid grid-cols-[minmax(84px,100px)_minmax(0,1fr)] [overflow-wrap:anywhere] gap-y-1.5 text-[12.5px]">
                {[
                  ["Source hash", "sha256 9c1e40…d2a47b"],
                  ["Mapping", "v3 · confirmed by a reviewer"],
                  ["Ruleset", "Lloyd’s CRS v5.2"],
                  ["Audit chain", "Intact"],
                  ["Source values", "Unchanged"],
                ].map(([l, v]) => (
                  <span key={l} className="contents">
                    <span style={{ color: "#595d6c" }}>{l}</span>
                    <span>{v}</span>
                  </span>
                ))}
              </div>
            </div>
          </div>
          <div className="flex flex-wrap justify-between gap-2 pt-4 text-[11px]" style={{ boxShadow: "0 -1px 0 rgba(28,30,42,.12)", color: "#676b7e" }}>
            <span>Sample document. Real reports carry your organisation’s name, run reference and audit-chain entries.</span>
          </div>
        </article>
      </main>
      <SiteFooter />
    </div>
  );
}
