"use client";

import { Suspense } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMe } from "@/components/auth/AuthGate";
import { PageHeader, ds } from "@/components/ds";
import { Tabs } from "@/components/ui/Tabs";
import { PageSkeleton } from "@/components/layout/ShellSkeleton";
import { MembersSettings } from "@/components/settings/MembersSettings";
import { OrganisationSettings } from "@/components/settings/OrganisationSettings";
import { SecuritySettings } from "@/components/settings/SecuritySettings";
import { SsoSettings } from "@/components/settings/SsoSettings";
import { hasPermission } from "@/lib/auth";

function SettingsInner() {
  const me = useMe();
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  if (!me) return <PageSkeleton label="Loading settings" />;
  const can = (p: string) => hasPermission(me.permissions, p);
  const tabs = [
    ...(can("org:read") ? [{ value: "organisation", label: "Organisation" }] : []),
    ...(can("member:read") ? [{ value: "members", label: "Members" }] : []),
    { value: "security", label: "Security" },
    ...(can("org:read") && me.role !== "SENDER" ? [{ value: "sso", label: "Single sign-on" }] : []),
  ];
  const requested = params.get("tab");
  const active = tabs.some((t) => t.value === requested) ? requested! : me.mfa?.setup_required ? "security" : tabs[0].value;
  const select = (v: string) => router.replace(`${pathname}?tab=${v}`);
  return (
    <>
      <PageHeader eyebrow="Govern" title="Settings" description={`${me.tenant.name} · signed in as ${me.user.email}`} />
      <div className={ds.stack}>
        <Tabs options={tabs} active={active} onChange={select} />
        {active === "organisation" && <OrganisationSettings canManage={can("org:manage")} />}
        {active === "members" && <MembersSettings canManage={can("member:manage")} myRole={me.role} myUserId={me.user.id} />}
        {active === "security" && <SecuritySettings required={params.get("required") === "1" || Boolean(me.mfa?.setup_required)} />}
        {active === "sso" && <SsoSettings canManage={can("org:manage")} />}
      </div>
    </>
  );
}

export default function SettingsPage() {
  return <Suspense fallback={<PageSkeleton label="Loading settings" />}><SettingsInner /></Suspense>;
}
