"use client";

import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { MappingField, Report, Sheet, SheetMapping } from "@/lib/types";
import { Button } from "@/components/ui/Button";
import { ErrorState, Icon, Panel, Pill, SkeletonRows, type Tone } from "@/components/ds";
import styles from "./intake.module.css";

const REVIEW: Record<string, { label: string; tone: Tone }> = {
  HIGH_CONFIDENCE: { label: "High confidence", tone: "good" },
  REVIEW: { label: "Check", tone: "warn" },
  AMBIGUOUS: { label: "Ambiguous", tone: "warn" },
  UNMAPPED: { label: "Not found", tone: "neutral" },
  CONFIRMED: { label: "Confirmed", tone: "brand" },
};
const METHOD: Record<string, string> = { MAPPED_BY_ALIAS: "alias", MAPPED_BY_AI: "AI", MANUAL: "manual", UNMAPPED: "" };

function sheetMark(s: Sheet): { icon: "check" | "alertCircle" | "x" | "layers"; tone: string; text: string } {
  if (s.status === "SKIPPED") return { icon: "x", tone: "var(--color-text-tertiary)", text: s.skip_reason ?? "skipped" };
  if (s.status === "CONFIRMED") return { icon: "check", tone: "var(--color-success)", text: "confirmed" };
  if (s.mapping_status === "unmapped" || s.mapping_status === "partial") return { icon: "alertCircle", tone: "var(--color-warning)", text: `${s.fields_mapped}/${s.fields_total} fields · needs attention` };
  return { icon: "layers", tone: "var(--color-primary)", text: `${s.fields_mapped}/${s.fields_total} fields${s.needs_review ? ` · ${s.needs_review} to check` : ""}` };
}

