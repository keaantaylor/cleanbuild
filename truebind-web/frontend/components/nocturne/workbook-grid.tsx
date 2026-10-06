"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowDown, ArrowSquareOut, ArrowUp, CloudArrowDown, CloudArrowUp, MagnifyingGlass } from "@phosphor-icons/react";
import { api, ApiError } from "@/lib/api";
import type { CellIssue, CellState, ConnectorInfo, ConnectorLink, GridCell, GridHit, GridIssueCell, GridRow, Report, Sheet } from "@/lib/types";
import { useUi } from "@/lib/ui";
import { LoadingState } from "@/components/nocturne/ui";

/* The workbook as the review surface. Rows AND columns are virtualised: the
   DOM holds only the cells in view (plus a small margin), fetched from the
   server in tiles of ROW_PAGE rows x COL_PAGE columns, so a 100,000-row or
   500-column sheet renders a few hundred nodes. Every state is shown with its
   words (legend, cell title, inspector), never colour alone. */

const ROW_H = 24;
const HEAD_H = 44; // column letters + the sheet's own header row, frozen
const RN_W = 56;
const DEFAULT_W = 112;
const ROW_PAGE = 100;
const COL_PAGE = 40;
const OVERSCAN = 4;
const MAX_TILES = 160;

const STATE_TEXT: Record<CellState, string> = {
  verified: "Verified",
  requires_reconciliation: "Requires reconciliation",
  undetermined: "Undetermined",
};
const STATE_COLOR: Record<CellState, { bg: string; bar: string; fg: string }> = {
  verified: { bg: "transparent", bar: "var(--ok)", fg: "var(--ok)" },
  requires_reconciliation: { bg: "var(--errT)", bar: "var(--err)", fg: "var(--err)" },
  undetermined: { bg: "var(--warnT)", bar: "var(--warn)", fg: "var(--warn)" },
};

export function colName(n: number): string {
  let s = "";
  while (n > 0) {
    const r = (n - 1) % 26;
    s = String.fromCharCode(65 + r) + s;
    n = Math.floor((n - 1) / 26);
  }
  return s;
}

function parseCell(cell: string): { row: number; col: number } | null {
  const m = /^([A-Z]{1,3})(\d+)$/.exec(cell.trim().toUpperCase());
  if (!m) return null;
  let c = 0;
  for (const ch of m[1]) c = c * 26 + ch.charCodeAt(0) - 64;
  return { row: Number(m[2]), col: c };
}

const isNumeric = (v: string | null) => v != null && /^-?[\d,]*\.?\d+$/.test(v.trim());
const fmt = (v: number | string | null | undefined) =>
  v == null ? "-" : typeof v === "number" ? v.toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : String(v);

type Tile = Map<number, GridRow>;
type Pos = { i: number; col: number }; // i: index into the displayed rows, col: 1-based column

export type GridFocus = { sheet: string | null; cell: string; nonce: number };

export function WorkbookGrid({ report, sheets, focus }: { report: Report; sheets: Sheet[]; focus?: GridFocus | null }) {
  const claimSheets = useMemo(() => sheets.filter((s) => s.status === "CONFIRMED"), [sheets]);
  const [sheetId, setSheetId] = useState<string | null>(claimSheets[0]?.id ?? null);
  const [seen, setSeen] = useState<number | null>(null);
  // A request to show a cell from elsewhere (the review queue): switch to its sheet first.
  if (focus && focus.nonce !== seen) {
    setSeen(focus.nonce);
    const target = claimSheets.find((s) => s.sheet_name === focus.sheet);
    if (target && target.id !== sheetId) setSheetId(target.id);
  }
  const current = claimSheets.find((s) => s.id === sheetId);
  if (!current) return <p className="m-0 text-[14px]" style={{ color: "var(--muted)" }}>No confirmed claims sheet to show.</p>;
  const forThis = focus && (focus.sheet == null || focus.sheet === current.sheet_name) ? focus : null;
  return (
    <div className="flex flex-col gap-2">
      {claimSheets.length > 1 && (
        <div role="tablist" aria-label="Sheets" className="flex flex-wrap gap-1">
          {claimSheets.map((s) => (
            <button key={s.id} type="button" role="tab" aria-selected={s.id === sheetId} onClick={() => setSheetId(s.id)}
              className="min-h-[32px] cursor-pointer rounded-t px-3 text-[13px]"
              style={{ background: s.id === sheetId ? "var(--surface)" : "transparent", boxShadow: s.id === sheetId ? "inset 0 -2px 0 var(--accent), inset 0 0 0 1px var(--line)" : "inset 0 0 0 1px var(--line)", fontWeight: s.id === sheetId ? 600 : 400 }}>
              {s.sheet_name}
            </button>
          ))}
        </div>
      )}
      <SheetGrid key={current.id} report={report} sheet={current} focus={forThis} />
    </div>
  );
}

