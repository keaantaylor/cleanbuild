"use client";

import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { ErrorState, Icon, Panel, PageHeader, Pill, ds } from "@/components/ds";
import { PageSkeleton } from "@/components/layout/ShellSkeleton";
import type { Channel } from "@/lib/types";
import styles from "./automations.module.css";

function ChannelList({ items }: { items: Channel[] }) {
  return (
    <ul className={styles.channels}>
      {items.map((c) => (
        <li key={c.id} className={`${styles.channel} ${c.status === "active" ? styles.on : ""}`}>
          <div>
            <p className={styles.name}>{c.name}</p>
            <p className={styles.detail}>{c.detail}</p>
          </div>
          <Pill tone={c.status === "active" ? "live" : c.status === "planned" ? "neutral" : "warn"} pulse={c.status === "active"}>
            {c.status === "active" ? "Live" : c.status === "planned" ? "Planned" : "Not configured"}
          </Pill>
        </li>
      ))}
    </ul>
  );
}

export default function AutomationsPage() {
  const { data, error, loading, reload } = useApi(() => api.channels());
  if (loading && !data) return <PageSkeleton label="Loading automations" />;
  if (error || !data) return <ErrorState title="Automations could not be loaded" message={error ?? ""} onRetry={reload} />;
  return (
    <>
      <PageHeader eyebrow="Deliver" title="Automations"
        description="How bordereaux reach TrueBind, what happens to them, and where results go. Live channels work today; planned ones are shown as planned, never as working." />
      <div className={ds.stack}>
        <Panel title="Processing pipeline" icon="automations" subtitle="Every file, from any channel, runs the same audited steps.">
          <ol className={styles.pipeline}>
            {data.pipeline.map((step, i) => (
              <li key={step} className={styles.step}>
                <span className={styles.stepNo}>{i + 1}</span>
                <span className={styles.stepName}>{step}</span>
                {i < data.pipeline.length - 1 && <Icon name="chevronRight" className={styles.arrow} />}
              </li>
            ))}
          </ol>
          <p className={styles.detail}>
            Upload limit {data.limits.max_upload_mb} MB · AI-assisted mapping {data.limits.ai_mapping ? "enabled (headers only, never cell values)" : "off (deterministic mapping only)"}.
          </p>
        </Panel>
        <div className={`${ds.grid} ${ds.cols2}`}>
          <Panel title="Inbound channels" icon="inbox"><ChannelList items={data.inbound} /></Panel>
          <Panel title="Outbound channels" icon="exports"><ChannelList items={data.outbound} /></Panel>
        </div>
        <Panel title="Planned: e-mail to report, hands-free" icon="mail"
          subtitle="The target workflow once the e-mail connector is enabled. Every step already exists for web and API uploads.">
          <ol className={styles.pipeline}>
            {["E-mail arrives", "Attachment detected", "Workbook ingested", "Processing runs", "Exceptions identified", "Report created", "Output sent"].map((s, i, a) => (
              <li key={s} className={styles.step}>
                <span className={styles.stepNo}>{i + 1}</span><span className={styles.stepName}>{s}</span>
                {i < a.length - 1 && <Icon name="chevronRight" className={styles.arrow} />}
              </li>
            ))}
          </ol>
        </Panel>
      </div>
    </>
  );
}
