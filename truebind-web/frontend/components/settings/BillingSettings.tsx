"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { formatDate } from "@/lib/formatters";
import { ErrorState, KeyValue, Panel, Pill, SkeletonRows, useToast } from "@/components/ds";
import { Button } from "@/components/ui/Button";
import styles from "./settings.module.css";

const MODULE_LABEL: Record<string, string> = { binder: "Binder compliance", leakage: "Leakage & overpayment", sanctions: "Sanctions screening" };

function errorText(err: unknown): string {
  return err instanceof ApiError ? err.message : "Please try again.";
}

const limit = (n: number | null, unit: string) => (n == null ? `Unlimited ${unit}` : `${n.toLocaleString("en-GB")} ${unit}`);

export function BillingSettings() {
  const toast = useToast();
  const { data, error, loading, reload } = useApi(() => api.getBilling());
  const [busy, setBusy] = useState<string | null>(null);
  if (loading && !data) return <Panel title="Billing"><SkeletonRows rows={3} /></Panel>;
  if (error || !data) return <ErrorState title="Billing could not be loaded" message={error ?? ""} onRetry={reload} />;
  async function go(kind: "checkout" | "portal", plan?: string) {
    setBusy(plan ?? kind);
    try {
      const { url } = kind === "checkout" ? await api.billingCheckout(plan!) : await api.billingPortal();
      window.location.href = url;
    } catch (err) {
      toast({ tone: "bad", title: "Could not open billing", body: errorText(err) });
      setBusy(null);
    }
  }
  if (!data.enforced) {
    return (
      <Panel title="Billing" icon="shield">
        <p className={styles.muted}>Billing is not enforced on this server: every check module is available and nothing is limited.</p>
      </Panel>
    );
  }
  return (
    <Panel title="Billing" icon="shield" subtitle="Subscriptions are handled by Stripe; card and invoice details never reach TrueBind."
      actions={data.customer ? <Button size="sm" variant="ghost" loading={busy === "portal"} onClick={() => go("portal")}>Manage billing</Button> : undefined}>
      <div className={styles.form}>
        <KeyValue items={[
          ["Plan", data.plan ? <strong key="p">{data.plans.find((p) => p.name === data.plan)?.label ?? data.plan}</strong> : "No active plan"],
          ["Status", data.status ? <Pill key="s" tone={["active", "trialing"].includes(data.status) ? "good" : "warn"}>{data.status}</Pill> : "—"],
          ["Renews", data.period_end ? formatDate(data.period_end) : "—"],
          ["Rows processed this month", `${data.rows_this_month.toLocaleString("en-GB")} of ${limit(data.monthly_rows, "rows")}`],
          ["Seats", `${data.seats_used} of ${limit(data.seats, "seats")}`],
          ["Check modules", data.modules && data.modules.length ? data.modules.map((m) => MODULE_LABEL[m] ?? m).join(", ") : "None included"],
        ]} />
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <caption className={styles.srOnly}>Plans</caption>
            <thead><tr><th scope="col">Plan</th><th scope="col">Check modules</th><th scope="col">Rows a month</th><th scope="col">Seats</th><th scope="col"><span className={styles.srOnly}>Actions</span></th></tr></thead>
            <tbody>{data.plans.map((p) => (
              <tr key={p.name}>
                <th scope="row">{p.label}</th>
                <td>{p.modules.map((m) => MODULE_LABEL[m] ?? m).join(", ") || "—"}</td>
                <td>{limit(p.monthly_rows, "")}</td>
                <td>{limit(p.seats, "")}</td>
                <td>{p.name === data.plan ? <Pill tone="good">Current</Pill>
                  : p.purchasable ? <Button size="sm" loading={busy === p.name} onClick={() => go("checkout", p.name)}>Choose</Button>
                  : <span className={styles.help}>Contact us</span>}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
        <p className={styles.help}>Prices are shown by Stripe at checkout.</p>
      </div>
    </Panel>
  );
}
