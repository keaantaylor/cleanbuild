"use client";

import { Tooltip } from "./Overlay";
import s from "./SheetGrid.module.css";

export type CellState = "warn" | "error" | "ok";
export type Cell = string | { v: string; state?: CellState; note?: string; selected?: boolean };

export interface SheetRow {
  /** Row number as it appears in the source sheet. */
  n: number;
  cells: Cell[];
}

const letter = (i: number): string => (i < 26 ? String.fromCharCode(65 + i) : letter(Math.floor(i / 26) - 1) + letter(i % 26));
const looksNumeric = (v: string) => /^[£$€]?-?[\d,]+(\.\d+)?$/.test(v.trim());

/** A source excerpt as a spreadsheet: column letters, row numbers, the header
 * row, flagged cells with a tooltip saying why, and sheet tabs. Values are
 * shown exactly as received. */
export function SheetGrid({
  headers,
  headerRow,
  rows,
  firstColumn = 0,
  title,
  formula,
  tabs,
  activeTab,
  showLetters = true,
  float = false,
  label,
}: {
  headers: string[];
  /** Row number of the header row; omit to show headers without an index. */
  headerRow?: number;
  rows: SheetRow[];
  /** Index of the first visible column (0 = A). */
  firstColumn?: number;
  title?: string;
  formula?: { ref: string; value: string };
  tabs?: string[];
  activeTab?: string;
  showLetters?: boolean;
  float?: boolean;
  label: string;
}) {
  return (
    <figure className={`${s.frame} ${float ? s.float : ""}`} style={{ margin: 0 }} data-theme="light">
      {title && (
        <div className={s.titleBar}>
          <span className={s.lights} aria-hidden="true"><i /><i /><i /></span>
          <span>{title}</span>
        </div>
      )}
      {formula && (
        <div className={s.formula} aria-hidden="true">
          <b>fx</b>
          <span>{formula.ref} {formula.value}</span>
        </div>
      )}
      <div className={s.scroll}>
        <table className={s.grid} aria-label={label}>
          {showLetters && (
            <thead className={s.letters} aria-hidden="true">
              <tr>
                <th className={s.corner} />
                {headers.map((_, i) => <th key={i}>{letter(firstColumn + i)}</th>)}
              </tr>
            </thead>
          )}
          <tbody>
            <tr>
              {showLetters && <td className={s.idx} aria-hidden="true">{headerRow ?? ""}</td>}
              {headers.map((h, i) => <th key={i} scope="col" className={s.header}>{h}</th>)}
            </tr>
            {rows.map((r) => (
              <tr key={r.n}>
                {showLetters && <th scope="row" className={s.idx}>{r.n}</th>}
                {r.cells.map((c, i) => {
                  const cell = typeof c === "string" ? { v: c } : c;
                  const cls = [s.cell, looksNumeric(cell.v) && s.num, cell.state && s[cell.state], cell.selected && s.selected].filter(Boolean).join(" ");
                  if (cell.note) {
                    return (
                      <td key={i} className={`${cls} ${s.flagged}`}>
                        <Tooltip content={cell.note}>
                          <span tabIndex={0} aria-label={`${cell.v || "empty"}: ${cell.note}`}>{cell.v || " "}</span>
                        </Tooltip>
                      </td>
                    );
                  }
                  return <td key={i} className={cls}>{cell.v}</td>;
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {tabs && (
        <div className={s.tabs} aria-label="Sheets">
          {tabs.map((t) => (
            <span key={t} className={`${s.tab} ${t === (activeTab ?? tabs[0]) ? s.tabActive : ""}`} aria-current={t === (activeTab ?? tabs[0]) || undefined}>
              {t}
            </span>
          ))}
        </div>
      )}
    </figure>
  );
}
