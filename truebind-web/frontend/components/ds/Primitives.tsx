"use client";

import { CheckCircle, File, FileCsv, FileXls, Info, Warning, WarningCircle } from "@phosphor-icons/react";
import s from "./Primitives.module.css";

const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

export function Mark({ size = 24 }: { size?: number }) {
  // eslint-disable-next-line @next/next/no-img-element
  return <img src="/assets/mark.png" alt="" width={size} height={size} className={s.mark} style={{ borderRadius: Math.round(size / 4) }} />;
}

export function Logo({ size = 24, label = true }: { size?: number; label?: boolean }) {
  return (
    <span className={s.brand} style={{ fontSize: size * 0.68 }}>
      <Mark size={size} />
      {label && "TrueBind"}
    </span>
  );
}

export function Panel({
  title,
  sub,
  actions,
  flush = false,
  children,
  className,
  as: Tag = "section",
  ...rest
}: {
  title?: React.ReactNode;
  sub?: React.ReactNode;
  actions?: React.ReactNode;
  flush?: boolean;
  children?: React.ReactNode;
  className?: string;
  as?: "section" | "div" | "aside";
} & React.HTMLAttributes<HTMLElement>) {
  return (
    <Tag className={cx(s.panel, className)} {...rest}>
      {(title || actions) && (
        <header className={s.panelHead}>
          <div>
            {title && <h2 className={s.panelTitle}>{title}</h2>}
            {sub && <div className={s.panelSub}>{sub}</div>}
          </div>
          {actions && <div className={s.actions}>{actions}</div>}
        </header>
      )}
      <div className={cx(s.panelBody, flush && s.flush)}>{children}</div>
    </Tag>
  );
}

export function PageHeader({ title, meta, actions, eyebrow }: { title: React.ReactNode; meta?: React.ReactNode; actions?: React.ReactNode; eyebrow?: string }) {
  return (
    <div className={s.pageHeader}>
      <div className={s.pageTitleBlock}>
        {eyebrow && <span className={s.eyebrow}>{eyebrow}</span>}
        <h1 className={s.h1}>{title}</h1>
        {meta && <p className={s.meta}>{meta}</p>}
      </div>
      {actions && <div className={s.actions}>{actions}</div>}
    </div>
  );
}

export function Eyebrow({ children, as: Tag = "span" }: { children: React.ReactNode; as?: "span" | "p" | "h2" }) {
  return <Tag className={s.eyebrow}>{children}</Tag>;
}

/** A system code, small and mono. Only ever under a plain label. */
export function Code({ children }: { children: React.ReactNode }) {
  return <span className={s.code}>{children}</span>;
}

export function TwoLine({ label, code }: { label: React.ReactNode; code?: React.ReactNode }) {
  return (
    <span className={s.twoLine}>
      <span>{label}</span>
      {code && <Code>{code}</Code>}
    </span>
  );
}

export function Kbd({ children }: { children: React.ReactNode }) {
  return <kbd className={s.kbd}>{children}</kbd>;
}

export function Avatar({ name, size = 28 }: { name: string; size?: number }) {
  const initials = name.trim().split(/[\s@.]+/).filter(Boolean).slice(0, 2).map((w) => w[0]?.toUpperCase()).join("") || "?";
  return (
    <span className={s.avatar} style={{ width: size, height: size, fontSize: Math.round(size * 0.4) }} aria-hidden="true">
      {initials}
    </span>
  );
}

export function FileChip({ name, meta }: { name: string; meta?: React.ReactNode }) {
  const ext = name.split(".").pop()?.toLowerCase();
  const Icon = ext === "csv" ? FileCsv : ext && ["xlsx", "xlsm", "xls"].includes(ext) ? FileXls : File;
  return (
    <span className={s.fileChip}>
      <Icon size={20} className={s.fileIcon} aria-hidden="true" />
      <span className={s.fileText}>
        <span className={s.fileName} title={name}>{name}</span>
        {meta && <span className={s.fileMeta}>{meta}</span>}
      </span>
    </span>
  );
}

export function Skeleton({ h = 14, w = "100%", r = 6 }: { h?: number; w?: number | string; r?: number }) {
  return <span className={s.skeleton} style={{ height: h, width: w, borderRadius: r }} aria-hidden="true" />;
}

/** Skeleton block with a screen-reader label, for a whole region that is loading. */
export function LoadingBlock({ label, rows = 4 }: { label: string; rows?: number }) {
  return (
    <div role="status" aria-live="polite" style={{ display: "flex", flexDirection: "column", gap: 10, padding: "4px 0" }}>
      <span className="sr-only-ds">{label}</span>
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} h={i === 0 ? 20 : 14} w={i === 0 ? "36%" : `${94 - i * 8}%`} />
      ))}
    </div>
  );
}

export function EmptyState({ title, body, action }: { title: string; body?: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className={s.empty}>
      <p className={s.emptyTitle}>{title}</p>
      {body && <p className={s.emptyBody}>{body}</p>}
      {action && <div className={s.emptyAction}>{action}</div>}
    </div>
  );
}

/** What happened, where, and what to do next. Never a blank screen. */
export function ErrorPanel({ title, body, reference, action }: { title: string; body?: React.ReactNode; reference?: string | null; action?: React.ReactNode }) {
  return (
    <div className={s.error} role="alert">
      <p className={s.errorTitle}>
        <WarningCircle size={16} weight="bold" aria-hidden="true" />
        {title}
      </p>
      {body && <p className={s.errorBody}>{body}</p>}
      {reference && <span className={s.errorRef}>Reference {reference}</span>}
      {action && <div style={{ marginTop: 6 }}>{action}</div>}
    </div>
  );
}

const BANNER = {
  info: [s.bannerInfo, Info],
  warning: [s.bannerWarning, Warning],
  success: [s.bannerSuccess, CheckCircle],
  danger: [s.bannerDanger, WarningCircle],
} as const;

export function Banner({ tone = "info", children }: { tone?: keyof typeof BANNER; children: React.ReactNode }) {
  const [c, Icon] = BANNER[tone];
  return (
    <div className={cx(s.banner, c)} role={tone === "danger" ? "alert" : "status"}>
      <Icon size={16} weight="bold" aria-hidden="true" />
      <div>{children}</div>
    </div>
  );
}

/** Shown on a direct visit to a module that is switched off in lib/flags.ts. */
export function NotAvailable({ what = "This page" }: { what?: string }) {
  return (
    <div className={s.notAvailable}>
      <Eyebrow>Not available yet</Eyebrow>
      <h1 className={s.h1} style={{ marginTop: 10 }}>{what} isn&rsquo;t switched on for your workspace.</h1>
      <p className={s.meta} style={{ marginTop: 8 }}>Ask your TrueBind contact if you need it.</p>
    </div>
  );
}
