"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  AddressBook,
  Bell,
  CaretRight,
  ChartLineUp,
  CheckSquare,
  Copy,
  FileText,
  Gear,
  Lightning,
  List,
  MagnifyingGlass,
  Moon,
  PaperPlaneTilt,
  ShieldCheck,
  SignOut,
  SquaresFour,
  Sun,
  Tray,
  UploadSimple,
  Warning,
  X,
} from "@phosphor-icons/react";
import { Mark, ThemeToggle } from "./ui";
import { useMe } from "@/components/auth/AuthGate";
import { useShell } from "@/components/layout/ShellContext";
import { api } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/auth";
import type { Alert, Report } from "@/lib/types";
import { useUi } from "@/lib/ui";
import { timeAgo } from "@/lib/formatters";

type NavItem = { id: string; label: string; icon: React.ElementType; href: string; badge?: "work" | "alerts" };

export const NAV: { label: string; items: NavItem[] }[] = [
  { label: "Operate", items: [
    { id: "overview", label: "Overview", icon: SquaresFour, href: "/overview" },
    { id: "inbox", label: "Inbox", icon: Tray, href: "/inbox" },
    { id: "upload", label: "Intake", icon: UploadSimple, href: "/upload" },
    { id: "todo", label: "Work queue", icon: CheckSquare, href: "/todo", badge: "work" },
  ] },
  { label: "Investigate", items: [
    { id: "reports", label: "Reports", icon: FileText, href: "/reports" },
    { id: "exceptions", label: "Exceptions", icon: Warning, href: "/exceptions" },
    { id: "duplicates", label: "Duplicates", icon: Copy, href: "/duplicates" },
    { id: "senders", label: "Senders", icon: AddressBook, href: "/senders" },
    { id: "scorecard", label: "Scorecard", icon: ChartLineUp, href: "/scorecard" },
  ] },
  { label: "Deliver", items: [
    { id: "exports", label: "Exports", icon: PaperPlaneTilt, href: "/exports" },
    { id: "automations", label: "Automations", icon: Lightning, href: "/automations" },
  ] },
  { label: "Govern", items: [
    { id: "alerts", label: "Alerts", icon: Bell, href: "/alerts", badge: "alerts" },
    { id: "audit", label: "Audit trail", icon: ShieldCheck, href: "/audit" },
  ] },
];

