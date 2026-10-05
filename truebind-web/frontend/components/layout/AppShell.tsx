"use client";

import {
  Bell,
  CaretRight,
  Files,
  Gear,
  House,
  List,
  MagnifyingGlass,
  Plus,
  ShieldCheck,
  SignOut,
  Stamp,
  UserCircle,
  Users,
  WarningDiamond,
} from "@phosphor-icons/react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useMe } from "@/components/auth/AuthGate";
import {
  Avatar,
  Button,
  ButtonLink,
  CountBadge,
  Kbd,
  Logo,
  Menu,
  NotAvailable,
  Popover,
  SearchCommand,
  Tag,
  type CommandItem,
} from "@/components/ds";
import { useShell } from "@/components/layout/ShellContext";
import { api } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/auth";
import { flags, isHiddenRoute } from "@/lib/flags";
import { timeAgo } from "@/lib/formatters";
import type { Alert, Report } from "@/lib/types";
import { useUi } from "@/lib/ui";
import s from "./AppShell.module.css";

interface NavEntry {
  id: string;
  label: string;
  href: string;
  icon: React.ElementType;
  /** Other paths that light this entry up. */
  also?: string[];
  badge?: "findings";
  tag?: string;
  show?: boolean;
}

const NAV: NavEntry[] = [
  { id: "home", label: "Home", href: "/overview", icon: House, also: ["/onboarding", "/todo", "/inbox"] },
  { id: "submissions", label: "Submissions", href: "/reports", icon: Files, also: ["/upload"] },
  { id: "findings", label: "Findings", href: "/exceptions", icon: WarningDiamond, also: ["/duplicates"], badge: "findings" },
  { id: "senders", label: "Senders", href: "/senders", icon: Users, show: flags.senders },
  { id: "evidence", label: "Evidence", href: "/exports", icon: ShieldCheck, also: ["/audit", "/alerts"] },
  { id: "binders", label: "Binders", href: "/settings?tab=binders", icon: Stamp, tag: "Beta", show: flags.binders },
];

const SETTINGS_PAGES = [
  ["Settings · Organisation", "/settings"],
  ["Settings · Members", "/settings?tab=members"],
  ["Settings · Security", "/settings?tab=security"],
  ["Settings · Channels", "/settings?tab=channels"],
] as const;

function isOn(entry: NavEntry, path: string, tab: string | null): boolean {
  const base = entry.href.split("?")[0];
  if (entry.id === "binders") return path === "/settings" && tab === "binders";
  const match = (p: string) => path === p || path.startsWith(p + "/");
  return match(base) || (entry.also ?? []).some(match);
}

function crumbsFor(path: string, tab: string | null): { label: string; href?: string }[] {
  if (path === "/settings") {
    if (tab === "binders") return [{ label: "Binders" }];
    return [{ label: "Settings" }];
  }
  if (path.startsWith("/reports/")) return [{ label: "Submissions", href: "/reports" }, { label: "Report" }];
  if (path.startsWith("/upload")) return [{ label: "Submissions", href: "/reports" }, { label: "New submission" }];
  if (path.startsWith("/audit")) return [{ label: "Evidence", href: "/exports" }, { label: "Audit trail" }];
  const hit = NAV.find((n) => isOn(n, path, tab));
  return [{ label: hit?.label ?? "Home" }];
}

