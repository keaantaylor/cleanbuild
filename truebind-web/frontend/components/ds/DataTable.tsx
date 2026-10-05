"use client";

import { CaretUpDown, SortAscending, SortDescending } from "@phosphor-icons/react";
import { useMemo, useRef, useState } from "react";
import { Skeleton } from "./Primitives";
import s from "./DataTable.module.css";

export type ColumnType = "text" | "numeric" | "code" | "twoLine" | "status";

export interface Column<T> {
  key: string;
  header: string;
  type?: ColumnType;
  render: (row: T) => React.ReactNode;
  /** Present → the header becomes a sort button. */
  sortValue?: (row: T) => string | number | null | undefined;
  width?: number | string;
  /** One of the (up to 3) key columns kept on the phone card. */
  key3?: boolean;
}

type Sort = { key: string; dir: "asc" | "desc" } | null;

/** Dense data table: sticky header, sortable columns, row selection,
 * ↑/↓ to move between rows, Enter to open, Space to select. On phones each
 * row becomes a card showing its key columns, with the rest behind Details. */
export function DataTable<T>({
  columns,
  rows,
  rowId,
  caption,
  onOpen,
  rowLabel,
  selectable = false,
  selected,
  onSelectedChange,
  loading = false,
  skeletonRows = 6,
  empty,
  initialSort = null,
  stickyFirst = true,
}: {
  columns: Column<T>[];
  rows: T[];
  rowId: (row: T) => string;
  caption: string;
  onOpen?: (row: T) => void;
  rowLabel?: (row: T) => string;
  selectable?: boolean;
  selected?: Set<string>;
  onSelectedChange?: (next: Set<string>) => void;
  loading?: boolean;
  skeletonRows?: number;
  empty?: React.ReactNode;
  initialSort?: Sort;
  stickyFirst?: boolean;
}) {
  const [sort, setSort] = useState<Sort>(initialSort);
  const [focusIdx, setFocusIdx] = useState(0);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const body = useRef<HTMLTableSectionElement>(null);

  const sorted = useMemo(() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.key === sort.key);
    if (!col?.sortValue) return rows;
    const v = col.sortValue;
    const dir = sort.dir === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => {
      const x = v(a);
      const y = v(b);
      if (x == null && y == null) return 0;
      if (x == null) return 1;
      if (y == null) return -1;
      return (typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y), "en-GB", { numeric: true })) * dir;
    });
  }, [rows, sort, columns]);

  const sel = selected ?? new Set<string>();
  const toggle = (id: string) => {
    const next = new Set(sel);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onSelectedChange?.(next);
  };
  const allIds = sorted.map(rowId);
  const allOn = allIds.length > 0 && allIds.every((id) => sel.has(id));
  const someOn = !allOn && allIds.some((id) => sel.has(id));
  const keyed = columns.filter((c) => c.key3).map((c) => c.key);
  const keyCols = new Set(keyed.length ? keyed : columns.slice(0, 3).map((c) => c.key));
  const cellClass = (t?: ColumnType) => [s.td, t === "numeric" && s.numeric, t === "code" && s.code].filter(Boolean).join(" ");
  const span = columns.length + (selectable ? 1 : 0) + 1;

  const focusRow = (i: number) => {
    const n = Math.max(0, Math.min(sorted.length - 1, i));
    setFocusIdx(n);
    body.current?.querySelectorAll<HTMLTableRowElement>("tr[data-row]")[n]?.focus();
  };

  return (
    <div className={s.scroller}>
      <table className={`${s.table} ${stickyFirst ? s.stickyFirst : ""}`} aria-busy={loading || undefined}>
        <caption className={s.caption}>{caption}</caption>
        <thead>
          <tr>
            {selectable && (
              <th className={`${s.th} ${s.check}`} scope="col">
                <input
                  type="checkbox"
                  aria-label="Select all rows"
                  checked={allOn}
                  ref={(el) => {
                    if (el) el.indeterminate = someOn;
                  }}
                  onChange={() => onSelectedChange?.(allOn ? new Set() : new Set(allIds))}
                />
              </th>
            )}
            {columns.map((c) => {
              const active = sort?.key === c.key;
              const ariaSort = active ? (sort!.dir === "asc" ? "ascending" : "descending") : c.sortValue ? "none" : undefined;
              const Icon = !active ? CaretUpDown : sort!.dir === "asc" ? SortAscending : SortDescending;
              return (
                <th key={c.key} scope="col" aria-sort={ariaSort} className={`${s.th} ${c.type === "numeric" ? s.numeric : ""}`} style={{ width: c.width }}>
                  {c.sortValue ? (
                    <button
                      type="button"
                      className={s.sortBtn}
                      onClick={() => setSort(!active ? { key: c.key, dir: c.type === "numeric" ? "desc" : "asc" } : { key: c.key, dir: sort!.dir === "asc" ? "desc" : "asc" })}
                    >
                      {c.header}
                      <Icon size={12} className={s.sortIcon} aria-hidden="true" />
                    </button>
                  ) : (
                    c.header
                  )}
                </th>
              );
            })}
            <th className={s.details} aria-hidden="true" />
          </tr>
        </thead>
        <tbody
          ref={body}
          onKeyDown={(e) => {
            if (!(e.target instanceof HTMLTableRowElement)) return;
            const row = sorted[focusIdx];
            if (e.key === "ArrowDown") focusRow(focusIdx + 1);
            else if (e.key === "ArrowUp") focusRow(focusIdx - 1);
            else if (e.key === "Home") focusRow(0);
            else if (e.key === "End") focusRow(sorted.length - 1);
            else if (e.key === "Enter" && row && onOpen) onOpen(row);
            else if (e.key === " " && row && selectable) toggle(rowId(row));
            else return;
            e.preventDefault();
          }}
        >
          {loading &&
            Array.from({ length: skeletonRows }, (_, i) => (
              <tr key={`sk${i}`} className={`${s.row} ${s.skelRow}`}>
                {selectable && <td className={`${s.td} ${s.check}`} />}
                {columns.map((c) => (
                  <td key={c.key} className={cellClass(c.type)} data-key={keyCols.has(c.key) ? "1" : undefined}>
                    <Skeleton h={12} w={c.type === "numeric" ? 64 : `${60 + ((i * 7 + c.key.length * 5) % 35)}%`} />
                  </td>
                ))}
                <td className={s.details} />
              </tr>
            ))}
          {!loading && sorted.length === 0 && empty && (
            <tr>
              <td colSpan={span} className={s.emptyCell}>{empty}</td>
            </tr>
          )}
          {!loading &&
            sorted.map((row, i) => {
              const id = rowId(row);
              const isSel = sel.has(id);
              const isExp = expanded.has(id);
              return (
                <tr
                  key={id}
                  data-row
                  data-expanded={isExp || undefined}
                  tabIndex={i === Math.min(focusIdx, sorted.length - 1) ? 0 : -1}
                  aria-selected={selectable ? isSel : undefined}
                  aria-label={rowLabel?.(row)}
                  className={`${s.row} ${onOpen ? s.clickable : ""}`}
                  onFocus={() => setFocusIdx(i)}
                  onClick={(e) => {
                    if ((e.target as HTMLElement).closest("a,button,input,select,textarea,label")) return;
                    onOpen?.(row);
                  }}
                >
                  {selectable && (
                    <td className={`${s.td} ${s.check}`}>
                      <input type="checkbox" checked={isSel} aria-label={`Select ${rowLabel?.(row) ?? "row"}`} onChange={() => toggle(id)} tabIndex={-1} />
                    </td>
                  )}
                  {columns.map((c) => (
                    <td key={c.key} className={cellClass(c.type)} data-label={c.header} data-key={keyCols.has(c.key) ? "1" : undefined}>
                      {c.render(row)}
                    </td>
                  ))}
                  <td className={s.details}>
                    {columns.length > keyCols.size && (
                      <button
                        type="button"
                        className={s.detailsBtn}
                        aria-expanded={isExp}
                        onClick={() =>
                          setExpanded((prev) => {
                            const next = new Set(prev);
                            if (next.has(id)) next.delete(id);
                            else next.add(id);
                            return next;
                          })
                        }
                      >
                        {isExp ? "Less" : "Details"}
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
        </tbody>
      </table>
    </div>
  );
}
