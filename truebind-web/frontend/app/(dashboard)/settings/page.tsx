"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { useMe } from "@/components/auth/AuthGate";
import { hasPermission } from "@/lib/auth";
import { LoadingState, PageHeader } from "@/components/nocturne/ui";
import { BillingSettings, BindersSettings, ChannelsSettings, MembersSettings, OrganisationSettings, SanctionsSettings, SecuritySettings, SsoSettings } from "@/components/nocturne/settings";

export default function SettingsPage() {
  return (
    <Suspense>
      <Settings />
    </Suspense>
  );
}

function Settings() {
  const me = useMe();
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  if (!me) return <div className="px-4 pt-8 sm:px-9"><LoadingState label="Loading settings" rows={6} /></div>;
  const can = (p: string) => hasPermission(me.permissions, p);
  const tabs = [
    ...(can("org:read") ? [["organisation", "Organisation"]] : []),
    ...(can("member:read") ? [["members", "Members"]] : []),
    ["security", "Security"],
    ...(can("org:read") && me.role !== "SENDER" ? [["sso", "Single sign-on"]] : []),
    ...(can("org:read") && me.role !== "SENDER" ? [["channels", "Channels"]] : []),
    ...(can("data:read") ? [["binders", "Binders"]] : []),
    ...(can("data:read") ? [["sanctions", "Sanctions lists"]] : []),
    ...(can("billing:manage") ? [["billing", "Billing"]] : []),
  ] as [string, string][];
  const requested = params.get("tab");
  const active = tabs.some(([v]) => v === requested) ? requested! : me.mfa?.setup_required ? "security" : tabs[0][0];

  return (
    <div className="flex max-w-[1200px] flex-col gap-6 px-4 pb-12 pt-8 sm:px-9">
      <PageHeader kicker="Workspace" title="Settings" sub={`${me.tenant.name} · signed in as ${me.user.email}`} />
      <label className="sm:hidden">
        <span className="tb-label">Section</span>
        <select className="tb-input" value={active} onChange={(e) => router.replace(`${pathname}?tab=${e.target.value}`)}>
          {tabs.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      </label>
      <div className="hidden flex-wrap gap-1 sm:flex" style={{ boxShadow: "0 1px 0 var(--line)" }} role="tablist" aria-label="Settings sections">
        {tabs.map(([v, l]) => (
          <button key={v} type="button" role="tab" aria-selected={active === v} onClick={() => router.replace(`${pathname}?tab=${v}`)} className="cursor-pointer whitespace-nowrap px-3.5 py-2.5 text-[13.5px] transition-colors hover:text-[var(--text)]" style={{ color: active === v ? "var(--text)" : "var(--muted)", boxShadow: active === v ? "inset 0 -2px 0 var(--accent)" : "none" }}>
            {l}
          </button>
        ))}
      </div>
      <div key={active} className="anim-fade">
        {active === "organisation" && <OrganisationSettings canManage={can("org:manage")} />}
        {active === "members" && <MembersSettings canManage={can("member:manage")} myRole={String(me.role)} myUserId={me.user.id} />}
        {active === "security" && <SecuritySettings required={params.get("required") === "1" || Boolean(me.mfa?.setup_required)} />}
        {active === "sso" && <SsoSettings canManage={can("org:manage")} />}
        {active === "channels" && <ChannelsSettings canManage={can("org:manage")} />}
        {active === "binders" && <BindersSettings canManage={can("data:write")} />}
        {active === "sanctions" && <SanctionsSettings canManage={can("data:write")} />}
        {active === "billing" && <BillingSettings />}
      </div>
    </div>
  );
}
