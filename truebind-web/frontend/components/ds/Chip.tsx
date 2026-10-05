import { statusMeta, type Tone } from "@/lib/statusMeta";
import s from "./Chip.module.css";

/** 22px chip: 6px dot plus a word. The word always carries the meaning; colour only repeats it. */
export function Chip({ tone = "neutral", dot = true, children, className }: { tone?: Tone; dot?: boolean; children: React.ReactNode; className?: string }) {
  return <span className={[s.chip, s[tone], dot && s.dot, className].filter(Boolean).join(" ")}>{children}</span>;
}

/** A system status in plain English, via statusMeta(). */
export function StatusPill({ status, label }: { status: string; label?: string }) {
  const m = statusMeta(status);
  return <Chip tone={m.tone}>{label ?? m.label}</Chip>;
}

export function Tag({ children }: { children: React.ReactNode }) {
  return <span className={s.tag}>{children}</span>;
}

/** Count badge. Caps at 9+ unless told otherwise. */
export function CountBadge({ n, cap = 9, strong = false, label }: { n: number; cap?: number; strong?: boolean; label?: string }) {
  if (n <= 0) return null;
  return (
    <span className={[s.count, strong && s.countStrong].filter(Boolean).join(" ")} aria-label={label ?? `${n}`}>
      {n > cap ? `${cap}+` : n}
    </span>
  );
}
