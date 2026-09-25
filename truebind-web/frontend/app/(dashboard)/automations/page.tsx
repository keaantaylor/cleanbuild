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

type AutoState = "live" | "manual" | "planned" | "not_configured";
const AUTO_LABEL: Record<AutoState, { label: string; tone: "live" | "info" | "neutral" | "warn" }> = {
  live: { label: "Live", tone: "live" }, manual: { label: "Manual today", tone: "info" },
  planned: { label: "Planned", tone: "neutral" }, not_configured: { label: "Not configured", tone: "warn" },
};

function AutomationCard({ icon, title, state, what, today }: {
  icon: "mail" | "automations" | "exceptions" | "calendar"; title: string; state: AutoState; what: string; today: string;
}) {
  const st = AUTO_LABEL[state];
  return (
    <article className={`${styles.card} ${state === "live" ? styles.cardLive : ""}`}>
      <div className={styles.cardHead}>
        <span className={styles.cardIcon}><Icon name={icon} size={18} /></span>
        <Pill tone={st.tone} pulse={state === "live"}>{st.label}</Pill>
      </div>
      <h3 className={styles.cardTitle}>{title}</h3>
      <p className={styles.detail}>{what}</p>
      <p className={styles.today}><strong>Today:</strong> {today}</p>
    </article>
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
        <div className={`${ds.grid} ${ds.cols4}`}>
          <AutomationCard icon="mail" title="E-mail intake" state={(data.inbound.find((c) => c.id === "email")?.status === "active" ? "live" : "planned")}
            what="Bordereaux e-mailed to a dedicated address are ingested automatically, with the sender recorded as provenance."
            today="Not connected. Files arrive by web upload or the API; both record sender and programme." />
          <AutomationCard icon="automations" title="Automatic processing" state="live"
            what="Every file is read, its sheets and header rows detected and a column mapping proposed the moment it arrives — no one has to start it."
            today="Live. Validation starts after a person confirms the mapping; that confirmation is deliberate and audited." />
          <AutomationCard icon="exceptions" title="Exception routing" state="manual"
            what="Findings are routed to an owner with a deadline, and tracked in the work queue until resolved."
            today="Assign and create follow-ups from the exception centre. Rule-based automatic routing is planned." />
          <AutomationCard icon="calendar" title="Scheduled delivery" state={(data.outbound.find((c) => c.id === "email")?.status === "active" ? "manual" : "not_configured")}
            what="Outputs are sent to agreed recipients on a schedule, with every delivery recorded."
            today={data.outbound.find((c) => c.id === "email")?.status === "active"
              ? "E-mail delivery works on demand from any report. Scheduling is planned."
              : "E-mail delivery needs SMTP settings on the server. Downloads work now; scheduling is planned."} />
        </div>
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
