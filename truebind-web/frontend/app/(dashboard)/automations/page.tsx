"use client";

import Link from "next/link";
import { ArrowRight, EnvelopeSimple, Lightning, PaperPlaneTilt, Warning } from "@phosphor-icons/react";
import { api } from "@/lib/api";
import type { Channel, ChannelStatus } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { ErrorState, LoadingState, PageHeader, StatusPill } from "@/components/nocturne/ui";

const STATUS: Record<ChannelStatus, { label: string; tone: "ok" | "med" | "warn" | "muted" }> = {
  active: { label: "Live", tone: "ok" },
  not_set_up: { label: "Ready to set up", tone: "med" },
  not_configured: { label: "Not configured on the server", tone: "warn" },
  planned: { label: "Planned", tone: "muted" },
};

function Card({ icon: Icon, title, state, what, today, action }: { icon: React.ElementType; title: string; state: { label: string; tone: "ok" | "med" | "warn" | "muted" }; what: string; today: string; action?: React.ReactNode }) {
  const live = state.tone === "ok";
  return (
    <article className="flex flex-col gap-3 rounded-md p-5" style={{ background: live ? "color-mix(in srgb, var(--ok) 6%, var(--surface))" : "var(--surface)", boxShadow: live ? "var(--shadow), inset 0 0 0 1px color-mix(in srgb, var(--ok) 40%, transparent)" : "var(--shadow)" }}>
      <span className="flex items-center justify-between gap-2">
        <span className="grid h-10 w-10 place-items-center rounded-md text-[18px]" style={{ background: "var(--accentTint)", color: "var(--accentText)" }}>
          <Icon />
        </span>
        <StatusPill tone={state.tone}>{state.label}</StatusPill>
      </span>
      <span className="text-[15px] font-medium">{title}</span>
      <span className="text-[13px] leading-[1.5]" style={{ color: "var(--muted)" }}>{what}</span>
      <span className="flex-1 text-[12.5px] leading-[1.5]">
        <b className="font-medium">Today:</b> <span style={{ color: "var(--muted)" }}>{today}</span>
      </span>
      {action}
    </article>
  );
}

function ChannelList({ items }: { items: Channel[] }) {
  return (
    <ul className="m-0 flex list-none flex-col p-0">
      {items.map((c) => (
        <li key={c.id} className="flex items-start justify-between gap-3 py-3" style={{ boxShadow: "0 1px 0 var(--line)" }}>
          <span className="flex min-w-0 flex-col">
            <span className="text-[13.5px] font-medium">{c.name}</span>
            <span className="text-[12.5px]" style={{ color: "var(--muted)" }}>{c.detail}</span>
          </span>
          <StatusPill tone={STATUS[c.status].tone}>{STATUS[c.status].label}</StatusPill>
        </li>
      ))}
    </ul>
  );
}

