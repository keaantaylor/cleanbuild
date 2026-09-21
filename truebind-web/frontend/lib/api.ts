import type { Alert, AuditLogEntry, DuplicatePair, ExceptionRow, ExcludedRow, MappingField, Obligation, Report, ReportSummary, Sheet, Template } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: init?.body instanceof FormData ? init.headers : { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // response wasn't JSON; fall back to statusText
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("text/csv")) {
    return (await res.text()) as unknown as T;
  }
  return res.json() as Promise<T>;
}

export const api = {
  uploadReport: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<Report>("/reports/upload", { method: "POST", body: form });
  },
  listReports: () => request<Report[]>("/reports"),
  getReport: (reportId: string) => request<Report>(`/reports/${reportId}`),
  getReportSummary: (reportId: string) => request<ReportSummary>(`/reports/${reportId}/summary`),
  deleteReport: (reportId: string) => request<void>(`/reports/${reportId}`, { method: "DELETE" }),

  listSheets: (reportId: string) => request<Sheet[]>(`/reports/${reportId}/sheets`),
  getSheetHeaders: (reportId: string, sheetName: string) =>
    request<string[]>(`/reports/${reportId}/sheets/${encodeURIComponent(sheetName)}/headers`),
  getSheetMapping: (reportId: string, sheetName: string) =>
    request<MappingField[]>(`/reports/${reportId}/sheets/${encodeURIComponent(sheetName)}/mapping`),
  confirmSheetMapping: (reportId: string, sheetName: string, mappings: Record<string, string | null>) =>
    request<Sheet>(`/reports/${reportId}/sheets/${encodeURIComponent(sheetName)}/mapping/confirm`, {
      method: "POST",
      body: JSON.stringify({ mappings }),
    }),
  processReport: (reportId: string) => request<Report>(`/reports/${reportId}/process`, { method: "POST" }),

  listExceptions: (reportId: string, checkType?: string, status?: string) => {
    const q = new URLSearchParams();
    if (checkType) q.set("check_type", checkType);
    if (status) q.set("status", status);
    const qs = q.toString();
    return request<ExceptionRow[]>(`/reports/${reportId}/exceptions${qs ? `?${qs}` : ""}`);
  },
  listExcludedRows: (reportId: string) => request<ExcludedRow[]>(`/reports/${reportId}/excluded-rows`),
  listDuplicates: (reportId: string) => request<DuplicatePair[]>(`/reports/${reportId}/duplicates`),
  reviewDuplicate: (reportId: string, validationResultId: string, reviewStatus: string) =>
    request<DuplicatePair>(`/reports/${reportId}/duplicates/${validationResultId}/review`, {
      method: "PATCH",
      body: JSON.stringify({ review_status: reviewStatus }),
    }),

  listObligations: (params: { reportId?: string; status?: string } = {}) => {
    const q = new URLSearchParams();
    if (params.reportId) q.set("report_id", params.reportId);
    if (params.status) q.set("status", params.status);
    const qs = q.toString();
    return request<Obligation[]>(`/obligations${qs ? `?${qs}` : ""}`);
  },
  createObligation: (reportId: string, body: Partial<Obligation> & { claim_row_id?: string }) =>
    request<Obligation>(`/reports/${reportId}/obligations`, { method: "POST", body: JSON.stringify(body) }),
  updateObligation: (obligationId: string, body: Partial<Obligation>) =>
    request<Obligation>(`/obligations/${obligationId}`, { method: "PATCH", body: JSON.stringify(body) }),

  listAlerts: (params: { reportId?: string; acknowledged?: boolean } = {}) => {
    const q = new URLSearchParams();
    if (params.reportId) q.set("report_id", params.reportId);
    if (params.acknowledged !== undefined) q.set("acknowledged", String(params.acknowledged));
    const qs = q.toString();
    return request<Alert[]>(`/alerts${qs ? `?${qs}` : ""}`);
  },
  acknowledgeAlert: (alertId: string) => request<Alert>(`/alerts/${alertId}`, { method: "PATCH" }),

  getAuditLog: (reportId: string, params: { actionType?: string; actor?: string } = {}) => {
    const q = new URLSearchParams();
    if (params.actionType) q.set("action_type", params.actionType);
    if (params.actor) q.set("actor", params.actor);
    const qs = q.toString();
    return request<AuditLogEntry[]>(`/reports/${reportId}/audit${qs ? `?${qs}` : ""}`);
  },

  listTemplates: () => request<Template[]>("/templates"),

  exportAuditCsvUrl: (reportId: string) => `${API_BASE}/reports/${reportId}/export/audit-csv`,
  exportByStatusUrl: (reportId: string) => `${API_BASE}/reports/${reportId}/export/by-status`,
};
