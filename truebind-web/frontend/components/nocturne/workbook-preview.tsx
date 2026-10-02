"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowsOut, DownloadSimple, X } from "@phosphor-icons/react";
import { api, ApiError } from "@/lib/api";
import type { GridPage, GridRow, Report, Sheet } from "@/lib/types";
import { exportFile } from "@/lib/exports";
import { useUi } from "@/lib/ui";

const PAGE = 100;
const FILL: Record<string, { bg: string; fg?: string }> = {
  ok: { bg: "#E2F0D9" },
  warn: { bg: "#FFF2CC" },
  err: { bg: "#FFC7CE", fg: "#9C0006" },
  grey: { bg: "#E7E6E6" },
};

function colName(i: number) {
  let s = "";
  for (let n = i + 1; n > 0; n = Math.floor((n - 1) / 26)) s = String.fromCharCode(65 + ((n - 1) % 26)) + s;
  return s;
}

/** Pages of a sheet, loaded 100 rows at a time as the user scrolls. The caller
 * remounts it per sheet (key), so state never needs resetting. */
function useGrid(reportId: string, sheetId: string) {
  const [rows, setRows] = useState<GridRow[]>([]);
  const [meta, setMeta] = useState<Omit<GridPage, "rows"> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const busy = useRef(false);
  const load = useCallback(
    (offset: number) =>
      api
        .sheetGrid(reportId, sheetId, offset, PAGE)
        .then(({ rows: got, ...m }) => {
          setMeta(m);
          setRows((r) => [...r, ...got]);
        })
        .catch((e) => setError(e instanceof ApiError ? e.message : "The sheet could not be loaded."))
        .finally(() => {
          busy.current = false;
          setLoading(false);
        }),
    [reportId, sheetId],
  );
  useEffect(() => {
    busy.current = true;
    void load(0);
  }, [load]);
  const more = useCallback(() => {
    if (busy.current || (meta && rows.length >= meta.total_rows)) return;
    busy.current = true;
    setLoading(true);
    void load(rows.length);
  }, [load, meta, rows.length]);
  return { rows, meta, error, loading, more, done: !!meta && rows.length >= meta.total_rows };
}

