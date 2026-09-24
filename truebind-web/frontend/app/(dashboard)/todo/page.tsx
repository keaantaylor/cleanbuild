"use client";

import Link from "next/link";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { formatDate } from "@/lib/formatters";
import { ButtonLink } from "@/components/ui/Button";
import { EmptyState, ErrorState, Icon, Panel, PageHeader, Pill, StatTile, ds, severityTone } from "@/components/ds";
import type { IconName } from "@/components/ds";
import { PageSkeleton } from "@/components/layout/ShellSkeleton";
import styles from "./todo.module.css";

const KIND_ICON: Record<string, IconName> = {
  mapping: "layers", failed: "alertCircle", stalled: "server", critical: "exceptions", duplicates: "duplicates",
  obligations: "clock", exports: "exports",
};

export default function WorkQueuePage() {
  const q = useApi(() => api.workQueue(), [], 15_000);
  const obligations = useApi(() => api.listObligations({}), []);
  if (q.loading && !q.data) return <PageSkeleton label="Loading work queue" />;
  if (q.error && !q.data) return <ErrorState title="The work queue could not be loaded" message={q.error} onRetry={q.reload} />;
  const items = q.data?.items ?? [];
  const by = (p: string) => items.filter((i) => i.priority === p).length;
  const open = (obligations.data ?? []).filter((o) => o.status !== "RESOLVED");

  return (
    <>
      <PageHeader eyebrow="Operate" title="Work queue"
        description="Everything waiting on a person, most urgent first. Items leave the queue when the underlying work is done." />
      <div className={ds.stack}>
        <div className={`${ds.grid} ${ds.cols4}`}>
          <StatTile label="Critical" value={by("CRITICAL")} tone={by("CRITICAL") ? "bad" : "good"} icon="alertCircle" />
          <StatTile label="High" value={by("HIGH")} tone={by("HIGH") ? "warn" : "good"} icon="exceptions" />
          <StatTile label="Medium" value={by("MEDIUM")} tone="info" icon="info" />
          <StatTile label="Open follow-ups" value={open.length} tone="neutral" icon="todo" />
        </div>
        <Panel title="Actions" icon="todo" flush>
          {items.length === 0 ? (
            <EmptyState icon="check" title="Nothing waiting on you" body="New files, mapping reviews, critical findings and duplicate candidates will appear here."
              action={<ButtonLink href="/upload" variant="secondary">Upload a bordereau</ButtonLink>} />
          ) : (
            <ul className={styles.queue}>
              {items.map((i, idx) => (
                <li key={`${i.kind}-${i.report_id ?? idx}`} className={styles.item}>
                  <span className={`${styles.icon} ${styles[`p-${i.priority}`]}`}><Icon name={KIND_ICON[i.kind] ?? "info"} size={17} /></span>
                  <div className={styles.body}>
                    <p className={styles.title}>{i.title}</p>
                    <p className={styles.detail}>{i.detail}</p>
                  </div>
                  <Pill tone={severityTone(i.priority)}>{i.priority.toLowerCase()}</Pill>
                  {i.href && <ButtonLink href={i.href} variant="secondary" size="sm">Open</ButtonLink>}
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel title="Assigned follow-ups" icon="clock" subtitle="Created from findings on the Exceptions page.">
          {open.length === 0 ? <p className={styles.detail}>No open follow-ups.</p> : (
            <ul className={styles.queue}>
              {open.map((o) => (
                <li key={o.id} className={styles.item}>
                  <span className={styles.icon}><Icon name="todo" size={17} /></span>
                  <div className={styles.body}>
                    <p className={styles.title}>{o.note || "Follow-up"}</p>
                    <p className={styles.detail}>{o.owner ? `Owner: ${o.owner}` : "Unassigned"} · due {formatDate(o.deadline)} · <Link href={`/reports/${o.report_id}`}>report</Link></p>
                  </div>
                  <Pill tone={o.status === "OVERDUE" ? "bad" : "info"}>{o.status.toLowerCase().replace("_", " ")}</Pill>
                  <span />
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </>
  );
}
