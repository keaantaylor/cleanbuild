"use client";

/* Data-presentation components: big numbers, confidence, provenance,
 * evidence, timelines and compact controls. Everything here renders only
 * what it is given -- no component invents a delta, a percentage or a
 * progress value it was not handed. */

import Link from "next/link";
import type { ReactNode } from "react";
import { Icon, type IconName } from "./Icon";
import s from "./data.module.css";

export type MetricTone = "neutral" | "good" | "warn" | "bad" | "processing" | "brand";

/** Large-number metric. `compare` is optional and must come from real data
 * (e.g. the previous submission); without it no trend is shown. */
export function MetricCard({ label, value, unit, caption, tone = "neutral", icon, href, compare, size = "md" }: {
  label: string; value: ReactNode; unit?: string; caption?: ReactNode; tone?: MetricTone; icon?: IconName;
  href?: string; compare?: { text: string; direction: "up" | "down" | "flat"; good?: boolean }; size?: "md" | "lg";
}) {
  const body = (
    <>
      <span className={s.metricLabel}>{icon && <Icon name={icon} size={14} />}{label}</span>
      <span className={`${s.metricValue} ${size === "lg" ? s.metricLg : ""}`}>
        {value}{unit && <span className={s.metricUnit}>{unit}</span>}
      </span>
      {(caption || compare) && (
        <span className={s.metricCaption}>
          {compare && (
            <span className={`${s.delta} ${compare.good === undefined ? "" : compare.good ? s.deltaGood : s.deltaBad}`}>
              {compare.direction === "up" ? "▲" : compare.direction === "down" ? "▼" : "■"} {compare.text}
            </span>
          )}
          {caption}
        </span>
      )}
    </>
  );
  const cls = `${s.metric} ${s[`m-${tone}`]}`;
  return href ? <Link href={href} className={`${cls} ${s.metricLink}`}>{body}</Link> : <div className={cls}>{body}</div>;
}

/** Mapping / match confidence. Accepts 0-1 or 0-100 (alias scores). */
export function ConfidenceIndicator({ score, source, compact }: { score: number | null | undefined; source?: string; compact?: boolean }) {
  if (score === null || score === undefined || Number.isNaN(score)) {
    return <span className={s.conf} data-level="none"><span className={s.confTrack}><span className={s.confFill} style={{ width: 0 }} /></span>{!compact && <span className={s.confText}>No match</span>}</span>;
  }
  const pct = Math.max(0, Math.min(100, score <= 1 ? score * 100 : score));
  const level = pct >= 90 ? "high" : pct >= 70 ? "medium" : "low";
  const word = level === "high" ? "High" : level === "medium" ? "Medium" : "Low";
  return (
    <span className={s.conf} data-level={level} title={`${Math.round(pct)}% confidence${source ? ` · ${source}` : ""}`}>
      <span className={s.confTrack} aria-hidden="true"><span className={s.confFill} style={{ width: `${pct}%` }} /></span>
      <span className={s.confText}>{compact ? `${Math.round(pct)}%` : `${word} · ${Math.round(pct)}%`}</span>
    </span>
  );
}

/** Where a value came from: file › sheet › row › column. */
export function SourceReference({ file, sheet, row, column }: { file?: string; sheet?: string; row?: number | string; column?: string }) {
  const parts = [
    file && { k: "file", v: file, icon: "file" as IconName },
    sheet && { k: "sheet", v: sheet, icon: "layers" as IconName },
    row !== undefined && row !== null && row !== "" && { k: "row", v: `Row ${row}`, icon: null },
    column && { k: "column", v: column, icon: null },
  ].filter(Boolean) as { k: string; v: string; icon: IconName | null }[];
  if (!parts.length) return null;
  return (
    <span className={s.source} aria-label={`Source: ${parts.map((p) => p.v).join(", ")}`}>
      {parts.map((p, i) => (
        <span key={p.k} className={s.sourcePart}>
          {i > 0 && <Icon name="chevronRight" size={12} className={s.sourceSep} />}
          {p.icon && <Icon name={p.icon} size={12} />}
          <span className={s.sourceText}>{p.v}</span>
        </span>
      ))}
    </span>
  );
}

/** Labelled facts that justify a finding. Values are shown verbatim. */
export function EvidencePanel({ title = "Evidence", items, children }: {
  title?: string; items: { label: ReactNode; value: ReactNode; emphasis?: boolean }[]; children?: ReactNode;
}) {
  return (
    <section className={s.evidence} aria-label={title}>
      <h3 className={s.evidenceTitle}><Icon name="search" size={14} />{title}</h3>
      <dl className={s.evidenceList}>
        {items.map((it, i) => (
          <div key={i} className={`${s.evidenceRow} ${it.emphasis ? s.evidenceEmph : ""}`}>
            <dt>{it.label}</dt><dd>{it.value}</dd>
          </div>
        ))}
      </dl>
      {children}
    </section>
  );
}

