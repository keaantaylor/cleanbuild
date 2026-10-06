"use client";

import { useState } from "react";
import { DownloadSimple, EnvelopeSimple, ShieldCheck, WarningCircle } from "@phosphor-icons/react";
import { useMe } from "@/components/auth/AuthGate";
import { api, ApiError } from "@/lib/api";
import { formatBytes, formatNumber, timeAgo } from "@/lib/formatters";
import type { Trail } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { useUi } from "@/lib/ui";
import { EmptyState, ErrorState, LoadingState, StatusPill } from "./ui";

const short = (h: string | null | undefined) => (h ? `${h.slice(0, 12)}…` : "-");
const when = (iso: string | null | undefined) => (iso ? <time title={new Date(iso).toLocaleString("en-GB")}>{timeAgo(iso)}</time> : "-");

const REQ_TONE: Record<string, "ok" | "warn" | "err" | "med" | "muted"> = { OPEN: "warn", ANSWERED: "med", RESOLVED: "ok" };
const CORR_TONE: Record<string, "ok" | "warn" | "err" | "med" | "muted"> = { PROPOSED: "warn", APPROVED: "ok", REJECTED: "muted" };

function Section({ title, sub, children, action }: { title: string; sub?: string; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <section className="tb-card flex flex-col gap-3 p-4 sm:p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div className="flex flex-col gap-0.5">
          <h2 className="m-0 text-[15px] font-medium">{title}</h2>
          {sub && <span className="text-[12.5px]" style={{ color: "var(--muted)" }}>{sub}</span>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

/** The bordereau from arrival to approval: source hash, processing, corrections
 * under policy, corrected versions, information requests and the audit chain. */
export function TrailView({ reportId }: { reportId: string }) {
  const trail = useApi(() => api.reportTrail(reportId), [reportId]);
  if (trail.error && !trail.data) return <ErrorState title="The trail could not be loaded" message={trail.error} onRetry={trail.reload} />;
  if (!trail.data) return <LoadingState label="Loading the trail" rows={6} />;
  return <TrailBody t={trail.data} reportId={reportId} reload={trail.reload} />;
}

function TrailBody({ t, reportId, reload }: { t: Trail; reportId: string; reload: () => void }) {
  const me = useMe();
  const { toast } = useUi();
  const [busy, setBusy] = useState<string | null>(null);
  const canWrite = !!me?.can_write;
  const fv = t.final_verification;

  const run = async (key: string, fn: () => Promise<unknown>, ok: string) => {
    setBusy(key);
    try {
      await fn();
      toast(ok, "ok");
      reload();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "That didn't work. Try again.", "err");
    } finally {
      setBusy(null);
    }
  };

  const checks: [string, boolean | null][] = [
    ["Source file unchanged since arrival", fv.source_unchanged],
    ["Audit chain intact", fv.audit_chain_intact],
    ["No open issues", fv.open_issues === 0],
    ["Every approved correction re-checked", fv.unverified_corrections === 0],
  ];

  return (
    <div className="flex flex-col gap-4">
      <Section title="Final verification" sub={fv.approved_version ? `Version ${fv.approved_version.number} approved by ${fv.approved_version.approved_by ?? "-"}` : "No corrected version approved yet"}>
        <ul className="m-0 grid list-none gap-2 p-0 sm:grid-cols-2">
          {checks.map(([label, ok]) => (
            <li key={label} className="flex items-center gap-2 text-[13.5px]">
              {ok ? <ShieldCheck size={16} weight="fill" style={{ color: "var(--ok)" }} aria-hidden /> : <WarningCircle size={16} weight="fill" style={{ color: ok === null ? "var(--faint)" : "var(--warn)" }} aria-hidden />}
              <span>{label}</span>
              <span className="sr-only">{ok ? ": yes" : ok === null ? ": not known" : ": no"}</span>
              {label === "No open issues" && fv.open_issues > 0 && <span className="tnum text-[12.5px]" style={{ color: "var(--muted)" }}>({formatNumber(fv.open_issues)} open)</span>}
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Arrival">
        <dl className="m-0 grid gap-x-6 gap-y-2 text-[13px] sm:grid-cols-[160px_1fr]">
          <dt style={{ color: "var(--muted)" }}>File</dt><dd className="m-0 break-all">{t.arrival.file_name} · {formatBytes(t.arrival.size)}</dd>
          <dt style={{ color: "var(--muted)" }}>SHA-256</dt><dd className="mono m-0 break-all">{t.arrival.sha256 ?? "-"}</dd>
          <dt style={{ color: "var(--muted)" }}>Channel</dt><dd className="m-0">{t.arrival.channel}{t.arrival.sender ? ` · ${t.arrival.sender}` : ""}{t.arrival.programme ? ` · ${t.arrival.programme}` : ""}</dd>
          <dt style={{ color: "var(--muted)" }}>Received</dt><dd className="m-0">{when(t.arrival.received_at)}{t.arrival.received_by ? ` by ${t.arrival.received_by}` : ""}</dd>
          <dt style={{ color: "var(--muted)" }}>Rules</dt><dd className="mono m-0">{t.analysis.ruleset_versions.join(", ")}</dd>
        </dl>
      </Section>

      <Section
        title="Corrected versions"
        sub="The source file is never changed. Approved corrections go into a new version, each with its own hash."
        action={canWrite && (
          <button type="button" className="tb-btn" disabled={busy === "create"} onClick={() => run("create", () => api.createVersion(reportId), "Corrected version created")}>
            Create corrected version
          </button>
        )}
      >
        {t.versions.length === 0 ? (
          <p className="m-0 text-[13px]" style={{ color: "var(--muted)" }}>No versions yet. Approve corrections in the workbook, then create a version here.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] border-collapse text-[13px]">
              <thead>
                <tr style={{ color: "var(--muted)" }}>
                  {["Version", "Kind", "Corrections", "Hash", "Created", ""].map((h) => <th key={h} className="px-2 py-2 text-left font-normal" style={{ boxShadow: "0 1px 0 var(--line)" }}>{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {t.versions.map((v) => (
                  <tr key={v.id} style={{ boxShadow: "0 1px 0 var(--line)" }}>
                    <td className="tnum px-2 py-2.5">v{v.number}</td>
                    <td className="px-2 py-2.5">{v.kind}</td>
                    <td className="tnum px-2 py-2.5">{formatNumber(v.corrections)}</td>
                    <td className="mono px-2 py-2.5" title={v.sha256}>{short(v.sha256)}</td>
                    <td className="px-2 py-2.5">{when(v.created_at)}{v.created_by ? ` · ${v.created_by}` : ""}</td>
                    <td className="whitespace-nowrap px-2 py-2.5 text-right">
                      <a className="tb-btn tb-btn-ghost" href={api.versionDownloadUrl(reportId, v.id)}><DownloadSimple size={14} /> Download</a>
                      {canWrite && v.kind === "corrected" && (
                        <button type="button" className="tb-btn tb-btn-primary ml-1" disabled={busy === v.id} onClick={() => run(v.id, () => api.approveVersion(reportId, v.id), `Version ${v.number} approved`)}>
                          Approve
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Section title="Corrections" sub="Every proposed change, its execution policy and who decided it.">
        {t.corrections.length === 0 ? (
          <p className="m-0 text-[13px]" style={{ color: "var(--muted)" }}>No corrections proposed for this file.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] border-collapse text-[13px]">
              <thead>
                <tr style={{ color: "var(--muted)" }}>
                  {["Cell", "Before → after", "Policy", "Status", "Decided"].map((h) => <th key={h} className="px-2 py-2 text-left font-normal" style={{ boxShadow: "0 1px 0 var(--line)" }}>{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {t.corrections.map((c) => (
                  <tr key={c.id} style={{ boxShadow: "0 1px 0 var(--line)" }}>
                    <td className="mono px-2 py-2.5">{c.sheet}!{c.cell}</td>
                    <td className="px-2 py-2.5"><span className="mono">{c.before ?? "(blank)"}</span> → <span className="mono">{c.after ?? "(blank)"}</span>{c.why && <div className="text-[12px]" style={{ color: "var(--muted)" }}>{c.why}</div>}</td>
                    <td className="px-2 py-2.5" title={c.policy_reason ?? undefined}>{(c.policy ?? "-").replace(/_/g, " ").toLowerCase()}</td>
                    <td className="px-2 py-2.5"><StatusPill tone={CORR_TONE[c.status] ?? "muted"}>{c.status.toLowerCase()}</StatusPill></td>
                    <td className="px-2 py-2.5">{c.decided_by ? <>{c.decided_by} · {when(c.decided_at)}</> : "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Section title="Information requests" sub="Queries sent to the sender, each with a [TB-n] reference. Replies are stored as received.">
        {t.information_requests.length === 0 ? (
          <EmptyState icon={<EnvelopeSimple />} title="No requests sent" body="Use “Send to sender” on an issue in Review issues to ask the sender for the missing information." />
        ) : (
          <ul className="m-0 flex list-none flex-col gap-2 p-0">
            {t.information_requests.map((r) => (
              <li key={r.id} className="flex flex-col gap-1 rounded-md p-3" style={{ boxShadow: "inset 0 0 0 1px var(--line)" }}>
                <div className="flex flex-wrap items-center gap-2 text-[13.5px]">
                  <span className="mono">{r.reference}</span>
                  <span className="font-medium">{r.subject}</span>
                  <StatusPill tone={REQ_TONE[r.status] ?? "muted"}>{r.status.toLowerCase()}</StatusPill>
                </div>
                <span className="text-[12.5px]" style={{ color: "var(--muted)" }}>
                  {formatNumber(r.issues)} {r.issues === 1 ? "issue" : "issues"} · to {r.to ?? "-"} · {when(r.created_at)}
                  {r.delivery_error ? ` · not delivered: ${r.delivery_error}` : ""}
                  {r.replies.length ? ` · ${r.replies.length} ${r.replies.length === 1 ? "reply" : "replies"}` : ""}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Audit chain" sub={fv.audit_chain_intact ? `Chain intact · ${formatNumber(t.audit.length)} entries for this file` : `Chain broken at entry #${fv.audit_chain_first_bad_seq ?? "?"}`}>
        <ol className="m-0 flex max-h-[420px] list-none flex-col overflow-y-auto p-0 text-[13px]">
          {t.audit.slice().reverse().map((e) => (
            <li key={e.seq} className="grid grid-cols-[56px_1fr_auto] gap-3 py-2" style={{ boxShadow: "0 1px 0 var(--line)" }}>
              <span className="mono" style={{ color: "var(--faint)" }}>#{e.seq}</span>
              <span>{e.action.replace(/_/g, " ").toLowerCase()} <span style={{ color: "var(--muted)" }}>by {e.actor}</span></span>
              <span className="text-[12px]" style={{ color: "var(--muted)" }}>{when(e.at)}</span>
            </li>
          ))}
        </ol>
      </Section>
    </div>
  );
}
