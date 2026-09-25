/* The TrueBind engine, drawn in code: messy spreadsheet fragments on the
 * left are pulled through the binding bar and leave as structured,
 * validated rows that end in an action. Pure SVG + CSS keyframes: no
 * video, nothing to download, static under prefers-reduced-motion.
 * Decorative -- the page text carries the meaning. */
import s from "./engine.module.css";

const MESSY = [
  { x: 24, y: 58, r: -6, t: "Claim Ref." },
  { x: 58, y: 118, r: 4, t: "Paid (GBP)" },
  { x: 16, y: 176, r: -3, t: "Outstndg" },
  { x: 70, y: 236, r: 7, t: "D.O.L" },
  { x: 22, y: 296, r: -5, t: "Status " },
  { x: 62, y: 352, r: 3, t: "Tot. Inc." },
];
const ROWS = [
  { y: 92, code: "CR0104M", label: "Claim reference", ok: true },
  { y: 146, code: "TB_PAID_TD", label: "Paid to date", ok: true },
  { y: 200, code: "CR0130CM", label: "Reserve", ok: true },
  { y: 254, code: "CR0155CM", label: "Total incurred", ok: false },
  { y: 308, code: "CR0105CM", label: "Claim status", ok: true },
];

export function EngineScene() {
  return (
    <svg className={s.scene} viewBox="0 0 760 420" role="img" aria-label="Spreadsheet columns flowing through the TrueBind engine into validated fields">
      <defs>
        <linearGradient id="thread" x1="0" x2="1">
          <stop offset="0" stopColor="#8FA2FF" stopOpacity="0.15" />
          <stop offset="1" stopColor="#8FA2FF" stopOpacity="0.9" />
        </linearGradient>
        <linearGradient id="bar" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="#6FE3C1" stopOpacity="0.2" />
          <stop offset="0.5" stopColor="#6FE3C1" />
          <stop offset="1" stopColor="#6FE3C1" stopOpacity="0.2" />
        </linearGradient>
        <radialGradient id="glow"><stop offset="0" stopColor="#6FE3C1" stopOpacity="0.55" /><stop offset="1" stopColor="#6FE3C1" stopOpacity="0" /></radialGradient>
        <pattern id="grid" width="24" height="24" patternUnits="userSpaceOnUse"><path d="M24 0H0V24" fill="none" stroke="#FFFFFF" strokeOpacity="0.04" /></pattern>
      </defs>
      <rect width="760" height="420" fill="url(#grid)" />

      {/* incoming fragments + threads */}
      {MESSY.map((m, i) => (
        <g key={m.t} className={s.frag} style={{ animationDelay: `${i * 0.35}s` }}>
          <path className={s.thread} d={`M${m.x + 110} ${m.y + 14} C ${250} ${m.y + 14}, ${260} ${210}, ${352} ${120 + i * 36}`}
                stroke="url(#thread)" style={{ animationDelay: `${i * 0.35}s` }} />
          <g transform={`translate(${m.x} ${m.y}) rotate(${m.r})`}>
            <rect width="110" height="28" rx="6" className={s.cell} />
            <text x="10" y="18" className={s.cellText}>{m.t}</text>
          </g>
        </g>
      ))}

      {/* binding bar */}
      <circle cx="366" cy="210" r="120" fill="url(#glow)" className={s.glow} />
      <rect x="356" y="70" width="20" height="280" rx="10" fill="url(#bar)" />
      <rect x="360" y="90" width="12" height="240" rx="6" className={s.barCore} />
      <circle cx="366" cy="100" r="5" className={s.pulse} />

      {/* structured output */}
      {ROWS.map((r, i) => (
        <g key={r.code} className={s.row} style={{ animationDelay: `${0.6 + i * 0.3}s` }}>
          <path d={`M378 ${r.y + 16} H 410`} className={s.link} />
          <rect x="410" y={r.y} width="250" height="32" rx="8" className={r.ok ? s.rowBox : s.rowBoxWarn} />
          <text x="424" y={r.y + 20} className={s.code}>{r.code}</text>
          <text x="520" y={r.y + 20} className={s.rowText}>{r.label}</text>
          <g transform={`translate(${672} ${r.y + 4})`}>
            <rect width="72" height="24" rx="12" className={r.ok ? s.chipOk : s.chipWarn} />
            <text x="36" y="16" textAnchor="middle" className={s.chipText}>{r.ok ? "valid" : "exception"}</text>
          </g>
        </g>
      ))}
      <g className={s.action}>
        <rect x="410" y="360" width="334" height="34" rx="17" className={s.actionBox} />
        <text x="577" y="382" textAnchor="middle" className={s.actionText}>Report built · exception routed · audit recorded</text>
      </g>
    </svg>
  );
}
