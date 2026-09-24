"use client";

import { useEffect } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import type { Report } from "@/lib/types";
import { ds } from "@/components/ds";

/** Selected completed report, kept in ?reportId= so views are linkable and
 * survive reloads. Defaults to the most recent completed report. */
export function useSelectedReport(): { reportId: string | null; reports: Report[]; loading: boolean; select: (id: string) => void } {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const { data, loading } = useApi(() => api.listReports(), []);
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
  return { reportId, reports: complete, loading, select };
}

export function ReportSelect({ reportId, reports, onSelect }: { reportId: string | null; reports: Report[]; onSelect: (id: string) => void }) {
  return (
    <label style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
      <span className={ds.muted}>Report</span>
      <select className={ds.select} value={reportId ?? ""} onChange={(e) => onSelect(e.target.value)} style={{ maxWidth: 360 }}>
        {reports.map((r) => <option key={r.id} value={r.id}>{r.file_name} · {new Date(r.created_at).toLocaleDateString("en-GB")}</option>)}
      </select>
    </label>
  );
}