export function SegmentedControl<T extends string>({ value, onChange, options, label }: {
  value: T; onChange: (v: T) => void; options: { value: T; label: ReactNode; count?: number }[]; label: string;
}) {
  return (
    <div className={s.segmented} role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button key={o.value} type="button" role="radio" aria-checked={value === o.value}
                className={`${s.segment} ${value === o.value ? s.segmentOn : ""}`} onClick={() => onChange(o.value)}>
          {o.label}{o.count !== undefined && <span className={s.segmentCount}>{o.count.toLocaleString("en-GB")}</span>}
        </button>
      ))}
    </div>
  );
}

export function Breadcrumbs({ items }: { items: { label: string; href?: string }[] }) {
  return (
    <nav aria-label="Breadcrumb" className={s.crumbs}>
      <ol>
        {items.map((it, i) => (
          <li key={i}>
            {i > 0 && <Icon name="chevronRight" size={12} className={s.crumbSep} />}
            {it.href && i < items.length - 1
              ? <Link href={it.href}>{it.label}</Link>
              : <span aria-current={i === items.length - 1 ? "page" : undefined}>{it.label}</span>}
          </li>
        ))}
      </ol>
    </nav>
  );
}

/** Determinate only when real counts are supplied; otherwise an honest
 * indeterminate bar -- never a made-up percentage. */
export function ProgressIndicator({ done, total, label }: { done?: number; total?: number; label: string }) {
  const known = typeof done === "number" && typeof total === "number" && total > 0;
  const pct = known ? Math.min(100, (100 * done) / total) : 0;
  return (
    <div className={s.progress} role="progressbar" aria-label={label}
         aria-valuemin={known ? 0 : undefined} aria-valuemax={known ? total : undefined} aria-valuenow={known ? done : undefined}>
      <span className={`${s.progressFill} ${known ? "" : s.indeterminate}`} style={known ? { width: `${pct}%` } : undefined} />
    </div>
  );
}

export type TimelineTone = "neutral" | "good" | "warn" | "bad" | "processing" | "ai" | "brand";

export function Timeline({ items }: {
  items: { id: string | number; icon: IconName; tone?: TimelineTone; title: ReactNode; meta?: ReactNode; body?: ReactNode }[];
}) {
  return (
    <ol className={s.timeline}>
      {items.map((it) => (
        <li key={it.id} className={s.tlItem}>
          <span className={`${s.tlIcon} ${s[`t-${it.tone ?? "neutral"}`]}`}><Icon name={it.icon} size={14} /></span>
          <div className={s.tlBody}>
            <p className={s.tlTitle}>{it.title}</p>
            {it.body && <div className={s.tlText}>{it.body}</div>}
            {it.meta && <p className={s.tlMeta}>{it.meta}</p>}
          </div>
        </li>
      ))}
    </ol>
  );
}

/** A file as an object: name, type, size, and whatever facts are known. */
export function FileCard({ name, meta, status, href, actions }: {
  name: string; meta?: ReactNode; status?: ReactNode; href?: string; actions?: ReactNode;
}) {
  const ext = name.split(".").pop()?.toUpperCase() ?? "FILE";
  const title = href ? <Link href={href} className={s.fileName}>{name}</Link> : <span className={s.fileName}>{name}</span>;
  return (
    <div className={s.fileCard}>
      <span className={s.fileGlyph} aria-hidden="true"><span>{ext.slice(0, 4)}</span></span>
      <div className={s.fileMain}>
        {title}
        {meta && <span className={s.fileMeta}>{meta}</span>}
      </div>
      {status}
      {actions}
    </div>
  );
}

/** Section heading inside long pages (report sections, landing). */
export function SectionHeading({ id, eyebrow, title, description, actions }: {
  id?: string; eyebrow?: string; title: ReactNode; description?: ReactNode; actions?: ReactNode;
}) {
  return (
    <div className={s.section} id={id}>
      <div style={{ minWidth: 0 }}>
        {eyebrow && <p className={s.sectionEyebrow}>{eyebrow}</p>}
        <h2 className={s.sectionTitle}>{title}</h2>
        {description && <p className={s.sectionDesc}>{description}</p>}
      </div>
      {actions && <div className={s.sectionActions}>{actions}</div>}
    </div>
  );
}

/** Health ring: a real 0-100 score drawn as an arc. */
export function HealthRing({ score, label, size = 132 }: { score: number; label: string; size?: number }) {
  const r = 52, c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, score));
  const tone = pct >= 90 ? "good" : pct >= 70 ? "warn" : "bad";
  return (
    <div className={`${s.ring} ${s[`ring-${tone}`]}`} style={{ width: size, height: size }} role="img"
         aria-label={`${label}: ${Math.round(pct)} out of 100`}>
      <svg viewBox="0 0 120 120" width={size} height={size} aria-hidden="true">
        <circle cx="60" cy="60" r={r} className={s.ringTrack} />
        <circle cx="60" cy="60" r={r} className={s.ringArc} strokeDasharray={c}
                strokeDashoffset={c * (1 - pct / 100)} transform="rotate(-90 60 60)" />
      </svg>
      <span className={s.ringValue}>{Math.round(pct)}<span className={s.ringOf}>/100</span></span>
    </div>
  );
}
