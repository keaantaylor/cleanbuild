"use client";

import { LinkBreak, ShieldCheck } from "@phosphor-icons/react";
import { useRef } from "react";
import type { Tone } from "@/lib/statusMeta";
import s from "./Pipeline.module.css";

export const PIPELINE = ["Received", "Ingest", "Map", "Validate", "Reconcile", "Audit"] as const;

export type StepState = "done" | "active" | "upcoming" | "failed";

/** 00 Received · 01 Ingest · … With onSelect it becomes a keyboard-operable
 * tablist (marketing); without, a read-only progress list with the current
 * step announced (processing screen, report header). */
export function Stepper({
  steps = PIPELINE as unknown as string[],
  current,
  states,
  onSelect,
  compact = false,
  label = "Pipeline",
  describe,
}: {
  steps?: string[];
  current: number;
  /** Override per-step state; defaults to done before current, active at current. */
  states?: StepState[];
  onSelect?: (i: number) => void;
  compact?: boolean;
  label?: string;
  /** Tooltip text per step, e.g. what ran and what didn't. */
  describe?: (i: number) => string | undefined;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const stateOf = (i: number): StepState => states?.[i] ?? (i < current ? "done" : i === current ? "active" : "upcoming");
  const cls = (i: number) => [s.step, s[stateOf(i)]].filter(Boolean).join(" ");
  const style = { "--n": steps.length } as React.CSSProperties;

  if (onSelect) {
    const go = (i: number) => {
      const n = (i + steps.length) % steps.length;
      refs.current[n]?.focus();
      onSelect(n);
    };
    return (
      <div role="tablist" aria-label={label} className={`${s.stepper} ${compact ? s.compact : ""}`} style={style}>
        {steps.map((name, i) => (
          <button
            key={name}
            ref={(el) => {
              refs.current[i] = el;
            }}
            type="button"
            role="tab"
            aria-selected={i === current}
            tabIndex={i === current ? 0 : -1}
            className={cls(i)}
            title={describe?.(i)}
            onClick={() => onSelect(i)}
            onKeyDown={(e) => {
              if (e.key === "ArrowRight") go(i + 1);
              else if (e.key === "ArrowLeft") go(i - 1);
              else return;
              e.preventDefault();
            }}
          >
            <span className={s.num}>{String(i).padStart(2, "0")}</span>
            <span className={s.name}>{name}</span>
          </button>
        ))}
      </div>
    );
  }
  return (
    <ol aria-label={label} className={`${s.stepper} ${compact ? s.compact : ""}`} style={style}>
      {steps.map((name, i) => {
        const st = stateOf(i);
        return (
          <li key={name} className={cls(i)} aria-current={st === "active" ? "step" : undefined} title={describe?.(i)}>
            <span className={s.num}>{String(i).padStart(2, "0")}</span>
            <span className={s.name}>{name}</span>
            <span className="sr-only-ds">{st === "done" ? ", done" : st === "active" ? ", in progress" : st === "failed" ? ", failed" : ""}</span>
          </li>
        );
      })}
    </ol>
  );
}

export interface TimelineStep {
  title: string;
  body: React.ReactNode;
  children?: React.ReactNode;
}

/** "One audited path": numbered steps on a hairline with lavender dots. */
export function Timeline({ steps, vertical = false }: { steps: TimelineStep[]; vertical?: boolean }) {
  return (
    <ol className={`${s.timeline} ${vertical ? s.vertical : ""}`} style={{ "--n": Math.min(steps.length, 3) } as React.CSSProperties}>
      {steps.map((st, i) => (
        <li key={st.title} className={s.tItem}>
          <h3 className={s.tHead}>
            <span className={s.tNum}>{String(i + 1).padStart(2, "0")}</span>
            {st.title}
          </h3>
          <p className={s.tBody}>{st.body}</p>
          {st.children}
        </li>
      ))}
    </ol>
  );
}

export interface EvidenceLine {
  tone: Tone;
  text: React.ReactNode;
}

const TONE_WORD: Record<Tone, string> = { danger: "Breach", warning: "Review", success: "OK", neutral: "Not assessed", brand: "Info" };

/** Evidence lines with a status dot, e.g. "row 5 · incurred 39,171.00 ≠ 37,671.00". */
export function EvidenceCard({ lines, label }: { lines: EvidenceLine[]; label?: string }) {
  return (
    <ul className={s.evidence} aria-label={label}>
      {lines.map((l, i) => (
        <li key={i} className={s.eLine}>
          <span className={`${s.eDot} ${s[`d-${l.tone}`]}`} aria-hidden="true" />
          <span>
            <span className="sr-only-ds">{TONE_WORD[l.tone]}: </span>
            {l.text}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** "#113 · mapping v3 confirmed by molly · 14:02" with its hash. */
export function AuditEntry({ seq, action, actor, when, whenTitle, hash }: { seq: number; action: React.ReactNode; actor: string; when: string; whenTitle?: string; hash?: string }) {
  return (
    <div className={s.audit}>
      <span className={s.seq}>#{seq}</span>
      <span className={s.what}>
        {action} <span className={s.who}>by {actor}</span>
      </span>
      <time className={s.when} title={whenTitle}>{when}</time>
      {hash && <span className={s.hash} title={hash}>{hash.slice(0, 16)}…</span>}
    </div>
  );
}

export function ChainStatus({ intact, entries }: { intact: boolean; entries: number }) {
  return intact ? (
    <span className={s.chain}>
      <ShieldCheck size={16} weight="bold" aria-hidden="true" />
      Chain intact · {entries.toLocaleString("en-GB")} entries
    </span>
  ) : (
    <span className={`${s.chain} ${s.chainBroken}`}>
      <LinkBreak size={16} weight="bold" aria-hidden="true" />
      Chain broken
    </span>
  );
}
