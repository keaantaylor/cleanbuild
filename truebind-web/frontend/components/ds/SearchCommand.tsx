"use client";

import { MagnifyingGlass } from "@phosphor-icons/react";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Kbd } from "./Primitives";
import s from "./SearchCommand.module.css";

export interface CommandItem {
  id: string;
  group: string;
  label: string;
  hint?: string;
  keywords?: string;
  run: () => void;
}

/** ⌘K palette: a combobox over pages, submissions and actions.
 * ↑/↓ move, Enter opens, Esc closes and returns focus. */
export function SearchCommand({ open, onClose, items, placeholder = "Search submissions and pages" }: { open: boolean; onClose: () => void; items: CommandItem[]; placeholder?: string }) {
  const ref = useRef<HTMLDialogElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const id = useId();

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) {
      opener.current = document.activeElement as HTMLElement | null;
      d.showModal();
    } else if (!open && d.open) {
      d.close();
      opener.current?.focus?.();
    }
  }, [open]);

  const results = useMemo(() => {
    const t = q.trim().toLowerCase();
    const hits = t ? items.filter((i) => `${i.label} ${i.keywords ?? ""} ${i.group}`.toLowerCase().includes(t)) : items;
    return hits.slice(0, 30);
  }, [q, items]);

  const choose = (item: CommandItem | undefined) => {
    if (!item) return;
    onClose();
    item.run();
  };

  return (
    <dialog
      ref={ref}
      className={s.dialog}
      aria-label="Search"
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      {open && (
        <>
          <div className={s.inputRow}>
            <MagnifyingGlass size={18} aria-hidden="true" />
            <input
              autoFocus
              className={s.input}
              value={q}
              placeholder={placeholder}
              role="combobox"
              aria-expanded="true"
              aria-controls={`${id}-list`}
              aria-activedescendant={results[active] ? `${id}-${results[active].id}` : undefined}
              aria-label="Search"
              onChange={(e) => {
                setQ(e.target.value);
                setActive(0);
              }}
              onKeyDown={(e) => {
                if (e.key === "ArrowDown") setActive((a) => Math.min(results.length - 1, a + 1));
                else if (e.key === "ArrowUp") setActive((a) => Math.max(0, a - 1));
                else if (e.key === "Enter") choose(results[active]);
                else return;
                e.preventDefault();
              }}
            />
            <Kbd>Esc</Kbd>
          </div>
          {results.length === 0 ? (
            <p className={s.empty}>Nothing matches &ldquo;{q}&rdquo;. Try a file name, sender or page.</p>
          ) : (
            <ul id={`${id}-list`} role="listbox" aria-label="Results" className={s.list}>
              {results.map((r, i) => {
                const header = i === 0 || results[i - 1].group !== r.group ? r.group : null;
                return (
                  <li key={r.id} role="presentation">
                    {header && <div className={s.group} role="presentation">{header}</div>}
                    <div
                      id={`${id}-${r.id}`}
                      role="option"
                      aria-selected={i === active}
                      className={s.option}
                      onMouseMove={() => setActive(i)}
                      onClick={() => choose(r)}
                    >
                      <span className={s.optLabel}>{r.label}</span>
                      {r.hint && <span className={s.optHint}>{r.hint}</span>}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
          <div className={s.foot} aria-hidden="true">
            <span><Kbd>↑</Kbd><Kbd>↓</Kbd> move</span>
            <span><Kbd>↵</Kbd> open</span>
          </div>
        </>
      )}
    </dialog>
  );
}
