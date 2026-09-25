import Link from "next/link";
import { BrandMark } from "@/components/layout/BrandMark";
import { EngineScene } from "./EngineScene";
import s from "./landing.module.css";

/* Landing page. Every capability named here exists in the product today;
 * anything that does not is labelled "planned". The product panel shows the
 * engine's real output for a synthetic test workbook and says so. No
 * customers, logos, testimonials or savings figures are claimed. */

const PIPELINE = [
  { k: "01", t: "Receive", d: "Upload any workbook — one sheet or twenty. File checks run first: type, size, structure. Macros never run.",
    f: ["xlsx · xlsm · xls · csv", "sender and programme recorded", "sha-256 fingerprint"] },
  { k: "02", t: "Understand", d: "Every sheet is inspected, header rows found below titles, and each source column matched to a Lloyd’s CRS field.",
    f: ["alias rules first", "AI sees headers only", "confidence per column"] },
  { k: "03", t: "Validate", d: "Required data, arithmetic to total incurred, dates, currency and status — row by row, with every source row reconciled.",
    f: ["paid + expenses + reserve", "no silent row loss", "currencies never mixed"] },
  { k: "04", t: "Investigate", d: "Each finding says what happened, where it came from, the evidence and why it matters. Duplicates are told apart from development.",
    f: ["exact vs probable", "development ≠ duplicate", "source row for every finding"] },
  { k: "05", t: "Act", d: "Decide, assign, follow up and export — every decision written to a hash-chained audit trail.",
    f: ["work queue", "claims / exceptions / audit CSV", "verifiable audit chain"] },
];

const TRUST = [
  { t: "Every source row accounted for", d: "Each row becomes a claim or a recorded exclusion with its reason. The report shows the reconciliation." },
  { t: "Nothing merged automatically", d: "Duplicates are flagged for a person to confirm, dismiss or send back. Source data is never altered." },
  { t: "AI reads headers, not your data", d: "Column mapping may ask a model about header text only. Cell values are never sent. Calls are capped and time-boxed." },
  { t: "Tamper-evident audit trail", d: "Every mapping, decision and export is hash-chained. Anyone can verify the chain is intact." },
  { t: "Isolated by organisation", d: "Tenant isolation in the application and PostgreSQL row-level security underneath it." },
  { t: "Safe outputs", d: "CSV exports are guarded against formula injection; uploads are checked before anything reads them." },
];

const FLOW: { t: string; state: "live" | "planned" }[] = [
  { t: "E-mail arrives", state: "planned" }, { t: "Attachment detected", state: "planned" },
  { t: "Workbook ingested", state: "live" }, { t: "Mapping proposed", state: "live" },
  { t: "Validated", state: "live" }, { t: "Exceptions raised", state: "live" },
  { t: "Report built", state: "live" }, { t: "Output sent", state: "live" },
];