function useTab(): string | null {
  const [tab, setTab] = useState<string | null>(null);
  const path = usePathname();
  useEffect(() => {
    const read = () => setTab(new URLSearchParams(window.location.search).get("tab"));
    read();
    window.addEventListener("popstate", read);
    return () => window.removeEventListener("popstate", read);
  }, [path]);
  return tab;
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const tab = useTab();
  const router = useRouter();
  const me = useMe();
  const { openFindings } = useShell();
  const [searchOpen, setSearchOpen] = useState(false);
  const [reports, setReports] = useState<Report[]>([]);
  const sheet = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setSearchOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Close the mobile sheet on navigation.
  useEffect(() => {
    if (sheet.current?.open) sheet.current.close();
  }, [path]);

  useEffect(() => {
    if (!searchOpen || !me) return;
    let live = true;
    api.listReports().then((r) => live && setReports(r)).catch(() => undefined);
    return () => {
      live = false;
    };
  }, [searchOpen, me]);

  const canWrite = me?.can_write ?? false;
  const nav = NAV.filter((n) => n.show !== false);

  const commands = useMemo<CommandItem[]>(() => {
    const go = (href: string) => () => router.push(href);
    return [
      ...(canWrite ? [{ id: "new", group: "Actions", label: "New submission", run: go("/upload") }] : []),
      ...nav.map((n) => ({ id: `p-${n.id}`, group: "Pages", label: n.label, run: go(n.href) })),
      ...SETTINGS_PAGES.map(([label, href]) => ({ id: `p-${href}`, group: "Pages", label, run: go(href) })),
      ...reports.map((r) => ({
        id: `r-${r.id}`,
        group: "Submissions",
        label: r.file_name,
        hint: [r.sender, timeAgo(r.created_at)].filter(Boolean).join(" · "),
        keywords: `${r.sender ?? ""} ${r.programme ?? ""}`,
        run: go(`/reports/${r.id}`),
      })),
    ];
  }, [router, reports, canWrite, nav]);

  const signOut = async () => {
    try {
      await api.logout();
    } finally {
      // A full navigation drops every in-memory cache of the old session.
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      window.location.assign("/login");
    }
  };

  const name = me?.user.display_name || me?.user.email || "";
  const role = ROLE_LABEL[String(me?.role)] ?? "";
  const crumbs = crumbsFor(path, tab);

  const sidebar = (
    <nav className={s.sidebar} aria-label="Main">
      <Link href="/overview" className={s.org}>
        <Logo size={26} label={false} />
        <span className={s.orgText}>
          <span className={s.orgName}>{me?.tenant.name ?? "TrueBind"}</span>
          {role && <span className={s.orgRole}>{role}</span>}
        </span>
      </Link>
      <ul className={s.nav}>
        {nav.map((n) => (
          <li key={n.id}>
            <Link href={n.href} className={s.navItem} aria-current={isOn(n, path, tab) ? "page" : undefined}>
              <n.icon size={16} weight={isOn(n, path, tab) ? "fill" : "regular"} aria-hidden="true" />
              <span className={s.navLabel}>{n.label}</span>
              {n.tag && <Tag>{n.tag}</Tag>}
              {n.badge === "findings" && <CountBadge n={openFindings} label={`${openFindings} open findings`} />}
            </Link>
          </li>
        ))}
      </ul>
      <div className={s.spacer} />
      <ul className={s.nav}>
        <li>
          <Link href="/settings" className={s.navItem} aria-current={path === "/settings" && tab !== "binders" ? "page" : undefined}>
            <Gear size={16} aria-hidden="true" />
            <span className={s.navLabel}>Settings</span>
          </Link>
        </li>
      </ul>
      <div className={s.userWrap}>
        <Menu
          label="Account"
          align="start"
          side="top"
          width={232}
          items={[
            { kind: "label", label: me?.user.email ?? "" },
            { label: "Profile and settings", icon: UserCircle, href: "/settings" },
            { label: "Two-step verification", icon: ShieldCheck, href: "/settings?tab=security" },
            { kind: "separator" },
            { label: "Sign out", icon: SignOut, danger: true, onSelect: signOut },
          ]}
          trigger={({ props }) => (
            <button type="button" className={s.userBtn} aria-label={`Account: ${name}`} {...props} aria-haspopup="menu">
              <Avatar name={name || "?"} size={28} />
              <span className={s.userText}>
                <span className={s.userName}>{name}</span>
                <span className={s.userMail}>{me?.user.email}</span>
              </span>
            </button>
          )}
        />
      </div>
    </nav>
  );

  return (
    <div className={s.app}>
      <a href="#main" className="sr-only-ds" onFocus={(e) => e.currentTarget.classList.remove("sr-only-ds")} onBlur={(e) => e.currentTarget.classList.add("sr-only-ds")}>
        Skip to content
      </a>
      {sidebar}
      <dialog ref={sheet} className={s.sheet} aria-label="Navigation" onMouseDown={(e) => e.target === e.currentTarget && sheet.current?.close()}>
        {sidebar}
      </dialog>
      <div className={s.main}>
        <header className={`${s.topbar} no-print`}>
          <Button variant="ghost" size={32} iconOnly className={s.menuBtn} aria-label="Open navigation" onClick={() => sheet.current?.showModal()}>
            <List size={18} />
          </Button>
          <ol className={s.crumbs} aria-label="Breadcrumb">
            {crumbs.map((c, i) => (
              <li key={i}>
                {i > 0 && <CaretRight size={11} className={s.crumbSep} aria-hidden="true" />}
                {c.href ? <Link href={c.href}>{c.label}</Link> : <span aria-current="page">{c.label}</span>}
              </li>
            ))}
          </ol>
          <div className={s.grow} />
          <button type="button" className={s.search} onClick={() => setSearchOpen(true)} aria-label="Search (Ctrl K)">
            <MagnifyingGlass size={15} aria-hidden="true" />
            <span>Search</span>
            <Kbd>⌘K</Kbd>
          </button>
          <Button variant="ghost" size={32} iconOnly className={s.searchIcon} aria-label="Search" onClick={() => setSearchOpen(true)}>
            <MagnifyingGlass size={18} />
          </Button>
          <Notifications />
          {canWrite && (
            <ButtonLink href="/upload" variant="primary" size={32}>
              <Plus size={14} weight="bold" aria-hidden="true" />
              <span className={s.newLabel}>New submission</span>
            </ButtonLink>
          )}
        </header>
        <main id="main" tabIndex={-1} className={s.content}>
          {isHiddenRoute(path) ? <NotAvailable /> : children}
        </main>
      </div>
      <SearchCommand open={searchOpen} onClose={() => setSearchOpen(false)} items={commands} />
    </div>
  );
}

