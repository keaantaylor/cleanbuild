import { statusMeta } from "@/lib/statusMeta";
import { Chip } from "./Chip";
import s from "./Verdict.module.css";

export type VerdictState = "CLEAN" | "ISSUES_OPEN" | "INCOMPLETE" | "PROCESSING" | "FAILED";

export type VerdictMetric =
  | { kind?: "value"; label: string; value: React.ReactNode; caption?: React.ReactNode }
  | { kind: "grade"; label?: string; grade: number | null };

/** The report headline. Honesty is enforced here, not by each screen:
 * an INCOMPLETE report never shows a grade, and a report with open issues
 * never shows a grade above 3. Grades are numbers, never words. */
export function VerdictStrip({
  state,
  title,
  sentence,
  reasons = [],
  metrics,
}: {
  state: VerdictState;
  title: React.ReactNode;
  sentence?: React.ReactNode;
  reasons?: string[];
  metrics: VerdictMetric[];
}) {
  const meta = statusMeta(state);
  return (
    <section className={s.strip} style={{ "--n": metrics.length } as React.CSSProperties} aria-label="Verdict">
      <div className={`${s.cell} ${s.state}`}>
        <span><Chip tone={meta.tone}>{meta.label}</Chip></span>
        <h2 className={s.stateTitle}>{title}</h2>
        {sentence && <p className={s.stateSentence}>{sentence}</p>}
      </div>
      {metrics.map((m, i) =>
        m.kind === "grade" ? (
          <GradeCell key={i} state={state} grade={m.grade} label={m.label ?? "Data quality"} reasons={reasons} />
        ) : (
          <div key={i} className={s.cell}>
            <span className={s.label}>{m.label}</span>
            <span className={s.value}>{m.value}</span>
            {m.caption && <span className={s.caption}>{m.caption}</span>}
          </div>
        ),
      )}
    </section>
  );
}

function GradeCell({ state, grade, label, reasons }: { state: VerdictState; grade: number | null; label: string; reasons: string[] }) {
  let value: React.ReactNode;
  let caption: React.ReactNode;
  if (state === "INCOMPLETE" || state === "PROCESSING" || state === "FAILED" || grade == null) {
    value = <span className={s.valueMuted}>Grade withheld</span>;
    caption =
      state === "INCOMPLETE" && reasons.length > 0 ? (
        <ul className={s.reasons}>{reasons.map((r) => <li key={r}>{r}</li>)}</ul>
      ) : state === "PROCESSING" ? "Shown when processing finishes" : "Not enough was assessed to grade";
  } else if (state === "ISSUES_OPEN") {
    value = `${Math.min(grade, 3)} / 5`;
    caption = "Capped while breaches are open";
  } else {
    value = `${grade} / 5`;
    caption = "Based on what was assessed";
  }
  return (
    <div className={s.cell}>
      <span className={s.label}>{label}</span>
      <span className={s.value}>{value}</span>
      <span className={s.caption}>{caption}</span>
    </div>
  );
}

export interface Coverage {
  checked: number;
  flagged: number;
  unmapped: number;
  notAssessed: number;
}

/** Checked · Flagged · Unmapped · Not assessed, as a stacked bar with the four numbers under it. */
export function CoverageBar({ value, height = 8, legend = true, compact = false }: { value: Coverage; height?: number; legend?: boolean; compact?: boolean }) {
  const parts: [keyof Coverage, string, string][] = [
    ["checked", "Checked", s.checked],
    ["flagged", "Flagged", s.flagged],
    ["unmapped", "Unmapped", s.unmapped],
    ["notAssessed", "Not assessed", s.notAssessed],
  ];
  const total = parts.reduce((n, [k]) => n + value[k], 0) || 1;
  const summary = parts.map(([k, l]) => `${value[k].toLocaleString("en-GB")} ${l.toLowerCase()}`).join(", ");
  return (
    <div>
      <div className={s.bar} style={{ "--h": `${height}px` } as React.CSSProperties} role="img" aria-label={summary}>
        {parts.map(([k, , c]) => (value[k] > 0 ? <span key={k} className={`${s.seg} ${c}`} style={{ flexGrow: value[k] / total, flexBasis: 0 }} /> : null))}
      </div>
      {legend && (
        <dl className={`${s.legend} ${compact ? s.compactLegend : ""}`}>
          {parts.map(([k, l]) => (
            <div key={k}>
              <dt>{l}</dt>
              <dd>{value[k].toLocaleString("en-GB")}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}