function Table({ g, mode, height, onPick }: { g: ReturnType<typeof useGrid>; mode: "original" | "review"; height: number; onPick: (r: GridRow, c: number) => void }) {
  const sentinel = useRef<HTMLDivElement>(null);
  const { more, done } = g;
  useEffect(() => {
    const el = sentinel.current;
    if (!el || done) return;
    const io = new IntersectionObserver((e) => e[0]?.isIntersecting && void more(), { rootMargin: "300px" });
    io.observe(el);
    return () => io.disconnect();
  }, [more, done]);
  const cols = g.meta?.columns ?? 0;
  return (
    <div className="overflow-auto rounded border text-[12px]" style={{ maxHeight: height, borderColor: "var(--line2)", background: "#fff", color: "#1f2328" }}>
      <table className="tnum border-collapse" style={{ minWidth: "100%" }}>
        <thead className="sticky top-0 z-[1]" style={{ background: "#f3f4f6" }}>
          <tr>
            <th className="sticky left-0 z-[2] w-12 border px-1.5 py-1 text-right font-normal" style={{ background: "#f3f4f6", borderColor: "#d0d7de", color: "#57606a" }} />
            {Array.from({ length: cols }, (_, i) => (
              <th key={i} className="min-w-[90px] border px-1.5 py-1 text-center font-normal" style={{ borderColor: "#d0d7de", color: "#57606a" }}>{colName(i)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {g.rows.map((r) => (
            <tr key={r.row}>
              <td className="sticky left-0 border px-1.5 py-[3px] text-right" style={{ background: "#f3f4f6", borderColor: "#d0d7de", color: "#57606a" }}>{r.row}</td>
              {r.cells.map((c, i) => {
                const f = mode === "review" && c.tone ? FILL[c.tone] : null;
                const flagged = mode === "review" && c.notes.length > 0;
                return (
                  <td
                    key={i}
                    onClick={flagged ? () => onPick(r, i) : undefined}
                    title={flagged ? c.notes.map((n) => `${n.result}: ${n.text}\nFix: ${n.fix}`).join("\n\n") : undefined}
                    className={`max-w-[260px] truncate border px-1.5 py-[3px] ${flagged ? "cursor-pointer" : ""}`}
                    style={{ borderColor: "#d0d7de", background: f?.bg, color: f?.fg, fontWeight: r.kind === "header" ? 600 : undefined }}
                  >
                    {c.v ?? ""}
                    {flagged && <span className="ml-1 inline-block h-1.5 w-1.5 rounded-full align-middle" style={{ background: c.tone === "err" ? "#9C0006" : "#7F6000" }} />}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {!g.done && <div ref={sentinel} className="px-3 py-2 text-[12px]" style={{ color: "#57606a" }}>{g.loading ? "Loading rows…" : "Scroll for more rows"}</div>}
    </div>
  );
}

/** The source workbook inline: Original (as uploaded) and Review (colour-coded with notes). */
export function WorkbookPreview({ report, sheets }: { report: Report; sheets: Sheet[] }) {
  const claimSheets = sheets.filter((s) => s.status === "CONFIRMED");
  const [sheetId, setSheetId] = useState<string | null>(claimSheets[0]?.id ?? null);
  if (!sheetId) return null;
  return <Preview key={sheetId} report={report} claimSheets={claimSheets} sheetId={sheetId} setSheetId={setSheetId} />;
}

function Preview({ report, claimSheets, sheetId, setSheetId }: { report: Report; claimSheets: Sheet[]; sheetId: string; setSheetId: (id: string) => void }) {
  const { toast } = useUi();
  const [mode, setMode] = useState<"original" | "review">("review");
  const [expanded, setExpanded] = useState(false);
  const [pick, setPick] = useState<{ r: GridRow; c: number } | null>(null);
  const g = useGrid(report.id, sheetId);
  const name = report.file_name.replace(/\.\w+$/, "");
  const picked = pick ? pick.r.cells[pick.c] : null;

  const controls = (
    <div className="flex flex-wrap items-center gap-2">
      {claimSheets.length > 1 && (
        <select className="tb-input !min-h-[30px] !w-auto !py-1 text-[13px]" value={sheetId} onChange={(e) => setSheetId(e.target.value)} aria-label="Sheet">
          {claimSheets.map((s) => <option key={s.id} value={s.id}>{s.sheet_name}</option>)}
        </select>
      )}
      <div role="tablist" aria-label="View" className="flex rounded border p-0.5" style={{ borderColor: "var(--line2)" }}>
        {(["original", "review"] as const).map((m) => (
          <button key={m} type="button" role="tab" aria-selected={mode === m} onClick={() => setMode(m)} className="cursor-pointer rounded-sm px-2.5 py-1 text-[13px]" style={{ background: mode === m ? "var(--accentTint)" : "transparent", color: mode === m ? "var(--text)" : "var(--muted)" }}>
            {m === "original" ? "Original" : "Review"}
          </button>
        ))}
      </div>
      <button type="button" className="tb-btn !py-1 text-[13px]" onClick={() => setExpanded(true)}><ArrowsOut />Expand</button>
      <button type="button" className="tb-btn !py-1 text-[13px]" onClick={() => void exportFile(api.annotatedWorkbookUrl(report.id), `${name}_REVIEWED`, toast)}><DownloadSimple />Excel</button>
    </div>
  );
  const legend = (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-[12px]" style={{ color: "var(--muted)" }}>
      {([["ok", "Checked, OK"], ["warn", "Format issue or can’t validate"], ["err", "Error"], ["grey", "Title, header, subtotal"]] as const).map(([k, l]) => (
        <span key={k} className="flex items-center gap-1.5"><span className="h-3 w-3 border" style={{ background: FILL[k].bg, borderColor: "#d0d7de" }} />{l}</span>
      ))}
      <span>Click a marked cell for the finding and the fix.</span>
    </div>
  );
  const body = (height: number) =>
    g.error ? <div className="text-[13px]" style={{ color: "var(--err)" }}>{g.error}</div> : !g.meta ? <div className="text-[13px]" style={{ color: "var(--muted)" }}>Loading the sheet…</div> : <Table g={g} mode={mode} height={height} onPick={(r, c) => setPick({ r, c })} />;

  return (
    <section className="no-print flex w-full max-w-[1100px] flex-col gap-2" aria-labelledby="wb-preview">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 id="wb-preview" className="m-0 text-[16px] font-medium">Your workbook, reviewed</h2>
          <span className="text-[13px]" style={{ color: "var(--muted)" }}>{g.meta ? `${g.meta.sheet_name} · ${g.meta.total_rows.toLocaleString("en-GB")} rows · values exactly as received` : " "}</span>
        </div>
        {controls}
      </div>
      {mode === "review" && legend}
      {body(460)}
      {picked && pick && (
        <div className="flex flex-col gap-1.5 rounded border p-3 text-[13px]" style={{ borderColor: "var(--line2)", background: "var(--surface)" }} role="dialog" aria-label="Finding">
          <div className="flex items-start justify-between gap-2">
            <span className="tnum font-medium">{g.meta?.sheet_name}!{colName(pick.c)}{pick.r.row} · {picked.v ?? "(blank)"}</span>
            <button type="button" className="cursor-pointer" aria-label="Close" onClick={() => setPick(null)}><X /></button>
          </div>
          {picked.notes.map((n, i) => (
            <div key={i}><b className="font-medium" style={{ color: n.status === "FAIL" ? "var(--err)" : "var(--warn)" }}>{n.result}</b>: {n.text}<br /><span style={{ color: "var(--muted)" }}>Fix: {n.fix}</span></div>
          ))}
        </div>
      )}
      {expanded && (
        <div className="fixed inset-0 z-50 flex flex-col gap-2 p-4" style={{ background: "var(--bg)" }} role="dialog" aria-label="Workbook, full view">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-[15px] font-medium">{report.file_name}</span>
            <div className="flex items-center gap-2">{controls}<button type="button" className="tb-btn !py-1 text-[13px]" onClick={() => setExpanded(false)}><X />Close</button></div>
          </div>
          {mode === "review" && legend}
          {body(typeof window !== "undefined" ? window.innerHeight - 140 : 700)}
        </div>
      )}
    </section>
  );
}
