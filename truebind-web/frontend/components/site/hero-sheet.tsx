"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";

/* The hero's animated workbook: Received → Ingest → Map → Validate →
   Reconcile → Audit. Logic and numbers are a straight port of the
   prototype's renderVals(); only the React plumbing is new. */

const RED = { bg: "oklch(0.94 0.045 25)", fg: "oklch(0.48 0.17 25)", ring: "inset 0 0 0 1.5px oklch(0.62 0.18 25)" };
const AMB = { bg: "oklch(0.95 0.06 85)", fg: "oklch(0.46 0.1 70)", ring: "inset 0 0 0 1.5px oklch(0.72 0.14 75)" };
const GRN = { bg: "oklch(0.955 0.035 150)", fg: "oklch(0.4 0.1 150)", ring: "inset 0 0 0 1.5px oklch(0.6 0.12 150)" };
const HATCH = "repeating-linear-gradient(45deg, #eef0ee 0 4px, #e3e6e3 4px 8px)";

const W = [76, 58, 78, 110, 72, 70, 56, 78, 80];
const H = ["Clm No.", "Bdx Mth", "DOL", "Insured", "Paid £", "Resv", "Fees", "Total Inc", "Adj Notes"];
const M = ["claim_reference", "reporting_period", "date_of_loss", "insured_name", "paid_to_date", "reserve", "fees", "total_incurred", "unmapped"];
const D = [
  ["HBR-0004", "Jul-26", "12/05/2026", "Atlas Freight Ltd", "18,400.00", "6,100.00", "0.00", "24,500.00", "chased 2x"],
  ["HBR-0006", "Jul-26", "19/05/2026", "Kestrel Farms", "12,812.00", "36,896.00", "190.00", "49,898.00", ""],
  ["HBR-0008", "Jul-26", "04/06/2026", "Bexley Dental", "9,800.00", "4,200.00", "0.00", "15,000.00", "see email"],
  ["HBR-0011", "Jul-26", "", "Ferris & Lane", "1,120.00", "880.00", "0.00", "2,000.00", ""],
  ["HBR-0006", "Jul-26", "19/05/2026", "Kestrel Farms", "12,812.00", "36,896.00", "190.00", "49,898.00", ""],
  ["HBR-0004", "Aug-26", "12/05/2026", "Atlas Freight Ltd", "21,900.00", "2,600.00", "0.00", "24,500.00", "rev. reserve"],
  ["HBR-0016", "Aug-26", "06/28/2026", "Harrow Joinery", "640.00", "1,360.00", "0.00", "2,000.00", ""],
];
const JIT = [0, 5, -3, 7, -4, 3, -6];
const RZ = [0, 0.35, -0.2, 0.5, -0.3, 0.2, -0.45];
const TF = [
  "rotateX(20deg) rotateY(-24deg) rotateZ(5deg) translateZ(-20px)",
  "rotateX(26deg) rotateY(-30deg) rotateZ(3deg) translateZ(-40px)",
  "rotateX(14deg) rotateY(-16deg) rotateZ(1deg) translateZ(0px)",
  "rotateX(9deg) rotateY(-10deg) rotateZ(0deg) translateZ(10px)",
  "rotateX(7deg) rotateY(-7deg) rotateZ(0deg) translateZ(20px)",
  "rotateX(10deg) rotateY(-18deg) rotateZ(0deg) translateZ(0px)",
];
export const STAGES: [string, string][] = [
  ["Received", "A TPA bordereau as it actually arrives. Three sheets, 1,284 rows, nobody’s schema."],
  ["Ingest", "Every sheet inspected. Header row found on row 4 of “Claims”, below the title block."],
  ["Map", "8 of 9 columns mapped to Lloyd’s CRS v5.2. “Adj Notes” left unmapped — not guessed."],
  ["Validate", "Arithmetic, required data and formats checked on every row. 23 findings."],
  ["Reconcile", "Paid + reserve + fees checked against incurred. Resubmissions split from development."],
  ["Audit", "Every step hash-chained against the untouched source. Evidence ready to forward."],
];
const FORM = [
  "A4   Clm No.",
  "A4   Clm No.   · header row detected",
  "A4   claim_reference  ←  “Clm No.”",
  "H7   =E7+F7+G7  →  14,000.00  ≠  15,000.00",
  "H7   =E7+F7+G7  →  14,000.00  ≠  15,000.00",
  "source unchanged · sha256 9c1e…a47b · chain #113",
];

export function useHeroStage(seconds = 3.4) {
  const [stage, setStage] = useState(0);
  const [paused, setPaused] = useState(false);
  useEffect(() => {
    if (paused) return;
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    const t = setTimeout(() => setStage((s) => (s + 1) % 6), (stage === 5 ? 1.8 : 1) * seconds * 1000);
    return () => clearTimeout(t);
  }, [stage, paused, seconds]);
  return { stage, setStage, setPaused };
}

