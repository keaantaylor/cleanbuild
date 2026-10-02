"use client";

import { useEffect, useId, useRef } from "react";
import { CheckCircle, Info, Moon, ShieldCheck, Sun, Warning, WarningCircle, X } from "@phosphor-icons/react";
import { useUi } from "@/lib/ui";

export function Mark({ size = 24, radius = 6 }: { size?: number; radius?: number }) {
  // eslint-disable-next-line @next/next/no-img-element
  return <img src="/assets/mark.png" alt="" width={size} height={size} style={{ width: size, height: size, borderRadius: radius, flex: "none" }} />;
}

export function Brand({ size = 24, className = "" }: { size?: number; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-[9px] font-semibold ${className}`}>
      <Mark size={size} radius={Math.round(size / 4)} />
      TrueBind
    </span>
  );
}

export function ThemeToggle({ className = "", style }: { className?: string; style?: React.CSSProperties }) {
  const { theme, toggleTheme } = useUi();
  return (
    <button
      type="button"
      onClick={toggleTheme}
      title={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
      aria-label="Switch theme"
      className={`flex h-[34px] w-[34px] flex-none cursor-pointer items-center justify-center rounded-md text-[17px] transition-colors hover:bg-[var(--accentTint)] ${className}`}
      style={{ color: "var(--muted)", ...style }}
    >
      {theme === "dark" ? <Sun /> : <Moon />}
    </button>
  );
}

/** Centred dialog built on Nocturne's .dialog pattern. Esc and backdrop click close it. */
export function Modal({
  open,
  onClose,
  title,
  kicker,
  children,
  actions,
  width = 480,
}: {
  open: boolean;
  onClose: () => void;
  title: React.ReactNode;
  kicker?: string;
  children?: React.ReactNode;
  actions?: React.ReactNode;
  width?: number;
}) {
  const id = useId();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    const prev = document.activeElement as HTMLElement | null;
    ref.current?.querySelector<HTMLElement>("input,textarea,select,button[data-autofocus]")?.focus();
    return () => {
      window.removeEventListener("keydown", onKey);
      prev?.focus?.();
    };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div
      className="anim-fade fixed inset-0 z-[60] grid place-items-center p-4"
      style={{ background: "color-mix(in srgb, #0b0c14 55%, transparent)" }}
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby={id}
        className="anim-pop flex max-h-[88vh] w-full flex-col gap-4 overflow-y-auto rounded-md p-6"
        style={{
          maxWidth: width,
          background: "var(--surface)",
          color: "var(--text)",
          boxShadow: "0 0 0 1px var(--line2)",
        }}
      >
        <div className="flex items-start justify-between gap-4">
          <div className="flex flex-col gap-1.5">
            {kicker && <span className="kicker">{kicker}</span>}
            <h2 id={id} className="m-0 text-[20px] font-medium tracking-[-0.015em]">
              {title}
            </h2>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="tb-btn tb-btn-ghost -mr-2 -mt-1 !p-2">
            <X />
          </button>
        </div>
        {children && <div className="text-[14px] leading-[1.55]" style={{ color: "var(--muted)" }}>{children}</div>}
        {actions && <div className="mt-1 flex flex-wrap justify-end gap-2">{actions}</div>}
      </div>
    </div>
  );
}

const TONE = {
  ok: { icon: ShieldCheck, c: "oklch(0.76 0.12 155)" },
  info: { icon: Info, c: "#6fe3c1" },
  warn: { icon: Warning, c: "oklch(0.81 0.12 75)" },
  err: { icon: WarningCircle, c: "oklch(0.72 0.15 25)" },
};

/** The prototype's glass toast, bottom centre. */
export function Toaster() {
  const { toasts } = useUi();
  return (
    <div className="no-print pointer-events-none fixed bottom-7 left-1/2 z-[70] flex -translate-x-1/2 flex-col items-center gap-2" aria-live="polite">
      {toasts.map((t) => {
        const T = TONE[t.tone];
        return (
          <div
            key={t.id}
            className="anim-rise flex max-w-[calc(100vw-32px)] items-center gap-2.5 rounded-md px-4 py-[11px] text-[13px]"
            style={{
              background: "rgba(35,37,50,.9)",
              color: "#e9e9ed",
              boxShadow: "inset 0 1px 0 rgba(255,255,255,.08), 0 0 0 1px rgba(52,211,153,.4)",
            }}
          >
            <T.icon style={{ color: T.c, flex: "none" }} size={16} weight="regular" />
            <span className="truncate">{t.text}</span>
          </div>
        );
      })}
    </div>
  );
}

export function StatusPill({ tone, children }: { tone: "ok" | "warn" | "err" | "med" | "muted"; children: React.ReactNode }) {
  const map = {
    ok: ["var(--ok)", "var(--okT)"],
    warn: ["var(--warn)", "var(--warnT)"],
    err: ["var(--err)", "var(--errT)"],
    med: ["var(--med)", "var(--medT)"],
    muted: ["var(--muted)", "var(--line)"],
  }[tone];
  return (
    <span className="tb-pill" style={{ color: map[0], background: map[1] }}>
      {children}
    </span>
  );
}

/** Checked · Flagged · Unmapped · Not assessed — the honest-coverage bar. */
export function CoverageBar({ parts, height = 6 }: { parts: [number, number, number, number]; height?: number }) {
  return (
    <div className="flex overflow-hidden" style={{ height, borderRadius: 3, gap: 2, background: "var(--line)" }}>
      <div style={{ width: parts[0] + "%", background: "var(--ok)" }} />
      <div style={{ width: parts[1] + "%", background: "var(--warn)" }} />
      <div className="hatch" style={{ width: parts[2] + "%" }} />
      <div style={{ width: parts[3] + "%", background: "var(--na)" }} />
    </div>
  );
}

export function CoverageLegend() {
  const sw = "inline-block h-2 w-2 rounded-[2px]";
  return (
    <div className="flex flex-wrap gap-3.5 text-[11.5px] whitespace-nowrap" style={{ color: "var(--muted)" }}>
      <span className="flex items-center gap-1.5"><span className={sw} style={{ background: "var(--ok)" }} />Checked</span>
      <span className="flex items-center gap-1.5"><span className={sw} style={{ background: "var(--warn)" }} />Flagged</span>
      <span className="flex items-center gap-1.5"><span className={`${sw} hatch`} style={{ boxShadow: "inset 0 0 0 1px var(--muted)" }} />Unmapped</span>
      <span className="flex items-center gap-1.5"><span className={sw} style={{ background: "var(--na)" }} />Not assessed</span>
    </div>
  );
}

export function PageHeader({
  kicker,
  title,
  sub,
  actions,
}: {
  kicker: string;
  title: React.ReactNode;
  sub?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div className="flex flex-col gap-1.5">
        <span className="kicker">{kicker}</span>
        <h1 className="m-0 text-[30px] font-medium tracking-[-0.02em]">{title}</h1>
        {sub && <p className="m-0 max-w-[640px] text-[14.5px]" style={{ color: "var(--muted)" }}>{sub}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2 whitespace-nowrap">{actions}</div>}
    </div>
  );
}

/** A stat tile with the coloured top rule seen in the current build's screenshots. */
export function StatTile({
  label,
  value,
  note,
  color = "var(--line2)",
  icon,
  active,
  onClick,
}: {
  label: string;
  value: React.ReactNode;
  note?: React.ReactNode;
  color?: string;
  icon?: React.ReactNode;
  active?: boolean;
  onClick?: () => void;
}) {
  const Tag = onClick ? "button" : "div";
  return (
    <Tag
      type={onClick ? "button" : undefined}
      onClick={onClick}
      className={`relative flex flex-col gap-1.5 overflow-hidden rounded-md px-[18px] pb-4 pt-[18px] text-left transition-colors ${onClick ? "cursor-pointer hover:bg-[var(--accentTint)]" : ""}`}
      style={{
        background: active ? "var(--accentTint)" : "var(--surface)",
        boxShadow: active ? "var(--shadow), inset 0 0 0 1px var(--accent)" : "var(--shadow)",
        color: "var(--text)",
      }}
    >
      <span className="absolute left-[18px] right-[18px] top-0 h-[2px] rounded-b" style={{ background: color }} />
      <span className="flex items-center gap-2 text-[12.5px]" style={{ color: "var(--muted)" }}>
        <span style={{ color, display: "flex" }}>{icon}</span>
        {label}
      </span>
      <span className="tnum text-[26px] font-medium tracking-[-0.02em]">{value}</span>
      {note && <span className="text-[12px]" style={{ color: "var(--faint)" }}>{note}</span>}
    </Tag>
  );
}

export function Toggle({ on, onChange, label }: { on: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      onClick={() => onChange(!on)}
      className="relative h-[20px] w-[34px] flex-none cursor-pointer rounded-full transition-colors"
      style={{ background: on ? "var(--accent)" : "var(--line2)" }}
    >
      <span
        className="absolute top-[3px] h-[14px] w-[14px] rounded-full bg-white transition-all"
        style={{ left: on ? 17 : 3, boxShadow: "0 0 0 1px var(--line)" }}
      />
    </button>
  );
}

export function EmptyState({ icon, title, body, action }: { icon: React.ReactNode; title: string; body: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2.5 px-6 py-14 text-center">
      <span className="grid h-11 w-11 place-items-center rounded-full text-[20px]" style={{ background: "var(--accentTint)", color: "var(--accentText)" }}>
        {icon}
      </span>
      <span className="text-[15px] font-medium">{title}</span>
      <span className="max-w-[380px] text-[13px]" style={{ color: "var(--muted)" }}>{body}</span>
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export { CheckCircle };

/** Shaped placeholder while data loads. */
export function Skeleton({ h = 16, w = "100%", r = 6, className = "" }: { h?: number; w?: number | string; r?: number; className?: string }) {
  return <span className={`tb-skeleton block ${className}`} style={{ height: h, width: w, borderRadius: r }} aria-hidden="true" />;
}

export function LoadingState({ label, rows = 4 }: { label: string; rows?: number }) {
  return (
    <div className="flex flex-col gap-3 py-2" role="status" aria-live="polite">
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} h={i === 0 ? 22 : 14} w={i === 0 ? "40%" : `${92 - i * 9}%`} />
      ))}
    </div>
  );
}

/** Explained, retryable failure — never a blank screen. */
export function ErrorState({ title, message, onRetry }: { title: string; message?: string | null; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-start gap-2.5 rounded-md px-5 py-4" role="alert" style={{ background: "var(--errT)", boxShadow: "inset 0 0 0 1px color-mix(in srgb, var(--err) 35%, transparent)" }}>
      <span className="flex items-center gap-2 text-[14px] font-medium" style={{ color: "var(--err)" }}>
        <WarningCircle size={16} />
        {title}
      </span>
      {message && <span className="text-[13px]" style={{ color: "var(--muted)" }}>{message}</span>}
      {onRetry && (
        <button type="button" className="tb-btn !py-1.5 text-[13px]" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}