function crumbFor(path: string): [string, string] {
  if (path.startsWith("/reports/")) return ["Investigate", "Health Check"];
  if (path.startsWith("/settings")) return ["Workspace", "Settings"];
  for (const s of NAV) for (const it of s.items) if (path === it.href || path.startsWith(it.href + "/")) return [s.label, it.label];
  return ["Operate", "Overview"];
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const me = useMe();
  const { system, unreadAlerts, workItems, refresh } = useShell();
  const { toast, theme, toggleTheme } = useUi();
  const [mobileNav, setMobileNav] = useState(false);
  const [search, setSearch] = useState(false);
  const [bell, setBell] = useState(false);
  const [userMenu, setUserMenu] = useState(false);
  const [a, b] = crumbFor(path);

  // Close popovers on navigation (state adjusted during render, not in an effect).
  const [lastPath, setLastPath] = useState(path);
  if (lastPath !== path) {
    setLastPath(path);
    setMobileNav(false);
    setBell(false);
    setUserMenu(false);
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setSearch(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const online = system?.worker_available;
  const signOut = async () => {
    try {
      await api.logout();
    } finally {
      // Full navigation drops every in-memory cache of the old session.
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      window.location.assign("/login");
    }
  };
  const name = me?.user.display_name || me?.user.email || "";
  const initial = name.trim()[0]?.toUpperCase() ?? "?";
  const roleLabel = ROLE_LABEL[String(me?.role)] ?? String(me?.role ?? "");

  const sidebar = (
    // The sidebar stays dark in both themes, as in the design; scoping the dark tokens here does that.
    <aside
      data-theme="dark"
      className="flex h-full flex-col gap-[18px] overflow-y-auto px-3 py-[18px]"
      style={{ background: "var(--chrome)", color: "var(--chromeText)", boxShadow: "1px 0 0 var(--chromeLine)", scrollbarWidth: "thin", scrollbarColor: "rgba(233,233,237,.12) transparent" }}
    >
      <Link href="/overview" className="flex items-center gap-[9px] px-2 py-0.5 text-[15px] font-semibold" style={{ color: "var(--chromeStrong)" }} title="Overview">
        <Mark size={26} radius={7} />
        TrueBind
      </Link>
      <button
        type="button"
        onClick={() => setSearch(true)}
        className="flex cursor-pointer items-center gap-2 overflow-hidden whitespace-nowrap rounded-md px-2.5 py-2 text-left text-[12.5px] transition-colors hover:bg-[rgba(233,233,237,.06)]"
        style={{ background: "rgba(233,233,237,.04)", boxShadow: "inset 0 0 0 1px var(--chromeLine)", color: "var(--chromeFaint)" }}
      >
        <MagnifyingGlass />
        <span className="min-w-0 flex-1 truncate">Search or jump to…</span>
        <span className="rounded px-[5px] py-px text-[10.5px]" style={{ boxShadow: "inset 0 0 0 1px var(--chromeLine)" }}>⌘K</span>
      </button>
      {NAV.map((sec) => (
        <div key={sec.label} className="flex flex-col gap-px">
          <span className="px-2.5 pb-1.5 text-[10.5px] font-medium uppercase tracking-[.1em]" style={{ color: "var(--chromeFaint)" }}>{sec.label}</span>
          {sec.items.map((it) => {
            const on = path === it.href || path.startsWith(it.href + "/");
            const badge = it.badge === "work" ? workItems : it.badge === "alerts" ? unreadAlerts : 0;
            return (
              <Link
                key={it.id}
                href={it.href}
                aria-current={on ? "page" : undefined}
                className="flex items-center gap-2.5 rounded-[7px] px-2.5 py-[7px] text-[13.5px] transition-colors hover:bg-[rgba(233,233,237,.05)]"
                style={{ background: on ? "rgba(52,211,153,.14)" : undefined, color: on ? "var(--chromeStrong)" : "var(--chromeMuted)", boxShadow: on ? "inset 2px 0 0 var(--accent)" : "none" }}
              >
                <it.icon size={16} />
                <span className="flex-1">{it.label}</span>
                {badge > 0 && <span className="tnum text-[11px] font-medium" style={{ color: "var(--err)" }}>{badge}</span>}
              </Link>
            );
          })}
        </div>
      ))}
      <div className="mt-auto flex flex-col gap-px">
        <Link
          href="/settings"
          className="flex items-center gap-2.5 rounded-[7px] px-2.5 py-[7px] text-[13.5px] transition-colors hover:bg-[rgba(233,233,237,.05)]"
          style={{ background: path.startsWith("/settings") ? "rgba(52,211,153,.14)" : undefined, color: path.startsWith("/settings") ? "var(--chromeStrong)" : "var(--chromeMuted)", boxShadow: path.startsWith("/settings") ? "inset 2px 0 0 var(--accent)" : "none" }}
        >
          <Gear size={16} />
          Settings
        </Link>
      </div>
      <button
        type="button"
        onClick={() => {
          refresh();
          toast(
            !system
              ? "Checking the processing engine…"
              : online
                ? `Engine online · ${system.workers_alive} worker${system.workers_alive === 1 ? "" : "s"}${system.worker_modes?.length ? ` (${system.worker_modes.join(", ")})` : ""} · ${system.queued} queued · ${system.running} running`
                : "No processing worker has checked in recently. Uploads wait safely until one is running.",
            online ? "ok" : "warn",
          );
        }}
        className="flex cursor-pointer items-center gap-2 px-2.5 pt-2.5 text-left text-[12px]"
        style={{ color: !system ? "var(--chromeFaint)" : online ? "var(--ok)" : "var(--warn)", boxShadow: "0 -1px 0 var(--chromeLine)" }}
      >
        <span className="h-[7px] w-[7px] rounded-full" style={{ background: "currentColor" }} />
        {!system ? "Checking engine…" : online ? "Engine online" : "Engine offline"}
      </button>
    </aside>
  );

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] min-h-screen lg:grid-cols-[232px_minmax(0,1fr)]" style={{ background: "var(--bg)", color: "var(--text)" }}>
      <a href="#main" className="sr-only z-[70] rounded-md text-[13px] focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:px-3 focus:py-2" style={{ background: "var(--surface)", color: "var(--text)", boxShadow: "0 0 0 2px var(--accent)" }}>Skip to content</a>
      <div className="no-print sticky top-0 hidden h-screen lg:block">{sidebar}</div>
      {mobileNav && (
        <div className="anim-fade fixed inset-0 z-40 lg:hidden" style={{ background: "rgba(0,0,0,.45)" }} onClick={() => setMobileNav(false)}>
          <div className="anim-rise h-full w-[260px]" onClick={(e) => e.stopPropagation()}>{sidebar}</div>
        </div>
      )}

      <main className="flex min-w-0 flex-col overflow-x-clip">
        <header
          className="no-print tb-safe-top sticky top-0 z-30 flex min-h-14 items-center gap-1.5 px-3 sm:gap-3 sm:px-5"
          style={{ background: "color-mix(in srgb, var(--bg) 82%, transparent)", boxShadow: "0 1px 0 var(--line)" }}
        >
          <button type="button" className="tb-btn tb-btn-ghost !p-2 lg:hidden" aria-label="Open navigation" onClick={() => setMobileNav(true)}>
            <List size={18} />
          </button>
          <div className="flex min-w-0 flex-[0_1_auto] items-center gap-2 overflow-hidden whitespace-nowrap text-[13.5px]">
            <span className="hidden min-w-0 truncate sm:inline" style={{ color: "var(--muted)" }}>{a}</span>
            <CaretRight size={11} className="hidden flex-none sm:block" style={{ color: "var(--faint)" }} />
            <span className="min-w-0 truncate font-medium">{b}</span>
          </div>
          <span
            className="hidden flex-none items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-[12px] md:flex"
            style={{ background: !system ? "var(--line)" : online ? "var(--okT)" : "var(--warnT)", color: !system ? "var(--muted)" : online ? "var(--ok)" : "var(--warn)" }}
            title={system && !online ? "No processing worker has checked in recently" : undefined}
          >
            <span className="h-1.5 w-1.5 rounded-full" style={{ background: "currentColor" }} />
            {!system ? "Checking processing…" : online ? "Processing online" : "Processing unavailable"}
          </span>
          <div className="min-w-0 flex-1" />
          <button
            type="button"
            onClick={() => setSearch(true)}
            className="hidden min-w-[140px] flex-[0_1000_220px] cursor-pointer items-center gap-2 overflow-hidden whitespace-nowrap rounded-md px-2.5 py-[7px] text-left text-[13px] lg:flex"
            style={{ boxShadow: "inset 0 0 0 1px var(--line2)", color: "var(--faint)" }}
          >
            <MagnifyingGlass />
            <span className="flex-1 truncate">Search</span>
            <span className="text-[10.5px]">⌘K</span>
          </button>
          <button type="button" className="tb-btn tb-btn-ghost !p-2 lg:hidden" aria-label="Search" onClick={() => setSearch(true)}>
            <MagnifyingGlass size={17} />
          </button>
          <Link href="/upload" className="tb-btn tb-btn-primary flex-none !px-[13px] !py-2">
            <UploadSimple />
            <span className="hidden sm:inline">New intake</span>
          </Link>
          <span className="hidden sm:contents"><ThemeToggle /></span>
          <div className="relative flex-none">
            <button type="button" aria-label={`Notifications, ${unreadAlerts} unread`} onClick={() => setBell((v) => !v)} className="relative flex h-[34px] w-[34px] cursor-pointer items-center justify-center rounded-md text-[17px] hover:bg-[var(--accentTint)]" style={{ color: "var(--muted)" }}>
              <Bell />
              {unreadAlerts > 0 && (
                <span className="tnum absolute right-0.5 top-[3px] rounded-md px-1 text-[9.5px] font-semibold text-white" style={{ background: "var(--badge)" }}>
                  {unreadAlerts > 99 ? "99+" : unreadAlerts}
                </span>
              )}
            </button>
            {bell && <BellMenu onClose={() => setBell(false)} onChange={refresh} />}
          </div>
          <div className="relative flex-none">
            <button type="button" onClick={() => setUserMenu((v) => !v)} className="flex cursor-pointer items-center gap-[9px] rounded-md py-1 pl-1 pr-1 sm:pl-3 sm:[box-shadow:-1px_0_0_var(--line)]" aria-label="Account menu">
              <span className="grid h-[30px] w-[30px] place-items-center rounded-full text-[12px] font-semibold" style={{ background: "var(--accentTint)", color: "var(--accentText)" }}>{initial}</span>
              <span className="hidden max-w-[160px] flex-col text-left text-[12.5px] leading-[1.25] xl:flex">
                <span className="truncate font-medium">{name}</span>
                <span className="truncate text-[11.5px]" style={{ color: "var(--faint)" }}>{me?.tenant.name} · {roleLabel.toLowerCase()}</span>
              </span>
            </button>
            {userMenu && (
              <Popover onClose={() => setUserMenu(false)} width={240}>
                <div className="px-3 py-2.5 text-[12.5px]" style={{ boxShadow: "0 1px 0 var(--line)" }}>
                  <div className="truncate font-medium">{name}</div>
                  <div className="truncate" style={{ color: "var(--faint)" }}>{me?.user.email}</div>
                  <div className="truncate" style={{ color: "var(--faint)" }}>{me?.tenant.name} · {roleLabel}</div>
                </div>
                <MenuLink href="/settings" icon={Gear}>Settings</MenuLink>
                <button type="button" className="flex w-full cursor-pointer items-center gap-2.5 px-3 py-2.5 text-left text-[13px] hover:bg-[var(--accentTint)] sm:hidden" onClick={toggleTheme}>
                  {theme === "dark" ? <Sun size={15} style={{ color: "var(--muted)" }} /> : <Moon size={15} style={{ color: "var(--muted)" }} />}
                  {theme === "dark" ? "Light theme" : "Dark theme"}
                </button>
                <MenuLink href="/settings?tab=security" icon={ShieldCheck}>Two-step verification</MenuLink>
                <MenuLink href="/settings?tab=members" icon={CheckSquare}>Members & roles</MenuLink>
                <button type="button" className="flex w-full cursor-pointer items-center gap-2.5 px-3 py-2 text-left text-[13px] hover:bg-[var(--accentTint)]" style={{ color: "var(--err)", boxShadow: "0 -1px 0 var(--line)" }} onClick={signOut}>
                  <SignOut size={15} />
                  Sign out
                </button>
              </Popover>
            )}
          </div>
          <button type="button" aria-label="Sign out" title="Sign out" className="hidden h-[34px] w-[34px] flex-none cursor-pointer items-center justify-center rounded-md text-[17px] hover:bg-[var(--accentTint)] sm:flex" style={{ color: "var(--muted)" }} onClick={signOut}>
            <SignOut />
          </button>
        </header>
        <div id="main" tabIndex={-1} className="min-w-0 flex-1 outline-none">{children}</div>
      </main>

      <SearchPalette open={search} onClose={() => setSearch(false)} onNavigate={(h) => router.push(h)} />
    </div>
  );
}