export function Landing() {
  return (
    <div className={s.page}>
      <header className={s.nav}>
        <div className={s.navInner}>
          <Link href="/" className={s.brand}><BrandMark size={28} />TrueBind</Link>
          <nav aria-label="Sections" className={s.navLinks}>
            <a href="#pipeline">How it works</a><a href="#product">Product</a><a href="#trust">Trust</a><a href="#automation">Automation</a>
          </nav>
          <div className={s.navCta}>
            <Link href="/login" className={s.linkBtn}>Sign in</Link>
            <Link href="/login?mode=signup" className={s.btnPrimary}>Try TrueBind</Link>
          </div>
        </div>
      </header>

      <main>
        <section className={s.hero}>
          <div className={s.heroInner}>
            <div className={s.heroCopy}>
              <p className={s.kicker}><span className={s.kickerDot} />Bordereaux intelligence</p>
              <h1 className={s.h1}>Insurance data,<br /><span>finally in motion.</span></h1>
              <p className={s.lede}>
                TrueBind takes the bordereaux your partners actually send — any layout, any number of sheets — and turns them into
                validated, reconciled, explainable data your team can act on.
              </p>
              <div className={s.heroCtas}>
                <Link href="/login?mode=signup" className={s.btnPrimary}>Try TrueBind</Link>
                <a href="#pipeline" className={s.btnGhost}>See how it works</a>
              </div>
            </div>
            <div className={s.heroVisual}><EngineScene /></div>
          </div>
        </section>

        <section id="pipeline" className={s.section}>
          <div className={s.inner}>
            <p className={s.eyebrow}>The engine</p>
            <h2 className={s.h2}>From a messy workbook to a decision, in five steps.</h2>
            <ol className={s.pipeline}>
              {PIPELINE.map((p) => (
                <li key={p.k} className={s.stage}>
                  <span className={s.stageNo}>{p.k}</span>
                  <h3 className={s.stageTitle}>{p.t}</h3>
                  <p className={s.stageBody}>{p.d}</p>
                  <ul className={s.facts}>{p.f.map((f) => <li key={f}>{f}</li>)}</ul>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section id="product" className={`${s.section} ${s.sunken}`}>
          <div className={s.inner}>
            <p className={s.eyebrow}>The product</p>
            <h2 className={s.h2}>One file in. A health report you can defend.</h2>
            <p className={s.sub}>
              Below is the report TrueBind produced for a synthetic 450-row, three-sheet test workbook we use to exercise the engine.
              The numbers are the engine’s real output for that file. They are not customer data.
            </p>
            <div className={s.product} aria-label="Example report produced by the engine for a synthetic test workbook">
              <div className={s.productBar}><span /><span /><span /><em>Truebind_StressTest_450rows_replica.xlsx · synthetic test file</em></div>
              <div className={s.productBody}>
                <div className={s.pHero}>
                  <div className={s.pRing}><span>99</span><small>/100</small></div>
                  <div>
                    <p className={s.pGrade}>Grade 5 <small>/ 5 · Excellent</small></p>
                    <p className={s.pText}>450 claim rows across 3 of 3 sheets were assessed and every source row is accounted for.
                      6 exact resubmissions found. 6 claims show development from a previous period and are not treated as duplicates.</p>
                    <div className={s.pPills}><span className={s.good}>Every source row reconciles</span><span className={s.warn}>6 exact resubmissions</span>
                      <span className={s.info}>6 development</span></div>
                  </div>
                </div>
                <div className={s.pGrid}>
                  <div><small>Total incurred · GBP</small><strong>£81,631,049</strong></div>
                  <div><small>Paid to date</small><strong>£45,950,455</strong></div>
                  <div><small>Paid expenses / ALAE</small><strong>£2,050,145</strong></div>
                  <div><small>Reserve</small><strong>£33,630,449</strong></div>
                </div>
                <div className={s.pRows}>
                  <div className={s.pRow}><span className={`${s.sev} ${s.sevHigh}`}>high</span><strong>6 exact resubmissions of a claim</strong>
                    <em>Same claim reference, same reporting period and identical amounts — confirm each pair and ask the sender to withdraw the repeat.</em></div>
                  <div className={s.pRow}><span className={`${s.sev} ${s.sevInfo}`}>info</span><strong>6 source columns were not mapped</strong>
                    <em>Kept on every row and included in the claims export; not validated.</em></div>
                </div>
              </div>
            </div>
            <p className={s.note}>Measured in our test environment: that workbook went from upload to a rendered report in 3–5 seconds, including the mapping confirmation.</p>
          </div>
        </section>

        <section id="trust" className={s.section}>
          <div className={s.inner}>
            <p className={s.eyebrow}>Trust</p>
            <h2 className={s.h2}>Built for people who have to defend the number.</h2>
            <div className={s.trust}>
              {TRUST.map((t) => (
                <article key={t.t} className={s.trustItem}>
                  <span className={s.trustMark} aria-hidden="true" />
                  <h3>{t.t}</h3>
                  <p>{t.d}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section id="automation" className={`${s.section} ${s.dark}`}>
          <div className={s.inner}>
            <p className={s.eyebrowLight}>Automation</p>
            <h2 className={s.h2Light}>From inbox to outbound, without the copy-paste.</h2>
            <p className={s.subLight}>The same audited pipeline runs for every file. Web upload and API intake work today; e-mail intake is planned and marked as such.</p>
            <ol className={s.flow}>
              {FLOW.map((f, i) => (
                <li key={f.t} className={`${s.flowStep} ${f.state === "planned" ? s.planned : ""}`}>
                  <span className={s.flowNo}>{String(i + 1).padStart(2, "0")}</span>
                  <span className={s.flowText}>{f.t}</span>
                  <span className={s.flowState}>{f.state === "live" ? "live" : "planned"}</span>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section className={s.closing}>
          <div className={s.inner}>
            <h2 className={s.h2}>Bring your next bordereau.</h2>
            <p className={s.sub}>Create an organisation, upload a workbook and walk through mapping, validation and the report yourself.</p>
            <div className={s.heroCtas} style={{ justifyContent: "center" }}>
              <Link href="/login?mode=signup" className={s.btnPrimary}>Try TrueBind</Link>
              <Link href="/login" className={s.btnOutline}>Sign in</Link>
            </div>
          </div>
        </section>
      </main>

      <footer className={s.footer}>
        <div className={s.navInner}>
          <span className={s.brand}><BrandMark size={22} />TrueBind</span>
          <span>Bordereaux ingestion, validation and audit.</span>
        </div>
      </footer>
    </div>
  );
}