function SheetGrid({ report, sheet, focus }: { report: Report; sheet: Sheet; focus: GridFocus | null }) {
  const { toast } = useUi();
  const scroller = useRef<HTMLDivElement>(null);
  const [view, setView] = useState({ top: 0, left: 0, h: 560, w: 900 });
  const [meta, setMeta] = useState<{ total: number; cols: number; headerRow: number; headers: (string | null)[] } | null>(null);
  const [tiles, setTiles] = useState<Map<string, Tile>>(new Map());
  const inflight = useRef(new Set<string>());
  const [widths, setWidths] = useState<Record<number, number>>({});
  const [anchor, setAnchor] = useState<Pos>({ i: 0, col: 1 });
  const [active, setActive] = useState<Pos>({ i: 0, col: 1 });
  const [issuesOnly, setIssuesOnly] = useState(false);
  const [issueCells, setIssueCells] = useState<GridIssueCell[] | null>(null);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<GridHit[]>([]);
  const [hitIdx, setHitIdx] = useState(0);
  const [err, setErr] = useState<string | null>(null);
  const dragging = useRef(false);

  // Rows on screen: every row, or only rows with a flagged cell.
  const filteredRows = useMemo(() => (issueCells ? [...new Set(issueCells.map((c) => c.row))].sort((a, b) => a - b) : []), [issueCells]);
  const rowCount = issuesOnly ? filteredRows.length : meta?.total ?? 0;
  const rowAt = useCallback((i: number) => (issuesOnly ? filteredRows[i] : i + 1), [issuesOnly, filteredRows]);
  const indexOfRow = useCallback((row: number) => (issuesOnly ? filteredRows.indexOf(row) : row - 1), [issuesOnly, filteredRows]);

  const cols = meta?.cols ?? 0;
  const colX = useMemo(() => {
    const xs = [0];
    for (let c = 1; c <= cols; c++) xs.push(xs[c - 1] + (widths[c] ?? DEFAULT_W));
    return xs;
  }, [cols, widths]);
  const totalW = colX[cols] ?? 0;

  const firstRow = Math.max(0, Math.floor(view.top / ROW_H) - OVERSCAN);
  const lastRow = Math.min(rowCount - 1, Math.ceil((view.top + view.h) / ROW_H) + OVERSCAN);
  const firstCol = Math.max(1, upperBound(colX, view.left) - 1);
  const lastCol = Math.min(cols, upperBound(colX, view.left + view.w) + 1);

  const tileKey = useCallback((i: number, col: number) => `${issuesOnly ? "f" : "r"}:${Math.floor(i / ROW_PAGE)}:${Math.floor((col - 1) / COL_PAGE)}`, [issuesOnly]);

  const fetchTile = useCallback(async (key: string) => {
    if (inflight.current.has(key)) return;
    inflight.current.add(key);
    const [mode, rp, cp] = key.split(":");
    const r = Number(rp), c = Number(cp);
    try {
      const page = await api.gridTile(report.id, sheet.id, mode === "f"
        ? { rows: filteredRows.slice(r * ROW_PAGE, (r + 1) * ROW_PAGE), colOffset: c * COL_PAGE, colLimit: COL_PAGE }
        : { offset: r * ROW_PAGE, limit: ROW_PAGE, colOffset: c * COL_PAGE, colLimit: COL_PAGE });
      const tile: Tile = new Map(page.rows.map((row) => [row.row, row]));
      setTiles((prev) => {
        const next = new Map(prev);
        next.set(key, tile);
        while (next.size > MAX_TILES) next.delete(next.keys().next().value as string);
        return next;
      });
      if (!meta) setMeta({ total: page.total_rows, cols: page.columns, headerRow: page.header_row, headers: page.headers ?? [] });
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Could not load the sheet.");
    } finally {
      inflight.current.delete(key);
    }
  }, [report.id, sheet.id, filteredRows, meta]);

  // First tile gives the sheet's size; then fetch whatever is in view.
  useEffect(() => {
    if (!meta) void Promise.resolve().then(() => fetchTile("r:0:0"));
  }, [meta, fetchTile]);
  useEffect(() => {
    if (!meta || rowCount === 0) return;
    const need = new Set<string>();
    for (let i = firstRow; i <= lastRow; i += Math.max(1, Math.floor(ROW_PAGE / 2))) {
      for (let c = firstCol; c <= lastCol; c += Math.max(1, Math.floor(COL_PAGE / 2))) need.add(tileKey(i, c));
    }
    need.add(tileKey(lastRow, lastCol));
    const missing = [...need].filter((k) => !tiles.has(k));
    if (missing.length) void Promise.resolve().then(() => missing.forEach((k) => void fetchTile(k)));
  }, [meta, rowCount, firstRow, lastRow, firstCol, lastCol, tiles, tileKey, fetchTile]);

  const cellAt = useCallback((i: number, col: number): { row: GridRow | undefined; cell: GridCell | undefined } => {
    const row = tiles.get(tileKey(i, col))?.get(rowAt(i));
    return { row, cell: row?.cells[(col - 1) % COL_PAGE] };
  }, [tiles, tileKey, rowAt]);

  const refreshTileOf = useCallback((i: number, col: number) => {
    const key = tileKey(i, col);
    setTiles((prev) => {
      const next = new Map(prev);
      next.delete(key);
      return next;
    });
  }, [tileKey]);

  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setView((v) => ({ ...v, h: el.clientHeight, w: el.clientWidth })));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const onScroll = () => {
    const el = scroller.current;
    if (el) setView({ top: el.scrollTop, left: el.scrollLeft, h: el.clientHeight, w: el.clientWidth });
  };

  const reveal = useCallback((p: Pos) => {
    const el = scroller.current;
    if (!el) return;
    const y = p.i * ROW_H, x0 = colX[p.col - 1] ?? 0, x1 = colX[p.col] ?? x0;
    if (y < el.scrollTop) el.scrollTop = y;
    else if (y + ROW_H > el.scrollTop + el.clientHeight) el.scrollTop = y + ROW_H - el.clientHeight;
    if (x0 < el.scrollLeft) el.scrollLeft = x0;
    else if (x1 > el.scrollLeft + el.clientWidth) el.scrollLeft = x1 - el.clientWidth;
  }, [colX]);

  const select = useCallback((p: Pos, extend = false) => {
    const q = { i: Math.max(0, Math.min(rowCount - 1, p.i)), col: Math.max(1, Math.min(cols, p.col)) };
    setActive(q);
    if (!extend) setAnchor(q);
    reveal(q);
  }, [rowCount, cols, reveal]);

  const goToCell = useCallback((row: number, col: number) => {
    let i = indexOfRow(row);
    if (i < 0) {
      setIssuesOnly(false);
      i = row - 1;
    }
    requestAnimationFrame(() => {
      select({ i, col });
      scroller.current?.focus();
    });
  }, [indexOfRow, select]);

  // Jump requested from outside (an issue's "Show in workbook").
  useEffect(() => {
    if (!focus || !meta) return;
    const p = parseCell(focus.cell);
    if (!p) return;
    const id = requestAnimationFrame(() => goToCell(p.row, p.col));
    return () => cancelAnimationFrame(id);
  }, [focus, meta, goToCell]);

  useEffect(() => {
    let cancelled = false;
    api.gridIssues(report.id, sheet.id).then((r) => { if (!cancelled) setIssueCells(r.items); }).catch(() => undefined);
    return () => { cancelled = true; };
  }, [report.id, sheet.id]);

  function onKey(e: React.KeyboardEvent) {
    const page = Math.max(1, Math.floor(view.h / ROW_H) - 1);
    const ext = e.shiftKey;
    const moves: Record<string, Pos> = {
      ArrowDown: { i: active.i + 1, col: active.col }, ArrowUp: { i: active.i - 1, col: active.col },
      ArrowRight: { i: active.i, col: active.col + 1 }, ArrowLeft: { i: active.i, col: active.col - 1 },
      PageDown: { i: active.i + page, col: active.col }, PageUp: { i: active.i - page, col: active.col },
      Home: e.ctrlKey ? { i: 0, col: 1 } : { i: active.i, col: 1 }, End: e.ctrlKey ? { i: rowCount - 1, col: cols } : { i: active.i, col: cols },
      Tab: { i: active.i, col: active.col + (e.shiftKey ? -1 : 1) },
    };
    if (e.key in moves) {
      e.preventDefault();
      select(moves[e.key], ext && e.key !== "Tab");
    } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "f") {
      e.preventDefault();
      document.getElementById(`grid-search-${sheet.id}`)?.focus();
    } else if (e.altKey && (e.key === "n" || e.key === "p")) {
      e.preventDefault();
      jumpIssue(e.key === "n" ? 1 : -1);
    }
  }

  function jumpIssue(dir: 1 | -1) {
    const list = (issueCells ?? []).filter((c) => c.open > 0 && c.col != null);
    if (!list.length) return;
    const cur = rowAt(active.i);
    const idx = dir > 0 ? list.findIndex((c) => c.row > cur || (c.row === cur && (c.col ?? 0) > active.col))
      : findLastIndex(list, (c) => c.row < cur || (c.row === cur && (c.col ?? 0) < active.col));
    const target = list[idx >= 0 ? idx : dir > 0 ? 0 : list.length - 1];
    goToCell(target.row, target.col!);
  }

  async function runSearch(next = 0) {
    if (!query.trim()) return;
    try {
      const items = next === 0 || !hits.length ? (await api.gridSearch(report.id, sheet.id, query.trim())).items : hits;
      setHits(items);
      if (!items.length) return toast("No cell contains that text.", "err");
      const k = ((next % items.length) + items.length) % items.length;
      setHitIdx(k);
      goToCell(items[k].row, items[k].col);
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Search failed.", "err");
    }
  }

  // Range summary: count and sum of the numbers in the selection.
  const range = { i0: Math.min(anchor.i, active.i), i1: Math.max(anchor.i, active.i), c0: Math.min(anchor.col, active.col), c1: Math.max(anchor.col, active.col) };
  const summary = useMemo(() => {
    let n = 0, nums = 0, sum = 0;
    for (let i = range.i0; i <= Math.min(range.i1, range.i0 + 2000); i++) {
      for (let c = range.c0; c <= range.c1; c++) {
        n++;
        const v = cellAt(i, c).cell?.v ?? null;
        if (isNumeric(v)) { nums++; sum += Number(v!.replace(/,/g, "")); }
      }
    }
    return { n, nums, sum };
  }, [range.i0, range.i1, range.c0, range.c1, cellAt]);

  const startResize = (col: number) => (e: React.PointerEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const x0 = e.clientX, w0 = widths[col] ?? DEFAULT_W;
    const move = (ev: PointerEvent) => setWidths((w) => ({ ...w, [col]: Math.max(40, Math.min(600, w0 + ev.clientX - x0)) }));
    const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  if (err) return <p className="m-0 text-[13px]" style={{ color: "var(--err)" }}>{err}</p>;
  const activeData = cellAt(active.i, active.col);
  const activeAddr = `${colName(active.col)}${rowAt(active.i) ?? ""}`;
  const hitSet = new Set(hits.map((h) => `${h.row}:${h.col}`));
  const openIssues = (issueCells ?? []).reduce((n, c) => n + c.open, 0);

  return (
    <div className="grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1fr)_320px]">
      <section className="tb-card flex min-w-0 flex-col overflow-hidden" aria-label={`Sheet ${sheet.sheet_name}`}>
        {/* toolbar */}
        <div className="flex flex-wrap items-center gap-2 px-3 py-2" style={{ boxShadow: "0 1px 0 var(--line)" }}>
          <form className="flex items-center gap-1" onSubmit={(e) => { e.preventDefault(); void runSearch(hits.length ? hitIdx + 1 : 0); }}>
            <label htmlFor={`grid-search-${sheet.id}`} className="sr-only">Search the sheet</label>
            <input id={`grid-search-${sheet.id}`} className="tb-input !min-h-[32px] !w-[180px] !py-1 text-[13px]" placeholder="Search values or formulas" value={query}
              onChange={(e) => { setQuery(e.target.value); setHits([]); }} />
            <button type="submit" className="tb-btn !min-h-[32px]" aria-label="Find next"><MagnifyingGlass size={14} /></button>
            {hits.length > 0 && <span className="tnum text-[12px]" style={{ color: "var(--muted)" }}>{hitIdx + 1} of {hits.length}</span>}
          </form>
          <label className="flex cursor-pointer items-center gap-1.5 text-[13px]">
            <input type="checkbox" checked={issuesOnly} onChange={(e) => { setIssuesOnly(e.target.checked); setTiles(new Map()); setActive({ i: 0, col: 1 }); setAnchor({ i: 0, col: 1 }); if (scroller.current) scroller.current.scrollTop = 0; }} disabled={!filteredRows.length} />
            Rows with issues only
          </label>
          <button type="button" className="tb-btn !min-h-[32px] text-[13px]" onClick={() => jumpIssue(-1)} disabled={!openIssues} title="Previous open issue (Alt+P)"><ArrowUp size={14} />Previous issue</button>
          <button type="button" className="tb-btn !min-h-[32px] text-[13px]" onClick={() => jumpIssue(1)} disabled={!openIssues} title="Next open issue (Alt+N)"><ArrowDown size={14} />Next issue</button>
          <span className="tnum ml-auto text-[12px]" style={{ color: "var(--muted)" }}>{meta ? `${meta.total.toLocaleString("en-GB")} rows · ${cols} columns · ${openIssues} open issue cells` : "Loading the sheet…"}</span>
        </div>
        <Legend />
        {/* grid */}
        <div className="relative" style={{ height: 560 }}>
          {!meta && <div className="absolute inset-0 z-[4] p-6" style={{ background: "var(--surface)" }}><LoadingState label="Loading the sheet" rows={10} /></div>}
          <div className="absolute left-0 top-0 z-[3] grid place-items-center text-[11px]" style={{ width: RN_W, height: HEAD_H, background: "var(--surface2)", boxShadow: "inset -1px -1px 0 var(--line2)", color: "var(--faint)" }}>{activeAddr}</div>
          {/* frozen column letters + the sheet's header row */}
          <div className="absolute top-0 z-[2] overflow-hidden" style={{ left: RN_W, right: 0, height: HEAD_H, background: "var(--surface2)" }} aria-hidden>
            <div className="relative" style={{ width: totalW, height: HEAD_H, transform: `translateX(${-view.left}px)` }}>
              {range1(firstCol, lastCol).map((c) => (
                <div key={c} className="absolute top-0" style={{ left: colX[c - 1], width: colX[c] - colX[c - 1], height: HEAD_H, boxShadow: "inset -1px -1px 0 var(--line2)" }}>
                  <div className="text-center text-[11px] font-medium" style={{ height: 18, lineHeight: "18px", color: c >= range.c0 && c <= range.c1 ? "var(--accentText)" : "var(--faint)" }}>{colName(c)}</div>
                  <div className="truncate px-1.5 text-[12px] font-semibold" style={{ height: HEAD_H - 18, lineHeight: `${HEAD_H - 18}px` }} title={meta?.headers[c - 1] ?? ""}>{meta?.headers[c - 1] ?? ""}</div>
                  <span onPointerDown={startResize(c)} className="absolute right-0 top-0 h-full w-[6px] cursor-col-resize" role="separator" aria-orientation="vertical" />
                </div>
              ))}
            </div>
          </div>
          {/* frozen row numbers */}
          <div className="absolute left-0 z-[2] overflow-hidden" style={{ top: HEAD_H, bottom: 0, width: RN_W, background: "var(--surface2)" }} aria-hidden>
            <div className="relative" style={{ height: rowCount * ROW_H, transform: `translateY(${-view.top}px)` }}>
              {range1(firstRow, lastRow).map((i) => (
                <div key={i} className="tnum absolute left-0 pr-2 text-right text-[11px]" style={{ top: i * ROW_H, width: RN_W, height: ROW_H, lineHeight: `${ROW_H}px`, boxShadow: "inset -1px -1px 0 var(--line2)", color: i >= range.i0 && i <= range.i1 ? "var(--accentText)" : "var(--faint)" }}>{rowAt(i)}</div>
              ))}
            </div>
          </div>
          {/* cells */}
          <div ref={scroller} tabIndex={0} role="grid" aria-label={`${sheet.sheet_name}, ${rowCount} rows`} aria-rowcount={rowCount} aria-colcount={cols}
            aria-activedescendant={`gc-${active.i}-${active.col}`} onScroll={onScroll} onKeyDown={onKey}
            className="absolute overflow-auto outline-none focus-visible:ring-2" style={{ top: HEAD_H, left: RN_W, right: 0, bottom: 0 }}
            onPointerUp={() => { dragging.current = false; }}>
            <div className="relative" style={{ width: totalW, height: rowCount * ROW_H }}>
              {range1(firstRow, lastRow).map((i) => range1(firstCol, lastCol).map((c) => {
                const { row, cell } = cellAt(i, c);
                const st = cell?.state ?? null;
                const inRange = i >= range.i0 && i <= range.i1 && c >= range.c0 && c <= range.c1;
                const isActive = i === active.i && c === active.col;
                const sc = st && st !== "verified" ? STATE_COLOR[st] : null;
                const title = st ? `${STATE_TEXT[st]}${cell?.issues?.[0] ? `: ${cell.issues[0].label}` : ""}` : undefined;
                return (
                  <div key={`${i}-${c}`} id={`gc-${i}-${c}`} role="gridcell" aria-selected={inRange} title={title}
                    onPointerDown={(e) => { dragging.current = true; select({ i, col: c }, e.shiftKey); scroller.current?.focus(); }}
                    onPointerEnter={() => { if (dragging.current) select({ i, col: c }, true); }}
                    className={`absolute truncate px-1.5 text-[12.5px] ${isNumeric(cell?.v ?? null) ? "tnum text-right" : ""}`}
                    style={{
                      top: i * ROW_H, left: colX[c - 1], width: colX[c] - colX[c - 1], height: ROW_H, lineHeight: `${ROW_H}px`,
                      background: inRange && !isActive ? "var(--accentTint)" : sc?.bg ?? (row?.kind === "header" ? "var(--surface2)" : "var(--surface)"),
                      boxShadow: [isActive ? "inset 0 0 0 2px var(--accent)" : "inset -1px -1px 0 var(--line)", sc ? `inset 3px 0 0 ${sc.bar}` : "",
                        hitSet.has(`${rowAt(i)}:${c}`) ? "inset 0 0 0 1px var(--warn)" : ""].filter(Boolean).join(", "),
                      fontWeight: row?.kind === "header" ? 600 : 400,
                      color: row?.kind === "structural" ? "var(--faint)" : "var(--text)",
                    }}>
                    {cell ? cell.v ?? "" : row === undefined ? <span style={{ color: "var(--line2)" }}>·</span> : ""}
                    {cell?.correction && <span className="sr-only">, correction {cell.correction.status.toLowerCase()}</span>}
                  </div>
                );
              }))}
            </div>
          </div>
        </div>
        {/* status bar */}
        <div className="tnum flex flex-wrap gap-x-4 px-3 py-1.5 text-[12px]" style={{ boxShadow: "0 -1px 0 var(--line)", color: "var(--muted)" }} aria-live="polite">
          <span>{colName(range.c0)}{rowAt(range.i0)}{summary.n > 1 ? `:${colName(range.c1)}${rowAt(range.i1)}` : ""}</span>
          <span>{summary.n} cell{summary.n === 1 ? "" : "s"}</span>
          {summary.nums > 0 && <span>Sum {summary.sum.toLocaleString("en-GB", { maximumFractionDigits: 2 })}</span>}
          <span className="ml-auto">Arrows, Shift to select, Ctrl+F search, Alt+N next issue</span>
        </div>
      </section>
      <Inspector report={report} sheet={sheet} address={activeAddr} cell={activeData.cell} row={activeData.row}
        onChanged={() => { refreshTileOf(active.i, active.col); setIssueCells(null); api.gridIssues(report.id, sheet.id).then((r) => setIssueCells(r.items)).catch(() => undefined); }} />
    </div>
  );
}