export function Popover({ children, onClose, width = 360, align = "right" }: { children: React.ReactNode; onClose: () => void; width?: number; align?: "right" | "left" }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.parentElement?.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    const t = setTimeout(() => document.addEventListener("mousedown", onDown));
    window.addEventListener("keydown", onKey);
    return () => {
      clearTimeout(t);
      document.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);
  return (
    <div
      ref={ref}
      className="tb-popover anim-pop absolute top-[calc(100%+8px)] z-50 overflow-hidden rounded-md"
      style={{ [align]: 0, width, maxWidth: "calc(100vw - 24px)", background: "var(--surface)", boxShadow: "0 0 0 1px var(--line2)" }}
    >
      {children}
    </div>
  );
}

function MenuLink({ href, icon: Icon, children }: { href: string; icon: React.ElementType; children: React.ReactNode }) {
  return (
    <Link href={href} className="flex items-center gap-2.5 px-3 py-2 text-[13px] hover:bg-[var(--accentTint)]">
      <Icon size={15} style={{ color: "var(--muted)" }} />
      {children}
    </Link>
  );
}

const SEV_C: Record<string, string> = { CRITICAL: "var(--err)", HIGH: "var(--warn)", MEDIUM: "var(--med)", INFO: "var(--muted)" };

function BellMenu({ onClose, onChange }: { onClose: () => void; onChange: () => void }) {
  const { toast } = useUi();
  const [alerts, setAlerts] = useState<Alert[] | null>(null);
  const [err, setErr] = useState(false);
  useEffect(() => {
    let alive = true;
    api.listAlertsPage({ acknowledged: false, limit: 6 })
      .then((p) => alive && setAlerts(p.items))
      .catch(() => alive && setErr(true));
    return () => {
      alive = false;
    };
  }, []);
  const ack = async (id: string) => {
    try {
      await api.acknowledgeAlert(id);
      setAlerts((l) => l?.filter((x) => x.id !== id) ?? null);
      onChange();
    } catch {
      toast("That alert could not be marked read. Try again.", "err");
    }
  };
  return (
    <Popover onClose={onClose} width={380}>
      <div className="flex items-center justify-between px-4 py-3" style={{ boxShadow: "0 1px 0 var(--line)" }}>
        <span className="text-[14px] font-medium">Unread alerts</span>
        <Link href="/alerts" className="text-[12.5px]" style={{ color: "var(--accentText)" }}>All alerts</Link>
      </div>
      <div className="max-h-[380px] overflow-y-auto">
        {err && <div className="px-4 py-6 text-center text-[13px]" style={{ color: "var(--err)" }}>Alerts could not be loaded.</div>}
        {!err && !alerts && <div className="px-4 py-6 text-center text-[13px]" style={{ color: "var(--faint)" }}>Loading…</div>}
        {alerts?.length === 0 && <div className="px-4 py-6 text-center text-[13px]" style={{ color: "var(--faint)" }}>You are up to date.</div>}
        {alerts?.map((al) => (
          <div key={al.id} className="grid grid-cols-[10px_1fr_auto] items-start gap-3 px-4 py-3" style={{ boxShadow: "0 1px 0 var(--line)" }}>
            <span className="mt-1.5 h-2 w-2 rounded-full" style={{ background: SEV_C[al.severity] ?? "var(--muted)" }} />
            <Link href={`/reports/${al.report_id}`} onClick={() => void ack(al.id)} className="flex min-w-0 flex-col gap-0.5">
              <span className="text-[13px] font-medium leading-[1.35]">{al.message}</span>
              <span className="text-[11.5px]" style={{ color: "var(--faint)" }}>{timeAgo(al.created_at)}</span>
            </Link>
            <button type="button" className="cursor-pointer text-[12px]" style={{ color: "var(--accentText)" }} onClick={() => void ack(al.id)}>
              Mark read
            </button>
          </div>
        ))}
      </div>
    </Popover>
  );
}

