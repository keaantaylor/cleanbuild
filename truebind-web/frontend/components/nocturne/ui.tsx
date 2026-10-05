"use client";

/* Legacy component names kept compiling while screens are rebuilt. Each one
   now renders the matching components/ds component; delete this file once
   no screen imports it (Session 8). */
import { useEffect, useRef } from "react";
import { CheckCircle } from "@phosphor-icons/react";
import {
  Chip,
  EmptyState as DsEmpty,
  ErrorPanel,
  LoadingBlock,
  Logo,
  Mark as DsMark,
  Modal as DsModal,
  PageHeader as DsPageHeader,
  Skeleton as DsSkeleton,
} from "@/components/ds";
import { Button } from "@/components/ds";
export { Toaster } from "@/components/ds";

export function Mark({ size = 24 }: { size?: number; radius?: number }) {
  return <DsMark size={size} />;
}

export function Brand({ size = 24, className = "" }: { size?: number; className?: string }) {
  return (
    <span className={className}>
      <Logo size={size} />
    </span>
  );
}

/** Centred dialog (ds Modal). `kicker` is no longer shown. */
export function Modal({
  open,
  onClose,
  title,
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
  return (
    <DsModal open={open} onClose={onClose} title={title} footer={actions} width={width}>
      {children}
    </DsModal>
  );
}

const PILL_TONE = { ok: "success", warn: "warning", err: "danger", med: "neutral", muted: "neutral" } as const;

export function StatusPill({ tone, children }: { tone: keyof typeof PILL_TONE; children: React.ReactNode }) {
  return <Chip tone={PILL_TONE[tone]}>{children}</Chip>;
}

/** Checked · Flagged · Unmapped · Not assessed - the honest-coverage bar. */
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

export function PageHeader({ title, sub, actions }: { kicker: string; title: React.ReactNode; sub?: React.ReactNode; actions?: React.ReactNode }) {
  return <DsPageHeader title={title} meta={sub} actions={actions} />;
}

/** A count tile: label, number, note. Plain border, no colour rule. */
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

export function EmptyState({ title, body, action }: { icon?: React.ReactNode; title: string; body: string; action?: React.ReactNode }) {
  return <DsEmpty title={title} body={body} action={action} />;
}

export { CheckCircle };

export function Skeleton({ h = 16, w = "100%", r = 6 }: { h?: number; w?: number | string; r?: number; className?: string }) {
  return <DsSkeleton h={h} w={w} r={r} />;
}

export function LoadingState({ label, rows = 4 }: { label: string; rows?: number }) {
  return <LoadingBlock label={label} rows={rows} />;
}

/** Explained, retryable failure: never a blank screen. */
export function ErrorState({ title, message, onRetry }: { title: string; message?: string | null; onRetry?: () => void }) {
  return (
    <ErrorPanel
      title={title}
      body={message}
      action={onRetry && <Button size={28} onClick={onRetry}>Try again</Button>}
    />
  );
}

/** Controlled anchored panel (old shell API), used by the report picker until Session 2 replaces it. */
export function Popover({ children, onClose, width = 360, align = "right" }: { children: React.ReactNode; onClose: () => void; width?: number; align?: "right" | "left" }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.parentElement?.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);
  return (
    <div
      ref={ref}
      className="tb-popover absolute top-[calc(100%+8px)] z-50 overflow-hidden"
      style={{ [align]: 0, width, maxWidth: "calc(100vw - 24px)", background: "var(--surface-raised)", border: "1px solid var(--border)", borderRadius: "var(--r-control)", boxShadow: "var(--shadow-float)" }}
    >
      {children}
    </div>
  );
}
