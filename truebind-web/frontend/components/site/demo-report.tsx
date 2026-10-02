"use client";

import { useState } from "react";
import { DownloadSimple } from "@phosphor-icons/react";
import demo from "@/lib/demo-report.json";
import type { HealthView } from "@/lib/types";
import { TONE, severityLabel } from "@/lib/severity";
import { formatMoney, formatNumber } from "@/lib/formatters";
import { SiteFooter, SiteNav } from "./chrome";
import { LeadButton } from "./lead-form";
import { ContactLine } from "./contact";

const hv = demo.health_view as unknown as HealthView;
const PAPER = { text: "#1c1e2a", muted: "#3f424d", faint: "#555a69", line: "rgba(28,30,42,.12)" };
const FILES = [
  ["The file as received", "Sample_Bordereau.xlsx", "A synthetic 500-row monthly claims bordereau with problems planted in it. No real data."],
  ["Annotated workbook", "Sample_Bordereau_REVIEWED.xlsx", "The same file, every claim cell coloured, a Review notes column, hover notes with the fix, and an Issues sheet with links to each cell."],
  ["Corrected copy", "Sample_Bordereau_CORRECTED.xlsx", "Only the safe fixes applied, each listed on the Change Log sheet."],
] as const;

function plural(n: number, one: string) {
  return `${formatNumber(n)} ${n === 1 ? one : `${one}s`}`;
}