const PAGES = [
  ...NAV.flatMap((s) => s.items.map((i) => ({ label: i.label, href: i.href, kind: "Page" }))),
  { label: "Settings · organisation, members, security", href: "/settings", kind: "Page" },
  { label: "Settings · channels (e-mail intake, webhooks, SFTP)", href: "/settings?tab=channels", kind: "Page" },
  { label: "Settings · binders", href: "/settings?tab=binders", kind: "Page" },
  { label: "Settings · sanctions lists", href: "/settings?tab=sanctions", kind: "Page" },
  { label: "Upload a bordereau", href: "/upload", kind: "Action" },
];

function SearchPalette({ open, onClose, onNavigate }: { open: boolean; onClose: () => void; onNavigate: (href: string) => void }) {
  const [q, setQ] = useState("");
  const [i, setI] = useState(0);
  const [reports, setReports] = useState<Report[]>([]);
  useEffect(() => {
    if (!open) return;
    let alive = true;
    api.listReports().then((r) => alive && setReports(r)).catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [open]);
  const results = useMemo(() => {
    const all = [...PAGES, ...reports.map((r) => ({ label: `${r.file_name}${r.sender ? ` · ${r.sender}` : ""}`, href: `/reports/${r.id}`, kind: "Report" }))];
    const t = q.trim().toLowerCase();
    return (t ? all.filter((x) => x.label.toLowerCase().includes(t) || x.kind.toLowerCase().includes(t)) : all).slice(0, 12);
  }, [q, reports]);
  const [lastOpen, setLastOpen] = useState(open);
  if (lastOpen !== open) {
    setLastOpen(open);
    if (open) {
      setQ("");
      setI(0);
    }
  }
  if (!open) return null;
  const go = (href: string) => {
    onClose();
    onNavigate(href);
  };
  return (
    <div className="anim-fade fixed inset-0 z-[65] flex justify-center px-4 pt-[12vh]" style={{ background: "color-mix(in srgb, #0b0c14 55%, transparent)" }} onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="anim-pop flex h-fit max-h-[70vh] w-full max-w-[600px] flex-col overflow-hidden rounded-md" style={{ background: "var(--surface)", boxShadow: "0 0 0 1px var(--line2)" }} role="dialog" aria-label="Search">
        <div className="flex items-center gap-3 px-4" style={{ boxShadow: "0 1px 0 var(--line)" }}>
          <MagnifyingGlass size={18} style={{ color: "var(--faint)" }} />
          <input
            autoFocus
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setI(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "Escape") onClose();
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setI((x) => Math.min(results.length - 1, x + 1));
              }
              if (e.key === "ArrowUp") {
                e.preventDefault();
                setI((x) => Math.max(0, x - 1));
              }
              if (e.key === "Enter" && results[i]) go(results[i].href);
            }}
            placeholder="Search pages, reports and actions…"
            className="h-14 flex-1 bg-transparent text-[15px] outline-none"
            style={{ color: "var(--text)" }}
            aria-label="Search"
          />
          <button type="button" onClick={onClose} className="tb-btn tb-btn-ghost !p-1.5" aria-label="Close search">
            <X size={15} />
          </button>
        </div>
        <div className="overflow-y-auto py-1.5">
          {results.length === 0 && <div className="px-4 py-8 text-center text-[13.5px]" style={{ color: "var(--faint)" }}>Nothing matches “{q}”.</div>}
          {results.map((r, j) => (
            <button key={r.href + r.label} type="button" onMouseEnter={() => setI(j)} onClick={() => go(r.href)} className="flex w-full cursor-pointer items-center gap-3 px-4 py-2.5 text-left text-[13.5px]" style={{ background: j === i ? "var(--accentTint)" : "transparent" }}>
              <span className="w-[56px] flex-none text-[11px] uppercase tracking-[.06em]" style={{ color: "var(--faint)" }}>{r.kind}</span>
              <span className="truncate">{r.label}</span>
            </button>
          ))}
        </div>
        <div className="flex gap-4 px-4 py-2 text-[11.5px]" style={{ color: "var(--faint)", boxShadow: "0 -1px 0 var(--line)" }}>
          <span>↑↓ to move</span>
          <span>↵ to open</span>
          <span>Esc to close</span>
        </div>
      </div>
    </div>
  );
}