export function HeroSheet({ stage: s }: { stage: number }) {
  // The composition is laid out at a fixed 760px, then scaled to fit narrow screens.
  const wrap = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  useLayoutEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setScale(Math.min(1, e.contentRect.width / 760)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const headers = W.map((w, c) => {
    if (s < 2) return { w, top: H[c], sub: "", subOp: 0, bg: "transparent", fg: "#2a2f36" };
    if (c === 8) return { w, top: "unmapped", sub: "not guessed", subOp: 1, bg: HATCH, fg: "#7e858d" };
    return { w, top: M[c], sub: "from “" + H[c] + "”", subOp: 1, bg: "transparent", fg: "oklch(0.4 0.11 150)" };
  });
  const flag = (r: number, c: number) =>
    s >= 3 && ((r === 2 && c === 7) || (r === 3 && c === 2)) ? RED : s >= 3 && r === 6 && c === 2 ? AMB : null;
  const rows = D.map((d, r) => {
    let bg = "transparent",
      sh = "none",
      tf = "translateX(0px) translateZ(0px) rotateZ(0deg)";
    if (s < 2) tf = `translateX(${JIT[r]}px) translateZ(0px) rotateZ(${s === 0 ? RZ[r] : RZ[r] / 2}deg)`;
    if (s === 3 && [0, 1, 4, 5].includes(r)) bg = AMB.bg;
    if (s >= 4 && r === 4) {
      bg = RED.bg;
      tf = "translateX(22px) translateZ(34px) rotateZ(0deg)";
      sh = "0 10px 24px rgba(0,0,0,.25), 0 0 0 1px oklch(0.62 0.18 25)";
    }
    if (s >= 4 && r === 5) bg = GRN.bg;
    const dot = s >= 5 ? ([2, 3, 4].includes(r) ? "oklch(0.6 0.18 25)" : r === 6 ? "oklch(0.72 0.14 75)" : "oklch(0.6 0.13 150)") : "transparent";
    const ch = ({ 2: ["Δ 1,000.00 · incurred ≠ paid + reserve + fees", RED.fg], 4: ["Exact resubmission of row 6", RED.fg], 5: ["Development of row 5 · Jul → Aug", GRN.fg] } as Record<number, string[]>)[r];
    const cells = d.map((v, c) => {
      const f = flag(r, c);
      let t = v,
        fs = "normal",
        cbg = "transparent",
        fg = "#2a2f36",
        ring = "none";
      if (r === 3 && c === 2 && s >= 3) {
        t = "blank";
        fs = "italic";
      }
      if (c === 8 && s >= 2) {
        cbg = HATCH;
        fg = "#9aa1a9";
      }
      if (f) {
        cbg = f.bg;
        fg = f.fg;
        ring = f.ring;
      }
      if (s >= 4 && r === 5 && c >= 4 && c <= 7) fg = GRN.fg;
      return { t, w: W[c], fs, bg: cbg, fg, ring, al: c >= 4 && c <= 7 ? "flex-end" : "flex-start" };
    });
    return { n: r + 5, cells, bg, sh, tf, dot, chip: ch ? ch[0] : "", chipC: ch ? ch[1] : "transparent", chipOp: ch && s >= 4 ? 1 : 0 };
  });
  const back1 = { tf: s >= 1 ? "translate3d(28px,-34px,-60px)" : "translate3d(0,0,-2px)", op: s === 0 ? 0 : s >= 3 ? 0.55 : 1 };
  const back2 = { tf: s >= 1 ? "translate3d(56px,-68px,-120px)" : "translate3d(0,0,-4px)", op: s === 0 ? 0 : s >= 3 ? 0.35 : 1 };
  const audit = { tf: s === 5 ? "translateZ(90px) translateY(0px)" : "translateZ(20px) translateY(20px)", op: s === 5 ? 1 : 0 };
  const ease = "cubic-bezier(.2,.7,.1,1)";
  const grid = "repeating-linear-gradient(0deg, transparent 0 25px, #d6d9d4 25px 26px), repeating-linear-gradient(90deg, transparent 0 77px, #d6d9d4 77px 78px)";

  return (
    <div ref={wrap} className="relative w-full" style={{ height: 500 * scale }} aria-label={`Bordereau workbook — stage ${STAGES[s][0]}`} role="img">
      <div style={{ position: "absolute", left: 0, top: 0, width: 760, height: 500, transform: `scale(${scale})`, transformOrigin: "0 0", perspective: 1900, perspectiveOrigin: "40% 40%" }}>
        <div style={{ position: "absolute", left: 24, top: 48, width: 706, height: 374, transformStyle: "preserve-3d", transform: TF[s], transition: `transform 1.3s ${ease}` }}>
          <div style={{ position: "absolute", inset: 0, borderRadius: 10, background: "#e8eae7", boxShadow: "0 30px 60px rgba(0,0,0,.5)", transform: back2.tf, opacity: back2.op, transition: `all 1.1s ${ease}`, backgroundImage: grid }}>
            <span style={{ position: "absolute", left: 14, bottom: 8, font: "500 10.5px var(--font-body)", color: "#4b5159", padding: "3px 8px", background: "#fafbf9", borderRadius: 4 }}>Movements</span>
          </div>
          <div style={{ position: "absolute", inset: 0, borderRadius: 10, background: "#eef0ed", boxShadow: "0 30px 60px rgba(0,0,0,.5)", transform: back1.tf, opacity: back1.op, transition: `all 1.1s ${ease}`, backgroundImage: grid.replace(/#d6d9d4/g, "#dadcd7") }}>
            <span style={{ position: "absolute", left: 14, bottom: 8, font: "500 10.5px var(--font-body)", color: "#4b5159", padding: "3px 8px", background: "#fafbf9", borderRadius: 4 }}>Reserves</span>
          </div>
          <div style={{ position: "absolute", inset: 0, borderRadius: 10, background: "#f7f8f6", boxShadow: "0 40px 80px rgba(0,0,0,.6), 0 0 0 1px rgba(0,0,0,.08)", overflow: "hidden", color: "#2a2f36" }}>
            <div style={{ height: 30, display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 12px", background: "oklch(0.46 0.11 150)", color: "#eaf4ee", fontSize: 11.5, fontWeight: 500 }}>
              <div style={{ display: "flex", gap: 6 }}>
                {[0, 1, 2].map((i) => <span key={i} style={{ width: 8, height: 8, borderRadius: "50%", background: "rgba(255,255,255,.35)" }} />)}
              </div>
              <span>Harbour_MGA_Claims_Aug26_FINAL_v3.xlsx</span>
              <span className="tnum" style={{ fontSize: 10.5, opacity: 0.8 }}>{s === 0 ? "1 file" : "3 sheets · 1,284 rows"}</span>
            </div>
            <div className="tnum" style={{ height: 26, display: "flex", alignItems: "center", gap: 10, padding: "0 10px", borderBottom: "1px solid #e1e4df", background: "#fcfcfb", fontSize: 11, color: "#4b5159", whiteSpace: "pre" }}>
              <span style={{ fontStyle: "italic", color: "#8a9098" }}>fx</span>
              <span style={{ width: 1, height: 14, background: "#e1e4df" }} />
              <span>{FORM[s]}</span>
            </div>
            <div style={{ display: "flex", height: 20, background: "#eff1ee", borderBottom: "1px solid #e1e4df", fontSize: 10, color: "#8a9098" }}>
              <div style={{ width: 28, flex: "none", borderRight: "1px solid #e1e4df" }} />
              {W.map((w, i) => (
                <div key={i} style={{ width: w, flex: "none", display: "flex", alignItems: "center", justifyContent: "center", borderRight: "1px solid #e1e4df" }}>{"ABCDEFGHI"[i]}</div>
              ))}
            </div>
            <div style={{ display: "flex", height: 36, borderBottom: "1px solid #d5d9d3", background: "oklch(0.96 0.02 150)" }}>
              <div style={{ width: 28, flex: "none", display: "flex", alignItems: "center", justifyContent: "center", borderRight: "1px solid #e1e4df", fontSize: 10, color: "#8a9098", background: "#eff1ee" }}>4</div>
              {headers.map((h, i) => (
                <div key={i} style={{ width: h.w, flex: "none", padding: "4px 7px", borderRight: "1px solid #e1e4df", display: "flex", flexDirection: "column", justifyContent: "center", gap: 1, background: h.bg, transition: "background .6s" }}>
                  <span style={{ fontSize: 10.5, fontWeight: 600, color: h.fg, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{h.top}</span>
                  <span style={{ fontSize: 9, color: "#7e858d", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", opacity: h.subOp, transition: "opacity .6s" }}>{h.sub}</span>
                </div>
              ))}
            </div>
            {rows.map((row, ri) => (
              <div key={ri} style={{ position: "relative", display: "flex", height: 26, borderBottom: "1px solid #e6e8e4", background: row.bg, transform: row.tf, boxShadow: row.sh, transition: `transform .9s ${ease}, background .6s, box-shadow .6s` }}>
                <div style={{ width: 28, flex: "none", display: "flex", alignItems: "center", justifyContent: "center", gap: 3, borderRight: "1px solid #e1e4df", background: "#eff1ee", fontSize: 10, color: "#8a9098" }}>
                  <span style={{ width: 5, height: 5, borderRadius: "50%", background: row.dot, transition: "background .6s" }} />
                  {row.n}
                </div>
                {row.cells.map((c, ci) => (
                  <div key={ci} className="tnum" style={{ width: c.w, flex: "none", padding: "0 7px", display: "flex", alignItems: "center", justifyContent: c.al, borderRight: "1px solid #e6e8e4", fontSize: 10.5, color: c.fg, background: c.bg, boxShadow: c.ring, fontStyle: c.fs, whiteSpace: "nowrap", overflow: "hidden", transition: "background .6s, box-shadow .6s" }}>{c.t}</div>
                ))}
                <div style={{ position: "absolute", right: 6, top: 3, height: 18, display: "flex", alignItems: "center", padding: "0 8px", borderRadius: 5, background: "#fff", boxShadow: `0 0 0 1px ${row.chipC}, 0 4px 10px rgba(0,0,0,.12)`, color: row.chipC, fontSize: 10, fontWeight: 500, whiteSpace: "nowrap", opacity: row.chipOp, transition: "opacity .6s" }}>{row.chip}</div>
              </div>
            ))}
            {[12, 13].map((n) => (
              <div key={n} style={{ display: "flex", height: 26, borderBottom: "1px solid #edefeb" }}>
                <div style={{ width: 28, display: "flex", alignItems: "center", justifyContent: "center", borderRight: "1px solid #e1e4df", background: "#eff1ee", fontSize: 10, color: "#8a9098" }}>{n}</div>
              </div>
            ))}
            <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: 28, display: "flex", alignItems: "center", gap: 2, padding: "0 10px", background: "#eff1ee", borderTop: "1px solid #d5d9d3", fontSize: 10.5, fontWeight: 500, color: "#5e656d" }}>
              <span style={{ padding: "5px 12px", background: "#fcfcfb", color: "oklch(0.42 0.11 150)", boxShadow: "inset 0 -2px 0 oklch(0.5 0.12 150)" }}>Claims</span>
              <span style={{ padding: "5px 12px" }}>Reserves</span>
              <span style={{ padding: "5px 12px" }}>Movements</span>
            </div>
          </div>
          <div style={{ position: "absolute", left: 430, top: 196, width: 300, padding: "16px 18px", borderRadius: 14, background: "rgba(27,29,43,.92)", boxShadow: "inset 0 1px 0 rgba(255,255,255,.1), 0 0 0 1px rgba(145,132,217,.35), 0 30px 60px rgba(0,0,0,.55), 0 0 40px rgba(145,132,217,.12)", color: "#e9e9ed", display: "flex", flexDirection: "column", gap: 12, transform: audit.tf, opacity: audit.op, transition: `all 1s ${ease}` }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
              <span style={{ fontSize: 13, fontWeight: 500 }}>Evidence · run 7F3A</span>
              <span style={{ fontSize: 10.5, color: "#9397ab" }}>28 Sep 09:14</span>
            </div>
            <div style={{ display: "flex", height: 6, borderRadius: 3, overflow: "hidden", gap: 2 }}>
              <div style={{ width: "92%", background: "oklch(0.76 0.12 155)" }} />
              <div style={{ width: "4%", background: "oklch(0.81 0.12 75)" }} />
              <div style={{ width: "2%", background: "repeating-linear-gradient(45deg,#9397ab 0 2px,transparent 2px 4px)" }} />
              <div style={{ width: "2%", background: "#4a4d5c" }} />
            </div>
            <div className="tnum" style={{ display: "grid", gridTemplateColumns: "1fr auto", rowGap: 6, fontSize: 12, color: "#cfd3e5" }}>
              {[
                ["oklch(0.76 0.12 155)", "Checked", "1,259 rows"],
                ["oklch(0.81 0.12 75)", "Flagged", "23 rows"],
                ["hatch", "Unmapped", "1 column"],
                ["#4a4d5c", "Not assessed", "2 checks"],
              ].map(([c, l, v]) => (
                <span key={l} style={{ display: "contents" }}>
                  <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ width: 7, height: 7, borderRadius: 2, ...(c === "hatch" ? { boxShadow: "inset 0 0 0 1px #9397ab", background: "repeating-linear-gradient(45deg,#9397ab 0 2px,transparent 2px 4px)" } : { background: c }) }} />
                    {l}
                  </span>
                  <span>{v}</span>
                </span>
              ))}
            </div>
            <div style={{ paddingTop: 10, borderTop: "1px solid rgba(233,233,237,.08)", fontSize: 10.5, lineHeight: 1.65, color: "#9397ab" }}>
              source sha256 9c1e…a47b · unchanged
              <br />
              mapping v3 · confirmed by molly
              <br />
              Lloyd’s CRS v5.2 · chain entry #113
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
