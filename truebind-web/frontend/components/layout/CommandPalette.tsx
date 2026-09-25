"use client";

/* ⌘K / Ctrl+K command palette: jump to any page, any received file, or a
 * common action. Files come from the tenant's real report list, fetched
 * when the palette opens (not polled). */

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Icon, type IconName } from "@/components/ds/Icon";
import { statusMeta } from "@/components/ds";
import { api } from "@/lib/api";
import type { Report } from "@/lib/types";
import { NAV_GROUPS } from "./nav";
import s from "./CommandPalette.module.css";

type Cmd = { id: string; group: string; label: string; hint?: string; icon: IconName; href: string };

const ACTIONS: Cmd[] = [
  { id: "a-upload", group: "Actions", label: "Upload a bordereau", hint: "New intake", icon: "upload", href: "/upload" },
  { id: "a-exceptions", group: "Actions", label: "Review open exceptions", icon: "exceptions", href: "/exceptions" },
  { id: "a-queue", group: "Actions", label: "Open the work queue", icon: "todo", href: "/todo" },
  { id: "a-audit", group: "Actions", label: "Verify the audit trail", icon: "audit", href: "/audit" },
];

function reportHref(r: Report) {
  return ["COMPLETE", "FAILED", "CANCELLED", "EXPIRED"].includes(r.status) ? `/reports/${r.id}` : `/upload?reportId=${r.id}`;
}

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const [reports, setReports] = useState<Report[] | null>(null);
  const router = useRouter();
  const dialog = useRef<HTMLDialogElement>(null);
  const input = useRef<HTMLInputElement>(null);

  const show = useCallback(() => {
    setQ(""); setActive(0); setOpen(true);
    api.listReports().then(setReports).catch(() => setReports([]));
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); show(); }
    };
    const onOpen = () => show();
    window.addEventListener("keydown", onKey);
    window.addEventListener("tb:command", onOpen);
    return () => { window.removeEventListener("keydown", onKey); window.removeEventListener("tb:command", onOpen); };
  }, [show]);

  useEffect(() => {
    const d = dialog.current;
    if (!d) return;
    if (open && !d.open) { d.showModal(); setTimeout(() => input.current?.focus(), 0); }
    if (!open && d.open) d.close();
  }, [open]);

  const all = useMemo<Cmd[]>(() => {
    const pages = NAV_GROUPS.flatMap((g) => g.items.map((i) => ({ id: `p-${i.href}`, group: "Go to", label: i.label, icon: i.icon, href: i.href })));
    const files = (reports ?? []).slice(0, 60).map((r) => ({
      id: `r-${r.id}`, group: "Files", label: r.file_name, hint: statusMeta(r.status).label, icon: "file" as IconName, href: reportHref(r),
    }));
    return [...ACTIONS, ...pages, ...files];
  }, [reports]);

  const results = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return all.filter((c) => c.group !== "Files").concat(all.filter((c) => c.group === "Files").slice(0, 6));
    return all.filter((c) => `${c.label} ${c.hint ?? ""} ${c.group}`.toLowerCase().includes(needle)).slice(0, 40);
  }, [all, q]);

  const go = (c: Cmd | undefined) => { if (!c) return; setOpen(false); router.push(c.href); };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(results.length - 1, a + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(0, a - 1)); }
    else if (e.key === "Enter") { e.preventDefault(); go(results[active]); }
  };

  let lastGroup = "";
  return (
    <dialog ref={dialog} className={s.palette} aria-label="Command palette"
            onClose={() => setOpen(false)} onClick={(e) => { if (e.target === e.currentTarget) setOpen(false); }}>
      {open && (
        <div className={s.inner} onKeyDown={onKeyDown}>
          <div className={s.searchRow}>
            <Icon name="search" size={18} />
            <input ref={input} className={s.input} placeholder="Search pages, files and actions…" value={q}
                   onChange={(e) => { setQ(e.target.value); setActive(0); }} role="combobox" aria-expanded="true"
                   aria-controls="cmd-list" aria-activedescendant={results[active] ? `cmd-${results[active].id}` : undefined} />
            <kbd className={s.kbd}>Esc</kbd>
          </div>
          <ul id="cmd-list" role="listbox" className={s.list} aria-label="Results">
            {results.length === 0 && <li className={s.empty}>{reports === null ? "Loading files…" : `Nothing matches “${q}”.`}</li>}
            {results.map((c, i) => {
              const header = c.group !== lastGroup ? c.group : null;
              lastGroup = c.group;
              return (
                <li key={c.id} role="presentation">
                  {header && <p className={s.group}>{header}</p>}
                  <button type="button" id={`cmd-${c.id}`} role="option" aria-selected={i === active}
                          className={`${s.item} ${i === active ? s.itemOn : ""}`}
                          onMouseMove={() => setActive(i)} onClick={() => go(c)}>
                    <span className={s.itemIcon}><Icon name={c.icon} size={15} /></span>
                    <span className={s.itemLabel}>{c.label}</span>
                    {c.hint && <span className={s.itemHint}>{c.hint}</span>}
                    <Icon name="arrowRight" size={14} className={s.itemGo} />
                  </button>
                </li>
              );
            })}
          </ul>
          <div className={s.footer}><span><kbd className={s.kbd}>↑</kbd><kbd className={s.kbd}>↓</kbd> move</span>
            <span><kbd className={s.kbd}>↵</kbd> open</span></div>
        </div>
      )}
    </dialog>
  );
}