function Legend() {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 px-3 py-1.5 text-[12px]" style={{ boxShadow: "0 1px 0 var(--line)", color: "var(--muted)" }}>
      {(Object.keys(STATE_TEXT) as CellState[]).map((k) => (
        <span key={k} className="flex items-center gap-1.5">
          <span className="inline-block h-3 w-3" style={{ background: STATE_COLOR[k].bg === "transparent" ? "var(--surface)" : STATE_COLOR[k].bg, boxShadow: `inset 3px 0 0 ${STATE_COLOR[k].bar}, inset 0 0 0 1px var(--line2)` }} />
          {STATE_TEXT[k]}
        </span>
      ))}
      <span>Select a cell to see its value, formula, issues and corrections.</span>
    </div>
  );
}

function Inspector({ report, sheet, address, cell, row, onChanged }: { report: Report; sheet: Sheet; address: string; cell?: GridCell; row?: GridRow; onChanged: () => void }) {
  const { toast } = useUi();
  const [value, setValue] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const issues: CellIssue[] = [...(cell?.issues ?? []), ...(row?.row_issues ?? [])];
  const st = cell?.state ?? null;
  const corr = cell?.correction ?? null;
  const firstOpen = (cell?.issues ?? []).find((i) => !["AUTO_FIXED", "RESOLVED", "OVERRIDDEN"].includes(i.status));

  async function propose() {
    setBusy(true);
    try {
      const c = await api.proposeCorrection(report.id, { sheet_id: sheet.id, cell: address, after_value: value, reason, issue_id: firstOpen?.issue_id });
      toast(`Proposed under policy ${c.policy?.replaceAll("_", " ").toLowerCase()}.`, "ok");
      setValue("");
      setReason("");
      onChanged();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Not proposed.", "err");
    } finally {
      setBusy(false);
    }
  }
  async function decide(approve: boolean) {
    if (!corr) return;
    setBusy(true);
    try {
      const c = await api.decideCorrection(report.id, corr.id, approve);
      const rc = c.recheck;
      toast(approve ? (rc?.status === "ran" ? (rc.still_failing ? "Approved, but the re-check still fails." : "Approved and verified by the re-check.") : rc?.status === "queued" ? "Approved; re-check queued." : "Approved.") : "Rejected.", rc?.still_failing ? "err" : "ok");
      onChanged();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Not saved.", "err");
    } finally {
      setBusy(false);
    }
  }

  return (
    <aside className="tb-card flex flex-col gap-3 p-4 text-[13px]" aria-label="Cell inspector">
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-[family-name:var(--font-mono)] text-[14px] font-semibold">{sheet.sheet_name}!{address}</span>
        {st && <span className="rounded px-1.5 py-0.5 text-[12px] font-semibold" style={{ color: STATE_COLOR[st].fg, background: st === "verified" ? "var(--okT)" : STATE_COLOR[st].bg }}>{STATE_TEXT[st]}</span>}
      </div>
      <dl className="m-0 grid grid-cols-[72px_minmax(0,1fr)] gap-x-3 gap-y-1">
        <dt style={{ color: "var(--muted)" }}>Value</dt>
        <dd className="tnum m-0 break-words">{cell?.v ?? <span style={{ color: "var(--faint)" }}>(blank)</span>}</dd>
        {cell?.f && (<><dt style={{ color: "var(--muted)" }}>Formula</dt><dd className="m-0 break-all font-[family-name:var(--font-mono)] text-[12px]">{cell.f}</dd></>)}
        <dt style={{ color: "var(--muted)" }}>Row</dt>
        <dd className="m-0">{row ? row.kind : "loading"}</dd>
      </dl>
      {issues.map((i) => (
        <div key={i.issue_id} className="flex flex-col gap-1 rounded p-2" style={{ boxShadow: "inset 0 0 0 1px var(--line)" }}>
          <span className="font-medium" style={{ color: STATE_COLOR[i.state]?.fg }}>{STATE_TEXT[i.state]} · {i.status.replaceAll("_", " ").toLowerCase()}</span>
          <span>{i.label}</span>
          {(i.expected != null || i.actual != null) && (
            <table className="tnum w-full text-[12.5px]">
              <tbody>
                <tr><td style={{ color: "var(--muted)" }}>Expected</td><td className="text-right">{fmt(i.expected)}</td></tr>
                <tr><td style={{ color: "var(--muted)" }}>Actual</td><td className="text-right font-semibold">{fmt(i.actual)}</td></tr>
                <tr><td style={{ color: "var(--muted)" }}>Difference</td><td className="text-right">{fmt(i.difference)}</td></tr>
              </tbody>
            </table>
          )}
          <span className="font-[family-name:var(--font-mono)] text-[11.5px]" style={{ color: "var(--faint)" }}>{(i.rule ?? "").toUpperCase()} v{i.rule_version ?? "1.0"}</span>
          {i.known_exception && <span className="text-[12px]" style={{ color: "var(--muted)" }}>Accepted as reported last time{i.known_exception.reason ? `: ${i.known_exception.reason}` : ""}</span>}
        </div>
      ))}
      {corr && (
        <div className="flex flex-col gap-2 rounded p-2" style={{ boxShadow: "inset 0 0 0 1px var(--line)" }}>
          <span>Correction to <b className="tnum">{corr.after ?? "(blank)"}</b> · {corr.status.toLowerCase()}{corr.policy ? ` · ${corr.policy.replaceAll("_", " ").toLowerCase()}` : ""}{corr.verified === true ? " · verified" : corr.verified === false ? " · re-check failed" : ""}</span>
          {corr.status === "PROPOSED" && (
            <div className="flex gap-2">
              <button type="button" className="tb-btn tb-btn-solid min-h-[36px]" disabled={busy} onClick={() => void decide(true)}>Approve</button>
              <button type="button" className="tb-btn min-h-[36px]" disabled={busy} onClick={() => void decide(false)}>Reject</button>
            </div>
          )}
        </div>
      )}
      {cell && row?.kind === "claim" && !(corr && corr.status === "PROPOSED") && (
        <form className="flex flex-col gap-1.5" onSubmit={(e) => { e.preventDefault(); if (reason.trim()) void propose(); }}>
          <label className="font-medium" htmlFor="corr-value">Propose a correction</label>
          <input id="corr-value" className="tb-input !min-h-[34px] text-[13px]" value={value} onChange={(e) => setValue(e.target.value)} placeholder={cell.v ?? ""} />
          <input aria-label="Reason" className="tb-input !min-h-[34px] text-[13px]" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Why (required)" maxLength={2000} />
          <button type="submit" className="tb-btn min-h-[36px]" disabled={busy || !reason.trim()}>Propose</button>
          <span className="text-[12px]" style={{ color: "var(--faint)" }}>The source file is never changed. Amounts, currency, status and dates need a second person.</span>
        </form>
      )}
      <Connectors report={report} />
    </aside>
  );
}

