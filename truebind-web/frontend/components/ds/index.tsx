"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { Icon, type IconName } from "./Icon";
import s from "./ds.module.css";

export { Icon };
export * from "./data";
export * from "./overlays";
export type { IconName };
export const ds = s;

export type Tone = "neutral" | "good" | "warn" | "bad" | "info" | "brand" | "violet" | "live";

export function PageHeader({ eyebrow, title, description, actions, breadcrumbs }: {
  eyebrow?: string; title: ReactNode; description?: ReactNode; actions?: ReactNode; breadcrumbs?: ReactNode;
}) {
  return (
    <header className={s.pageHeader}>
      <div style={{ minWidth: 0 }}>
        {breadcrumbs && <div className={s.pageCrumbs}>{breadcrumbs}</div>}
        {!breadcrumbs && eyebrow && <p className={s.pageEyebrow}>{eyebrow}</p>}
        <h1 className={s.pageTitle}>{title}</h1>
        {description && <p className={s.pageDescription}>{description}</p>}
      </div>
      {actions && <div className={s.pageActions}>{actions}</div>}
    </header>
  );
}

export function Panel({ title, subtitle, icon, actions, children, flush, className }: {
  title?: ReactNode; subtitle?: ReactNode; icon?: IconName; actions?: ReactNode; children: ReactNode;
  flush?: boolean; className?: string;
}) {
  return (
    <section className={[s.panel, className].filter(Boolean).join(" ")}>
      {(title || actions) && (
        <div className={s.panelHead}>
          <div style={{ minWidth: 0 }}>
            {title && <h2 className={s.panelTitle}>{icon && <Icon name={icon} />}{title}</h2>}
            {subtitle && <p className={s.panelSubtitle}>{subtitle}</p>}
          </div>
          {actions && <div className={s.pageActions}>{actions}</div>}
        </div>
      )}
      <div className={flush ? s.panelFlush : s.panelBody}>{children}</div>
    </section>
  );
}

export function StatTile({ label, value, hint, tone = "neutral", href, icon }: {
  label: string; value: ReactNode; hint?: ReactNode; tone?: Exclude<Tone, "brand" | "violet" | "live">;
  href?: string; icon?: IconName;
}) {
  const body = (
    <>
      <span className={s.statBar} aria-hidden="true" />
      <span className={s.statLabel}>{icon && <Icon name={icon} size={14} />}{label}</span>
      <span className={s.statValue}>{value}</span>
      {hint && <span className={s.statHint}>{hint}</span>}
    </>
  );
  const cls = `${s.stat} ${s[`tone-${tone}`]}`;
  return href ? <Link href={href} className={cls}>{body}</Link> : <div className={cls}>{body}</div>;
}

export function Pill({ tone = "neutral", children, pulse, dot = true, title }: {
  tone?: Tone; children: ReactNode; pulse?: boolean; dot?: boolean; title?: string;
}) {
  return (
    <span className={[s.pill, s[`pill-${tone}`], pulse ? s.pulse : ""].join(" ")} title={title}>
      {dot && <span className={s.pillDot} aria-hidden="true" />}
      {children}
    </span>
  );
}

export function Skeleton({ width = "100%", height = 14, radius }: { width?: number | string; height?: number | string; radius?: number }) {
  return <span className={s.skeleton} style={{ display: "block", width, height, borderRadius: radius }} aria-hidden="true" />;
}

export function SkeletonRows({ rows = 5 }: { rows?: number }) {
  return (
    <div className={s.stack} style={{ gap: 12 }} aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => <Skeleton key={i} height={16} width={`${92 - (i % 3) * 14}%`} />)}
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return <span className={s.spinner} role="status" aria-label={label ?? "Loading"} />;
}