export default function AutomationsPage() {
  const { data, error, loading, reload } = useApi(() => api.channels());
  if (loading && !data) return <div className="px-4 pt-8 sm:px-6"><LoadingState label="Loading automations" rows={8} /></div>;
  if (error || !data) return <div className="px-4 pt-8 sm:px-6"><ErrorState title="Automations could not be loaded" message={error} onRetry={reload} /></div>;

  const email = data.inbound.find((c) => c.id === "email");
  const out = Object.fromEntries(data.outbound.map((c) => [c.id, c])) as Record<string, Channel | undefined>;
  const liveOut = data.outbound.filter((c) => c.id !== "download" && c.status === "active");
  const sftpAuto = out.sftp_out?.status === "active" && /automatic/.test(out.sftp_out.detail);

  return (
    <div className="flex max-w-[1440px] flex-col gap-7 px-4 pb-12 pt-8 sm:px-6">
      <PageHeader kicker="Deliver" title="Automations" sub="How bordereaux reach TrueBind, what happens to them, and where results go. Every status here comes from your server: live channels work today; anything not built is shown as planned, never as working." />
      <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(240px,1fr))" }}>
        <Card
          icon={EnvelopeSimple}
          title="Email intake"
          state={STATUS[email?.status ?? "planned"]}
          what="Bordereaux emailed to your organisation’s TrueBind address are checked and ingested like uploads, with the sender recorded."
          today={email?.status === "active" ? email.detail : email?.status === "not_set_up" ? "Built and available. Create your intake address in Settings → Channels." : email?.detail ?? "Not available on this server."}
          action={email?.status === "not_set_up" ? <Link href="/settings?tab=channels" className="tb-btn self-start !py-1.5 text-[12.5px]">Set up</Link> : undefined}
        />
        <Card icon={Lightning} title="Automatic processing" state={STATUS.active} what="Every file is read, its sheets and header rows detected and a column mapping proposed the moment it arrives." today="Validation starts after a person confirms the mapping; that confirmation is deliberate and audited." />
        <Card
          icon={PaperPlaneTilt}
          title="Outbound delivery"
          state={liveOut.length ? { label: sftpAuto ? "Live · SFTP automatic" : "Live · on demand", tone: "ok" } : { label: "Downloads only", tone: "med" }}
          what="Claims, exceptions and audit outputs sent by email, SFTP or signed webhooks, with every delivery recorded."
          today={liveOut.length ? `${liveOut.map((c) => c.name).join(", ")} ${liveOut.length === 1 ? "is" : "are"} live.${sftpAuto ? " SFTP sends automatically when a report completes." : " Send from any report or Exports."}` : "Downloads work now. Set up email, SFTP or webhooks in Settings → Channels."}
          action={!liveOut.length ? <Link href="/settings?tab=channels" className="tb-btn self-start !py-1.5 text-[12.5px]">Set up</Link> : undefined}
        />
        <Card icon={Warning} title="Exception routing" state={{ label: "Manual today", tone: "med" }} what="Findings are routed to an owner with a deadline and tracked in the work queue until resolved." today="Assign and create follow-ups from the exception centre. Rule-based automatic routing is planned." />
      </div>

      <section className="tb-card flex flex-col gap-4 p-5">
        <div className="flex flex-col gap-1">
          <span className="text-[15px] font-medium">Processing pipeline</span>
          <span className="text-[13px]" style={{ color: "var(--muted)" }}>Every file, from any channel, runs the same audited steps.</span>
        </div>
        <ol className="m-0 flex list-none flex-wrap items-center gap-2 p-0">
          {data.pipeline.map((s, i) => (
            <li key={s} className="flex items-center gap-2">
              <span className="flex items-center gap-2 rounded-md px-3 py-2 text-[13px]" style={{ boxShadow: "inset 0 0 0 1px var(--line2)" }}>
                <span className="tnum text-[11px]" style={{ color: "var(--faint)" }}>{String(i + 1).padStart(2, "0")}</span>
                {s}
              </span>
              {i < data.pipeline.length - 1 && <ArrowRight size={13} style={{ color: "var(--faint)" }} />}
            </li>
          ))}
        </ol>
        <span className="text-[12.5px]" style={{ color: "var(--faint)" }}>
          Upload limit {data.limits.max_upload_mb} MB · AI-assisted mapping {data.limits.ai_mapping ? `on${data.services?.ai.provider ? ` (${data.services.ai.provider}${data.services.ai.region ? `, ${data.services.ai.region}` : ""})` : ""} — headers only, never cell values` : "off — deterministic alias rules only"}
          {data.services?.fx ? ` · ${data.services.fx.source}${data.services.fx.latest_rate_date ? `, latest ${data.services.fx.latest_rate_date}` : ", not loaded yet"}` : ""}
        </span>
      </section>

      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-2">
        <section className="tb-card flex flex-col px-5 pb-2 pt-4">
          <span className="text-[15px] font-medium">Inbound channels</span>
          <ChannelList items={data.inbound} />
        </section>
        <section className="tb-card flex flex-col px-5 pb-2 pt-4">
          <span className="text-[15px] font-medium">Outbound channels</span>
          <ChannelList items={data.outbound} />
        </section>
      </div>

    </div>
  );
}