/** The public demo: a real run of the product on a generated sample (scripts/build_demo.py). */
export function DemoReport() {
  const [letter, setLetter] = useState(false);
  const ready = hv.verdict === "ready";
  const v = TONE[ready ? "ok" : "err"];
  return (
    <div className="min-h-screen" style={{ background: "var(--chrome)", color: "var(--chromeStrong)" }}>
      <SiteNav />
      <main id="main" className="mx-auto flex max-w-[1100px] flex-col gap-8 px-4 pb-20 pt-[130px] sm:px-6">
        <div className="flex max-w-[760px] flex-col gap-3">
          <span className="text-[12px] font-medium uppercase tracking-[.1em]" style={{ color: "var(--kicker)" }}>Sample Health Check</span>
          <h1 className="m-0 text-[36px] font-medium leading-[1.1] tracking-[-0.03em] sm:text-[44px]">This is what you get back.</h1>
          <p className="m-0 text-[16.5px] leading-[1.6]" style={{ color: "var(--chromeMuted)" }}>
            We generated a {formatNumber(demo.rows)}-row claims bordereau, planted {demo.planted_problems} problems in it, and ran it through TrueBind exactly as a customer file would be. Everything below, and every file you can download, is that run’s real output.
          </p>
        </div>

        <article className="flex flex-col gap-7 rounded-md px-6 pb-10 pt-9 sm:px-12" style={{ background: "#fbfbfd", color: PAPER.text, boxShadow: "0 0 0 1px var(--line)" }}>
          <span className="text-[12px] font-semibold uppercase tracking-[.1em]" style={{ color: "#047857" }}>Bordereau Health Check · {demo.file_name} · {formatNumber(demo.rows)} claim rows</span>
          <section className="flex flex-col gap-1.5 rounded-md px-5 py-4" style={{ background: v.bg, color: v.fg }}>
            <span className="text-[28px] font-semibold leading-[1.15] tracking-[-0.02em]">{hv.verdict_label}</span>
            <span className="text-[14.5px] font-medium">{hv.verdict_reason}</span>
          </section>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {([["err", "Errors", hv.counts.errors, "must be fixed"], ["warn", "Warnings", hv.counts.warnings, "unusual, or not in a checkable form"], ["muted", "Couldn’t check", hv.counts.couldnt_check, hv.counts.couldnt_check ? "checks that could not run" : "every check ran"]] as const).map(([t, l, n, sub]) => (
              <div key={l} className="flex flex-col gap-1 rounded-md p-4" style={{ background: TONE[t].bg, color: TONE[t].fg }}>
                <span className="text-[13px] font-semibold">{l}</span>
                <span className="tnum text-[30px] font-semibold leading-none">{formatNumber(n)}</span>
                <span className="text-[12.5px]">{sub}</span>
              </div>
            ))}
          </div>
          <section className="flex flex-col gap-2">
            <h2 className="m-0 text-[17px] font-semibold">Top {hv.top_fixes.length} fixes</h2>
            <ol className="m-0 flex list-none flex-col p-0">
              {hv.top_fixes.map((r, i) => {
                const t = TONE[r.outcome === "FAIL" ? "err" : "warn"];
                const ex = r.examples[0];
                return (
                  <li key={r.rule} className="grid grid-cols-[28px_minmax(0,1fr)] gap-x-3 py-3" style={{ boxShadow: `0 1px 0 ${PAPER.line}` }}>
                    <span className="tnum text-[15px] font-semibold" style={{ color: PAPER.faint }}>{i + 1}</span>
                    <div className="flex min-w-0 flex-col gap-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="rounded px-1.5 py-0.5 text-[11.5px] font-semibold" style={{ background: t.bg, color: t.fg }}>{t.label} · {severityLabel(r.severity)}</span>
                        <span className="text-[14.5px] font-semibold">{r.label}</span>
                        <span className="tnum text-[13px]" style={{ color: PAPER.muted }}>{plural(r.findings, "finding")}</span>
                      </div>
                      {ex && <span className="text-[13.5px]"><b className="tnum font-semibold">{ex.where}</b>: {ex.sentence}</span>}
                      {r.money_at_risk.length > 0 && <span className="tnum text-[13px]" style={{ color: PAPER.muted }}>Money on these rows: {r.money_at_risk.map((m) => formatMoney(m.amount, m.currency)).join(" · ")}</span>}
                      <span className="text-[13px]" style={{ color: PAPER.muted }}>Fix: {r.fix}</span>
                    </div>
                  </li>
                );
              })}
            </ol>
          </section>
          {demo.skipped_sheets.length > 0 && (
            <p className="m-0 text-[13px]" style={{ color: PAPER.muted }}>
              Not claims, so left out (and shown, never hidden): {demo.skipped_sheets.map((s) => `“${s.sheet_name}”`).join(", ")}.
            </p>
          )}
        </article>

        <section className="flex flex-col gap-3">
          <h2 className="m-0 text-[22px] font-medium">Download the files</h2>
          <div className="grid gap-4 md:grid-cols-3">
            {FILES.map(([title, file, body]) => (
              <a key={file} href={`/demo/${file}`} download className="flex flex-col gap-2 rounded-md p-5 transition-colors hover:bg-[rgba(52,211,153,.08)]" style={{ boxShadow: "inset 0 0 0 1px var(--line2)" }}>
                <span className="flex items-center gap-2 text-[15px] font-medium"><DownloadSimple />{title}</span>
                <span className="text-[13.5px] leading-[1.5]" style={{ color: "var(--chromeMuted)" }}>{body}</span>
                <span className="text-[12.5px]" style={{ color: "var(--accentText)" }}>{file}</span>
              </a>
            ))}
          </div>
        </section>

        <section className="flex flex-col gap-3">
          <div className="flex flex-wrap items-baseline justify-between gap-3">
            <h2 className="m-0 text-[22px] font-medium">The query letter</h2>
            <button type="button" className="tb-btn" onClick={() => setLetter((x) => !x)}>{letter ? "Hide the letter" : `Show the letter (${demo.query_letter.items} points)`}</button>
          </div>
          <p className="m-0 text-[14.5px]" style={{ color: "var(--chromeMuted)" }}>Only what the sender must fix, grouped by issue, each with its cell. Ready to paste into an email.</p>
          {letter && <pre className="m-0 max-h-[460px] overflow-auto whitespace-pre-wrap rounded-md p-5 text-[12.5px] leading-[1.55]" style={{ background: "var(--surface)", color: "var(--chromeText)", boxShadow: "inset 0 0 0 1px var(--line2)" }}>{`Subject: ${demo.query_letter.subject}\n\n${demo.query_letter.body}`}</pre>}
        </section>

        <section className="flex flex-col items-start gap-3 rounded-md p-6" style={{ background: "var(--section)" }}>
          <h2 className="m-0 text-[22px] font-medium">Try it on one of your own files</h2>
          <p className="m-0 text-[15px]" style={{ color: "var(--chromeText)" }}>Founding pilot: your first file is free. We return the annotated workbook, the corrected copy and the query letter.</p>
          <LeadButton kind="health" className="tb-btn tb-btn-primary">Get a free Health Check</LeadButton>
          <ContactLine />
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}
