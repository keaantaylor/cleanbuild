"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { CaretDown } from "@phosphor-icons/react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import type { Report } from "@/lib/types";
import { Popover } from "./ui";
import { FileGlyph } from "./intake";

/** Selected completed report, kept in ?reportId= so views are linkable and
 * survive reloads. Defaults to the most recent completed report. */
export function useSelectedReport(): { reportId: string | null; report: Report | null; reports: Report[]; loading: boolean; error: string | null; reload: () => void; select: (id: string) => void } {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const { data, loading, error, reload } = useApi(() => api.listReports(), []);
  const complete = (data ?? []).filter((r) => r.status === "COMPLETE");
  const fromUrl = params.get("reportId");
  const reportId = fromUrl && complete.some((r) => r.id === fromUrl) ? fromUrl : complete[0]?.id ?? null;
  useEffect(() => {
    if (!fromUrl && reportId) {
      const q = new URLSearchParams(params.toString());
      q.set("reportId", reportId);
      router.replace(`${pathname}?${q.toString()}`);
    }
  }, [fromUrl, reportId, params, pathname, router]);
  const select = (id: string) => {
    const q = new URLSearchParams(params.toString());
    q.set("reportId", id);
    router.replace(`${pathname}?${q.toString()}`);
  };
  return { reportId, report: complete.find((r) => r.id === reportId) ?? null, reports: complete, loading: loading && !data, error: data ? null : error, reload, select };
}

/** The prototype's file picker: a pill button with a popover list of completed reports. */
export function ReportPicker({ report, reports, onSelect }: { report: Report | null; reports: Report[]; onSelect: (id: string) => void }) {
  const [open, setOpen] = useState(false);
  if (!report) return null;
  return (
    <div className="relative">
      <button type="button" onClick={() => setOpen((v) => !v)} className="tb-btn max-w-[360px] !text-[13px]" aria-haspopup="listbox" aria-expanded={open}>
        <FileGlyph name={report.file_name} size={16} />
        <span className="truncate">{report.file_name}</span>
        <span className="flex-none" style={{ color: "var(--faint)" }}>· {new Date(report.created_at).toLocaleDateString("en-IE", { day: "numeric", month: "short" })}</span>
        <CaretDown style={{ color: "var(--faint)" }} />
      </button>
      {open && (
        <Popover onClose={() => setOpen(false)} width={380} align="left">
          <div className="max-h-[360px] overflow-y-auto" role="listbox" aria-label="Report">
            {reports.map((r) => (
              <button
                key={r.id}
                type="button"
                role="option"
                aria-selected={r.id === report.id}
                className="flex w-full cursor-pointer flex-col px-3.5 py-2.5 text-left text-[13px] hover:bg-[var(--accentTint)]"
                style={{ boxShadow: "0 1px 0 var(--line)", background: r.id === report.id ? "var(--accentTint)" : undefined }}
                onClick={() => {
                  setOpen(false);
                  onSelect(r.id);
                }}
              >
                <span className="truncate font-medium">{r.file_name}</span>
                <span className="text-[12px]" style={{ color: "var(--faint)" }}>
                  {r.sender ? `${r.sender} · ` : ""}
                  {new Date(r.created_at).toLocaleDateString("en-IE", { day: "numeric", month: "short", year: "numeric" })} · {r.issues_found ?? 0} findings
                </span>
              </button>
            ))}
          </div>
        </Popover>
      )}
    </div>
  );
}