function Connectors({ report }: { report: Report }) {
  const { toast } = useUi();
  const [providers, setProviders] = useState<ConnectorInfo[]>([]);
  const [links, setLinks] = useState<ConnectorLink[]>([]);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let cancelled = false;
    Promise.all([api.listConnectors(), api.connectorLinks(report.id)]).then(([p, l]) => {
      if (!cancelled) { setProviders(p.items.filter((x) => x.configured)); setLinks(l.items); }
    }).catch(() => undefined);
    return () => { cancelled = true; };
  }, [report.id]);
  if (!providers.length && !links.length) return null;
  const run = async (fn: () => Promise<string>) => {
    setBusy(true);
    try { toast(await fn(), "ok"); } catch (e) { toast(e instanceof ApiError ? e.message : "That did not work.", "err"); } finally { setBusy(false); }
  };
  return (
    <div className="flex flex-col gap-2" style={{ boxShadow: "0 -1px 0 var(--line)", paddingTop: 12 }}>
      {providers.map((p) => (
        <button key={p.key} type="button" className="tb-btn min-h-[36px]" disabled={busy} onClick={() => void run(async () => {
          const l = await api.openInProvider(report.id, p.key);
          setLinks((x) => [l, ...x]);
          window.open(l.web_url, "_blank", "noopener,noreferrer");
          return `Opened a copy in ${p.label}. The source file is unchanged.`;
        })}><ArrowSquareOut size={14} />{p.open_label}</button>
      ))}
      {links.slice(0, 3).map((l) => (
        <div key={l.id} className="flex flex-wrap items-center gap-1.5 text-[12px]">
          <a href={l.web_url} target="_blank" rel="noopener noreferrer" className="underline" style={{ color: "var(--accentText)" }}>{l.label} copy</a>
          <button type="button" className="tb-btn !min-h-[28px] text-[12px]" disabled={busy} title="Read edits back as proposed corrections" onClick={() => void run(async () => {
            const r = await api.pullConnector(report.id, l.id);
            return `${r.changed_cells} changed cells: ${r.proposed} proposed, ${r.blocked} refused by policy.`;
          })}><CloudArrowDown size={13} />Read edits</button>
          <button type="button" className="tb-btn !min-h-[28px] text-[12px]" disabled={busy} title="Write the approved corrections to that file" onClick={() => void run(async () => {
            await api.pushConnector(report.id, l.id);
            return `Wrote the working copy to ${l.label} as a new version.`;
          })}><CloudArrowUp size={13} />Write back</button>
        </div>
      ))}
    </div>
  );
}

function range1(a: number, b: number): number[] {
  const out = [];
  for (let i = a; i <= b; i++) out.push(i);
  return out;
}

function upperBound(xs: number[], x: number): number {
  let lo = 0, hi = xs.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (xs[mid] <= x) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

function findLastIndex<T>(xs: T[], f: (x: T) => boolean): number {
  for (let i = xs.length - 1; i >= 0; i--) if (f(xs[i])) return i;
  return -1;
}
