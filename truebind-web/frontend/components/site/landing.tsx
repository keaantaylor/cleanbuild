"use client";

import Link from "next/link";
import demo from "@/lib/demo-report.json";
import type { HealthView } from "@/lib/types";
import { severityLabel } from "@/lib/severity";
import { SiteFooter, SiteNav } from "./chrome";
import { LeadButton } from "./lead-form";
import { ContactLine } from "./contact";

const hv = demo.health_view as unknown as HealthView;

const FLOW: [string, string][] = [
  ["Receive", "Upload a workbook or send it by email. The file is fingerprinted and stored as received."],
  ["Profile", "Every sheet is read. Header rows, title rows, subtotals and blank runs are found and recorded."],
  ["Map", "Columns are matched to fields by rule. Anything the rules cannot place is left for a person to confirm."],
  ["Validate", "Each row is checked against versioned rules: required data, types, dates, currencies, arithmetic, policy period and limit."],
  ["Reconcile", "Duplicates, totals and month-on-month movements are checked across rows and sheets."],
  ["Isolate", "Every issue points to a sheet, a cell, the rule, the expected and actual value, and the difference."],
  ["Correct", "Safe formatting fixes are proposed. Nothing in the source file is overwritten; every change is versioned."],
  ["Approve and audit", "A person approves or overrides. Each step is written to a hash-chained audit log."],
];

const OUTPUTS: [string, string][] = [
  ["Annotated workbook", "Your file with each checked cell marked: OK, needs attention, or error, with the reason and the fix."],
  ["Corrected copy", "Only the safe fixes applied, each listed with before, after and the rule."],
  ["Query letter", "The items only the sender can fix, grouped by issue, each with its cell."],
  ["Audit trail", "What was received, checked, changed and approved, and by whom."],
];

export function Landing() {
  return (
    <div className="min-h-screen" style={{ background: "var(--bg)", color: "var(--text)" }}>
      <SiteNav />
      <main id="main">
        <section className="border-b" style={{ background: "var(--surface)", borderColor: "var(--line)" }}>
          <div className="mx-auto grid max-w-[1120px] gap-8 px-4 py-10 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
            <div className="flex flex-col gap-4">
              <h1 className="m-0 text-[28px] font-semibold leading-[1.2] sm:text-[32px]">Find the exact cells that stop a workbook reconciling.</h1>
              <p className="m-0 text-[15px] leading-[1.6]" style={{ color: "var(--muted)" }}>
                TrueBind checks bordereaux and other large workbooks against versioned rules. It points to the sheet, the cell, the rule and the fix, and keeps an audit trail of every correction. Source files are never changed.
              </p>
              <div className="flex flex-wrap gap-2">
                <LeadButton kind="health" className="tb-btn tb-btn-solid">Get a free Health Check</LeadButton>
                <Link href="/demo" className="tb-btn">See a sample report</Link>
              </div>
              <p className="m-0 text-[13px]" style={{ color: "var(--muted)" }}>First file free. No integration: upload the workbook as it is.</p>
            </div>
            <figure className="m-0 flex flex-col gap-2">
              <figcaption className="text-[12.5px]" style={{ color: "var(--muted)" }}>
                Sample output: a generated {demo.rows.toLocaleString("en-GB")}-row bordereau. {hv.verdict_label}: {hv.counts.errors} errors and {hv.counts.warnings} warnings.
              </figcaption>
              <div className="overflow-x-auto border" style={{ borderColor: "var(--line)", borderRadius: "var(--radius)" }}>
                <table className="w-full border-collapse text-[13px]">
                  <thead style={{ background: "var(--bg)" }}>
                    <tr className="text-left" style={{ color: "var(--muted)" }}>
                      <th className="px-3 py-2 font-medium">Cell</th>
                      <th className="px-3 py-2 font-medium">Issue</th>
                      <th className="px-3 py-2 font-medium">Result</th>
                      <th className="px-3 py-2 text-right font-medium">Count</th>
                    </tr>
                  </thead>
                  <tbody>
                    {hv.top_fixes.map((r) => (
                      <tr key={r.rule} className="border-t" style={{ borderColor: "var(--line)" }}>
                        <td className="mono px-3 py-2">{r.examples[0]?.cell ?? "-"}</td>
                        <td className="px-3 py-2">{r.label}</td>
                        <td className="px-3 py-2" style={{ color: r.outcome === "FAIL" ? "var(--err)" : "var(--warn)" }}>{r.outcome === "FAIL" ? "Error" : "Warning"} · {severityLabel(r.severity)}</td>
                        <td className="px-3 py-2 text-right">{r.findings}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Link href="/demo" className="text-[13px]" style={{ color: "var(--accentText)" }}>Open the full sample report and download the files</Link>
            </figure>
          </div>
        </section>

        <section id="how" className="mx-auto max-w-[1120px] scroll-mt-16 px-4 py-10">
          <h2 className="m-0 mb-4 text-[20px] font-semibold">How it works</h2>
          <ol className="m-0 grid list-none gap-x-8 gap-y-3 p-0 sm:grid-cols-2">
            {FLOW.map(([h, d], i) => (
              <li key={h} className="grid grid-cols-[24px_minmax(0,1fr)] gap-x-2 text-[14px]">
                <span className="tnum" style={{ color: "var(--muted)" }}>{i + 1}.</span>
                <span><b className="font-semibold">{h}.</b> <span style={{ color: "var(--muted)" }}>{d}</span></span>
              </li>
            ))}
          </ol>
        </section>

        <section className="border-y" style={{ background: "var(--surface)", borderColor: "var(--line)" }}>
          <div className="mx-auto max-w-[1120px] px-4 py-10">
            <h2 className="m-0 mb-4 text-[20px] font-semibold">What you get back</h2>
            <dl className="m-0 grid gap-x-8 gap-y-3 sm:grid-cols-2">
              {OUTPUTS.map(([h, d]) => (
                <div key={h} className="text-[14px]">
                  <dt className="font-semibold">{h}</dt>
                  <dd className="m-0" style={{ color: "var(--muted)" }}>{d}</dd>
                </div>
              ))}
            </dl>
          </div>
        </section>

        <section className="mx-auto flex max-w-[1120px] flex-col gap-3 px-4 py-10">
          <h2 className="m-0 text-[20px] font-semibold">Send one workbook</h2>
          <p className="m-0 max-w-[720px] text-[14px]" style={{ color: "var(--muted)" }}>
            We return the Health Check, the annotated workbook, the corrected copy and the query letter within one working day. Files are deleted after 30 days.
          </p>
          <div className="flex flex-wrap gap-2">
            <LeadButton kind="health" className="tb-btn tb-btn-solid">Get a free Health Check</LeadButton>
            <Link href="/pricing" className="tb-btn">Pricing</Link>
          </div>
          <ContactLine />
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}
