import type { IconName } from "@/components/ds/Icon";

export type NavItem = { href: string; label: string; icon: IconName; badge?: "work" | "alerts" };

/** The product's information architecture, shared by the rail and the
 * command palette so the two can never disagree. */
export const NAV_GROUPS: { label: string; items: NavItem[] }[] = [
  { label: "Operate", items: [
    { href: "/overview", label: "Overview", icon: "overview" },
    { href: "/inbox", label: "Inbox", icon: "inbox" },
    { href: "/upload", label: "Intake", icon: "upload" },
    { href: "/todo", label: "Work queue", icon: "todo", badge: "work" },
  ] },
  { label: "Investigate", items: [
    { href: "/reports", label: "Reports", icon: "reports" },
    { href: "/exceptions", label: "Exceptions", icon: "exceptions" },
    { href: "/duplicates", label: "Duplicates", icon: "duplicates" },
  ] },
  { label: "Deliver", items: [
    { href: "/exports", label: "Exports", icon: "exports" },
    { href: "/automations", label: "Automations", icon: "automations" },
  ] },
  { label: "Govern", items: [
    { href: "/alerts", label: "Alerts", icon: "bell", badge: "alerts" },
    { href: "/audit", label: "Audit trail", icon: "audit" },
  ] },
];