export function MappingReview({ report, sheets, onSheetsChange, onProcess }: {
  report: Report; sheets: Sheet[]; onSheetsChange: (s: Sheet[]) => void; onProcess: () => Promise<void>;
}) {
  const firstOpen = sheets.find((s) => s.status === "PENDING_CONFIRMATION") ?? sheets.find((s) => s.status !== "SKIPPED");
  const [active, setActive] = useState<string | null>(firstOpen?.id ?? null);
  const [mapping, setMapping] = useState<SheetMapping | null>(null);
  const [choices, setChoices] = useState<Record<string, string | null>>({});
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [actionErr, setActionErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    api.getSheetMappingFull(report.id, active)
      .then((m) => {
        if (cancelled) return;
        setMapping(m);
        setChoices(Object.fromEntries(m.fields.map((f) => [f.field_code, f.source_column])));
        setLoadErr(null);
      })
      .catch((e) => { if (!cancelled) setLoadErr(e instanceof ApiError ? e.message : "Could not load this sheet's mapping."); });
    return () => { cancelled = true; };
  }, [report.id, active]);

  const pending = sheets.filter((s) => s.status === "PENDING_CONFIRMATION");
  const allDone = sheets.length > 0 && pending.length === 0;
  const usedCols = useMemo(() => {
    const used: Record<string, string> = {};
    for (const [code, col] of Object.entries(choices)) if (col) used[col] = code;
    return used;
  }, [choices]);

  async function refreshSheets(nextActiveAfter?: string) {
    const list = await api.listSheets(report.id);
    onSheetsChange(list);
    const next = list.find((s) => s.status === "PENDING_CONFIRMATION" && s.id !== nextActiveAfter);
    setMapping(null);
    setActive(next?.id ?? null);
  }

  async function confirmActive() {
    if (!active) return;
    setBusy("confirm");
    setActionErr(null);
    try {
      await api.confirmSheetMapping(report.id, active, choices);
      await refreshSheets(active);
    } catch (e) {
      setActionErr(e instanceof ApiError ? e.message : "Could not confirm this sheet.");
    } finally {
      setBusy(null);
    }
  }

  async function confirmAllAsProposed() {
    setBusy("all");
    setActionErr(null);
    try {
      for (const s of pending) {
        const m = s.id === active && mapping ? { fields: mapping.fields } : await api.getSheetMappingFull(report.id, s.id);
        const proposed = s.id === active ? choices : Object.fromEntries(m.fields.map((f: MappingField) => [f.field_code, f.source_column]));
        await api.confirmSheetMapping(report.id, s.id, proposed);
      }
      await refreshSheets();
    } catch (e) {
      setActionErr(e instanceof ApiError ? e.message : "Could not confirm every sheet.");
      await refreshSheets().catch(() => {});
    } finally {
      setBusy(null);
    }
  }

  async function process() {
    setBusy("process");
    setActionErr(null);
    try {
      await onProcess();
    } catch (e) {
      setActionErr(e instanceof ApiError ? e.message : "Could not start processing.");
      setBusy(null);
    }
  }

  const activeSheet = sheets.find((s) => s.id === active);
  const toCheck = mapping?.fields.filter((f) => f.review_state === "REVIEW" || f.review_state === "AMBIGUOUS").length ?? 0;

  return (
    <div className={styles.review}>
      <Panel title="Sheets" icon="layers" subtitle={`${sheets.length - pending.length} of ${sheets.length} resolved`} flush>
        <ul className={styles.sheetList}>
          {sheets.map((s) => {
            const m = sheetMark(s);
            return (
              <li key={s.id}>
                <button type="button" className={`${styles.sheetBtn} ${s.id === active ? styles.sheetActive : ""}`}
                        disabled={s.status === "SKIPPED"} onClick={() => setActive(s.id)} aria-current={s.id === active ? "true" : undefined}>
                  <span className={styles.mark} style={{ color: m.tone }}><Icon name={m.icon} size={16} /></span>
                  <span>
                    <span className={styles.sheetName}>{s.sheet_name}</span>
                    <span className={styles.sheetMeta} style={{ display: "block" }}>{s.row_count ? `${s.row_count} rows · ` : ""}{m.text}</span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
        <div className={styles.bar}>
          {allDone ? (
            <Button onClick={process} loading={busy === "process"} style={{ width: "100%" }}>Produce health report</Button>
          ) : (
            <Button variant="secondary" onClick={confirmAllAsProposed} loading={busy === "all"} style={{ width: "100%" }}
                    title="Accept TrueBind's proposal for every remaining sheet">Confirm all as proposed ({pending.length})</Button>
          )}
        </div>
      </Panel>

      <Panel flush title={activeSheet ? activeSheet.sheet_name : allDone ? "All sheets resolved" : "Select a sheet"}
        subtitle={activeSheet ? `Header row ${(activeSheet.header_row_index ?? 0) + 1} · ${activeSheet.source_column_count} source columns${toCheck ? ` · ${toCheck} field(s) to check` : ""}` : undefined}>
        {actionErr && <div style={{ padding: "0 20px 12px" }}><ErrorState title="That didn't work" message={actionErr} /></div>}
        {!active ? (
          <div style={{ padding: 24 }}>
            <p style={{ margin: 0 }}>{allDone ? "Every sheet is mapped or skipped. Produce the health report to validate every row." : "Choose a sheet on the left."}</p>
          </div>
        ) : loadErr ? <div style={{ padding: 20 }}><ErrorState message={loadErr} /></div>
          : !mapping ? <div style={{ padding: 20 }}><SkeletonRows rows={8} /></div> : (
          <>
            <div style={{ overflowX: "auto" }}>
              <table className={styles.mapTable}>
                <thead><tr><th scope="col">Canonical field</th><th scope="col">Source column</th><th scope="col">Match</th><th scope="col">Sample values</th></tr></thead>
                <tbody>
                  {mapping.fields.map((f) => {
                    const r = REVIEW[f.review_state ?? "UNMAPPED"] ?? REVIEW.UNMAPPED;
                    const changed = (choices[f.field_code] ?? null) !== (f.source_column ?? null);
                    const conflict = choices[f.field_code] && usedCols[choices[f.field_code]!] !== f.field_code;
                    return (
                      <tr key={f.field_code}>
                        <td><div className={styles.fieldName}>{f.field_name}{f.required && <span className={styles.req} title="Required">*</span>}</div>
                          <div className={styles.fieldCode}>{f.field_code}</div></td>
                        <td>
                          <select className={`${styles.select} ${changed ? styles.changed : ""}`} aria-label={`Source column for ${f.field_name}`}
                                  value={choices[f.field_code] ?? ""} onChange={(e) => setChoices((p) => ({ ...p, [f.field_code]: e.target.value || null }))}>
                            <option value="">— not mapped —</option>
                            {mapping.headers.map((h) => (
                              <option key={h} value={h}>{h}{usedCols[h] && usedCols[h] !== f.field_code ? " (in use)" : ""}</option>
                            ))}
                          </select>
                          {conflict && <div className={styles.evidence} style={{ color: "var(--color-error)" }}>Also used by another field</div>}
                        </td>
                        <td>
                          {changed ? <Pill tone="brand">Your change</Pill> : <Pill tone={r.tone}>{r.label}</Pill>}
                          {!changed && f.source_column && (
                            <div className={styles.evidence}>
                              {METHOD[f.mapping_state] && <>{METHOD[f.mapping_state]}{f.confidence_score != null ? ` · ${Math.round(f.confidence_score <= 1 ? f.confidence_score * 100 : f.confidence_score)}%` : ""}</>}
                              {f.evidence ? ` · ${f.evidence}` : ""}
                            </div>
                          )}
                        </td>
                        <td className={styles.samples}>{f.sample_values.join(" · ") || "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className={`${styles.bar} ${styles.stickyBar}`}>
              <span className={styles.note}>Fields marked * are required. Unmapped source columns are kept on every row.</span>
              <Button onClick={confirmActive} loading={busy === "confirm"} disabled={activeSheet?.status === "SKIPPED"}>
                {activeSheet?.status === "CONFIRMED" ? "Save changes" : "Confirm sheet"}
              </Button>
            </div>
          </>
        )}
      </Panel>
    </div>
  );
}