/** Bell: unread alerts grouped per submission, newest first. */
function Notifications() {
  const { unreadAlerts, refresh } = useShell();
  const { toast } = useUi();
  const [alerts, setAlerts] = useState<Alert[] | null>(null);
  const [names, setNames] = useState<Record<string, string>>({});
  const [failed, setFailed] = useState(false);

  const load = useCallback(async () => {
    setFailed(false);
    try {
      const [page, reports] = await Promise.all([api.listAlertsPage({ acknowledged: false, limit: 100 }), api.listReports()]);
      setAlerts(page.items);
      setNames(Object.fromEntries(reports.map((r) => [r.id, r.file_name])));
    } catch {
      setFailed(true);
    }
  }, []);

  const groups = useMemo(() => {
    const by = new Map<string, Alert[]>();
    for (const a of alerts ?? []) by.set(a.report_id, [...(by.get(a.report_id) ?? []), a]);
    return [...by.entries()].sort((x, y) => y[1][0].created_at.localeCompare(x[1][0].created_at));
  }, [alerts]);

  const markAll = async () => {
    const ids = (alerts ?? []).map((a) => a.id);
    try {
      await Promise.all(ids.map((id) => api.acknowledgeAlert(id)));
      setAlerts([]);
      refresh();
    } catch {
      toast("Some notifications couldn't be marked read. Try again.", "err");
      void load();
    }
  };

  return (
    <Popover
      label="Notifications"
      width={380}
      trigger={({ props }) => (
        <span className={s.bellWrap}>
          <Button
            variant="ghost"
            size={32}
            iconOnly
            aria-label={unreadAlerts > 0 ? `Notifications, ${unreadAlerts} unread` : "Notifications"}
            {...props}
            onClick={(e) => {
              props.onClick?.(e);
              void load();
            }}
          >
            <Bell size={18} />
          </Button>
          <span className={s.bellCount}><CountBadge n={unreadAlerts} strong /></span>
        </span>
      )}
    >
      {(close) => (
        <>
          <div className={s.notifHead}>
            <h2 className={s.notifTitle}>Notifications</h2>
            {groups.length > 0 && (
              <Button variant="ghost" size={28} onClick={markAll}>
                Mark all read
              </Button>
            )}
          </div>
          {failed && <p className={s.notifEmpty}>Notifications couldn&rsquo;t be loaded. Close and open the panel to try again.</p>}
          {!failed && alerts === null && <p className={s.notifEmpty} role="status">Loading notifications…</p>}
          {!failed && alerts?.length === 0 && <p className={s.notifEmpty}>Nothing new. Notifications about your submissions appear here.</p>}
          {groups.length > 0 && (
            <ul className={s.notifList}>
              {groups.map(([reportId, items]) => {
                const critical = items.filter((a) => a.severity === "CRITICAL").length;
                const summary = critical > 0 ? `${critical} critical` : `${items.length} ${items.length === 1 ? "update" : "updates"}`;
                return (
                  <li key={reportId} className={s.notifItem}>
                    <Link href={`/reports/${reportId}`} className={s.notifLink} onClick={close}>
                      <span className={s.notifFile}>{names[reportId] ?? "Submission"}</span>
                      <span className={s.notifMeta}>
                        {summary} · <time title={new Date(items[0].created_at).toLocaleString("en-GB")}>{timeAgo(items[0].created_at)}</time>
                      </span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </>
      )}
    </Popover>
  );
}