export function EmptyState({ icon = "inbox", title, body, action }: {
  icon?: IconName; title: string; body?: ReactNode; action?: ReactNode;
}) {
  return (
    <div className={s.empty}>
      <span className={s.emptyIcon}><Icon name={icon} size={22} /></span>
      <p className={s.emptyTitle}>{title}</p>
      {body && <p className={s.emptyBody}>{body}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ title = "Something went wrong", message, onRetry, details }: {
  title?: string; message: ReactNode; onRetry?: () => void; details?: string;
}) {
  return (
    <div className={s.error} role="alert">
      <p className={s.errorTitle}><Icon name="alertCircle" />{title}</p>
      <p className={s.errorBody}>{message}</p>
      {onRetry && <button type="button" onClick={onRetry} className={s.input} style={{ cursor: "pointer", fontWeight: 600 }}>Try again</button>}
      {details && (
        <details className={s.details}>
          <summary>View technical details</summary>
          <code className={s.mono}>{details}</code>
        </details>
      )}
    </div>
  );
}

export function BarList({ items, max, format = (n) => n.toLocaleString("en-GB") }: {
  items: { label: string; value: number; tone?: "bad" | "warn" | "good" | "violet" | "neutral"; href?: string }[];
  max?: number; format?: (n: number) => string;
}) {
  const top = max ?? Math.max(1, ...items.map((i) => i.value));
  return (
    <ul className={s.barList}>
      {items.map((i) => (
        <li key={i.label} className={s.barRow}>
          <span className={s.barLabel}>{i.href ? <Link href={i.href}>{i.label}</Link> : i.label}</span>
          <span className={s.barValue}>{format(i.value)}</span>
          <span className={s.barTrack} aria-hidden="true">
            <span className={`${s.barFill} ${i.tone ? s[`fill-${i.tone}`] : ""}`}
                  style={{ width: `${Math.max(i.value > 0 ? 2 : 0, (100 * i.value) / top)}%` }} />
          </span>
        </li>
      ))}
    </ul>
  );
}

export function Sparkbars({ values, labels, title }: { values: number[]; labels?: string[]; title: string }) {
  const max = Math.max(1, ...values);
  const w = 100 / Math.max(values.length, 1);
  return (
    <svg className={s.spark} viewBox="0 0 100 40" preserveAspectRatio="none" role="img" aria-label={title}>
      {values.map((v, i) => {
        const h = v === 0 ? 2 : Math.max(3, (36 * v) / max);
        return (
          <rect key={i} x={i * w + w * 0.15} width={w * 0.7} y={40 - h} height={h} rx={1}
                className={v === 0 ? s.sparkBarZero : s.sparkBar}>
            <title>{`${labels?.[i] ?? i}: ${v}`}</title>
          </rect>
        );
      })}
    </svg>
  );
}

export type StageState = "done" | "active" | "pending" | "failed";

export function StageTimeline({ stages }: {
  stages: { key: string; label: string; state: StageState; detail?: ReactNode; meta?: ReactNode }[];
}) {
  return (
    <ol className={s.stages}>
      {stages.map((st) => (
        <li key={st.key} className={`${s.stage} ${s[st.state]}`} aria-current={st.state === "active" ? "step" : undefined}>
          <span className={s.stageDot}>
            {st.state === "done" ? <Icon name="check" size={14} strokeWidth={2.5} />
              : st.state === "failed" ? <Icon name="x" size={14} strokeWidth={2.5} />
              : st.state === "active" ? <span className={s.spinner} style={{ width: 14, height: 14 }} aria-hidden="true" />
              : null}
          </span>
          <div>
            <div className={s.stageLabel}>{st.label}</div>
            {st.detail && <div className={s.stageDetail}>{st.detail}</div>}
          </div>
          <span className={s.stageMeta}>{st.meta}</span>
        </li>
      ))}
    </ol>
  );
}

export function KeyValue({ items }: { items: [ReactNode, ReactNode][] }) {
  return (
    <dl className={s.kv}>
      {items.map(([k, v], i) => (
        <div key={i} style={{ display: "contents" }}><dt>{k}</dt><dd>{v}</dd></div>
      ))}
    </dl>
  );
}

/** Report status -> label + tone, shared by every table and header. */
export function statusMeta(status: string): { label: string; tone: Tone; live?: boolean } {
  switch (status) {
    case "UPLOADED": case "QUEUED": return { label: "Queued", tone: "info", live: true };
    case "INGESTING": return { label: "Reading workbook", tone: "info", live: true };
    case "PROCESSING": return { label: "Processing", tone: "info", live: true };
    case "WAITING_FOR_REVIEW": return { label: "Needs mapping review", tone: "warn" };
    case "COMPLETE": return { label: "Complete", tone: "good" };
    case "FAILED": return { label: "Failed", tone: "bad" };
    case "CANCELLED": return { label: "Cancelled", tone: "neutral" };
    case "EXPIRED": return { label: "Expired", tone: "neutral" };
    default: return { label: status, tone: "neutral" };
  }
}

export function StatusPill({ status }: { status: string }) {
  const m = statusMeta(status);
  return <Pill tone={m.tone} pulse={m.live}>{m.label}</Pill>;
}

export function severityTone(sev: string): Tone {
  return sev === "CRITICAL" ? "bad" : sev === "HIGH" ? "warn" : sev === "MEDIUM" ? "info" : "neutral";
}
