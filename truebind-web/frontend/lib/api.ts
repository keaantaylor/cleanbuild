import type { Alert, AuditLogEntry, DuplicatePair, ExceptionRow, ExceptionSummary, ExcludedRow, Me, MappingField, Obligation, Report, ReportSummary, Sheet, SheetMapping, Template } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

// The session lives in an HttpOnly cookie the browser sends automatically
// (credentials: "include"); JavaScript never sees it. Unsafe requests must
// echo the session's CSRF token, which /auth/login and /auth/me return.
let csrfToken: string | null = null;
function setCsrf(token: string | null) {
  csrfToken = token;
  try {
    if (token) sessionStorage.setItem("tb_csrf", token);
    else sessionStorage.removeItem("tb_csrf");
  } catch {
    // storage unavailable (private mode); the in-memory copy still works
  }
}
function getCsrf(): string | null {
  if (csrfToken) return csrfToken;
  try {
    csrfToken = sessionStorage.getItem("tb_csrf");
  } catch {
    csrfToken = null;
  }
  return csrfToken;
}

const DEFAULT_TIMEOUT_MS = 30_000;
const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

async function request<T>(path: string, init?: RequestInit & { timeoutMs?: number }): Promise<T> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, ...rest } = init ?? {};
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const method = (rest.method || "GET").toUpperCase();
  const headers: Record<string, string> = rest.body instanceof FormData ? {} : { "Content-Type": "application/json" };
  const token = getCsrf();
  if (UNSAFE.has(method) && token) headers["X-CSRF-Token"] = token;

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...rest,
      credentials: "include",
      signal: controller.signal,
      headers: { ...headers, ...(rest.headers as Record<string, string> | undefined) },
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(0, `Request timed out after ${Math.round(timeoutMs / 1000)}s — the server may be overloaded or unreachable.`);
    }
    throw new ApiError(0, err instanceof Error ? err.message : "Network error — could not reach the server.");
  } finally {
    clearTimeout(timer);
  }

  if (res.status === 401 && typeof window !== "undefined" && !path.startsWith("/auth/")) {
    setCsrf(null);
    window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`;
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : detail;
    } catch {
      // not JSON
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

type Page<T> = { items: T[]; total: number; limit: number; offset: number };
const items = <T,>(p: Promise<Page<T>>) => p.then((r) => r.items);

function qs(params: Record<string, string | number | boolean | undefined>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "") q.set(k, String(v));
  const s = q.toString();
  return s ? `?${s}` : "";
}

/** Poll a report until its status is no longer QUEUED/INGESTING/PROCESSING. */
export const IN_PROGRESS = new Set(["UPLOADED", "QUEUED", "INGESTING", "PROCESSING"]);
async function waitForReport(reportId: string, onUpdate?: (r: Report) => void, timeoutMs = 30 * 60_000): Promise<Report> {
  const deadline = Date.now() + timeoutMs;
  let delay = 500;
  for (;;) {
    const r = await request<Report>(`/reports/${reportId}`);
    onUpdate?.(r);
    if (!IN_PROGRESS.has(r.status)) return r;
    if (Date.now() > deadline) throw new ApiError(0, "Still processing after 30 minutes. Check back later.");
    await new Promise((res) => setTimeout(res, delay));
    delay = Math.min(delay * 1.5, 3000);
  }
}

export const api = {
  // ---- auth
  login: async (email: string, password: string) => {
    const me = await request<Me>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
    setCsrf(me.csrf_token);
    return me;
  },
  signup: async (body: { email: string; password: string; display_name: string; organisation: string }) => {
    const me = await request<Me>("/auth/signup", { method: "POST", body: JSON.stringify(body) });
    setCsrf(me.csrf_token);
    return me;
  },
  me: async () => {
    const me = await request<Me>("/auth/me");
    setCsrf(me.csrf_token);
    return me;
  },
  logout: async () => {
    try {
      await request<void>("/auth/logout", { method: "POST" });
    } finally {
      setCsrf(null);
    }
  },

  // ---- reports & jobs
  uploadReport: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<Report>("/reports/upload", { method: "POST", body: form, timeoutMs: 300_000 });
  },
  waitForReport,
  listReports: () => items(request<Page<Report>>("/reports?limit=200")),
  getReport: (reportId: string) => request<Report>(`/reports/${reportId}`),
  getReportSummary: async (reportId: string): Promise<ReportSummary | null> => {
    const r = await request<{ report: Report; summary: Omit<ReportSummary, "report"> | null }>(`/reports/${reportId}/summary`);
    return r.summary ? { ...r.summary, report: r.report } : null;
  },
  deleteReport: (reportId: string) => request<void>(`/reports/${reportId}`, { method: "DELETE" }),
  cancelReport: (reportId: string) => request<Report>(`/reports/${reportId}/cancel`, { method: "POST" }),
  retryReport: (reportId: string) => request<Report>(`/reports/${reportId}/retry`, { method: "POST" }),

  // ---- sheets & mapping (sheets are addressed by id, never by name)
  listSheets: (reportId: string) => request<Sheet[]>(`/reports/${reportId}/sheets`),
  getSheetMappingFull: (reportId: string, sheetId: string) =>
    request<SheetMapping>(`/reports/${reportId}/sheets/${sheetId}/mapping`),
  getSheetMapping: (reportId: string, sheetId: string) =>
    request<SheetMapping>(`/reports/${reportId}/sheets/${sheetId}/mapping`).then((m) => m.fields as MappingField[]),
  confirmSheetMapping: (reportId: string, sheetId: string, mappings: Record<string, string | null>) =>
    request<Sheet>(`/reports/${reportId}/sheets/${sheetId}/mapping`, { method: "POST", body: JSON.stringify({ mappings }) }),
  processReport: (reportId: string) => request<Report>(`/reports/${reportId}/process`, { method: "POST" }),

  // ---- findings
  getExceptionSummary: (reportId: string) =>
    request<ExceptionSummary | undefined>(`/reports/${reportId}/exceptions/summary`).then((s) => s ?? null),
  generateExceptionSummary: (reportId: string) =>
    request<ExceptionSummary>(`/reports/${reportId}/exceptions/summary`, { method: "POST" }),
  listExceptions: (reportId: string, checkType?: string, status?: string) =>
    items(request<Page<ExceptionRow>>(`/reports/${reportId}/exceptions${qs({ check_type: checkType, status, limit: 1000 })}`)),
  listExceptionsPage: (reportId: string, params: { checkType?: string; status?: string; limit?: number; offset?: number }) =>
    request<Page<ExceptionRow>>(`/reports/${reportId}/exceptions${qs({ check_type: params.checkType, status: params.status, limit: params.limit ?? 200, offset: params.offset ?? 0 })}`),
  listExcludedRows: (reportId: string) => items(request<Page<ExcludedRow>>(`/reports/${reportId}/excluded-rows?limit=1000`)),
  listDuplicates: (reportId: string) => items(request<Page<DuplicatePair>>(`/reports/${reportId}/duplicates?limit=1000`)),
  reviewDuplicate: (reportId: string, validationResultId: string, reviewStatus: string) =>
    request<DuplicatePair>(`/reports/${reportId}/duplicates/${validationResultId}/review`, {
      method: "PATCH",
      body: JSON.stringify({ review_status: reviewStatus }),
    }),

  // ---- obligations / alerts / audit / templates
  listObligations: (params: { reportId?: string; status?: string } = {}) =>
    items(request<Page<Obligation>>(`/obligations${qs({ report_id: params.reportId, status: params.status, limit: 1000 })}`)),
  createObligation: (reportId: string, body: { claim_row_id?: string; owner?: string | null; deadline?: string | null; note?: string | null }) =>
    request<Obligation>(`/reports/${reportId}/obligations`, { method: "POST", body: JSON.stringify(body) }),
  updateObligation: (obligationId: string, body: { owner?: string | null; deadline?: string | null; status?: string; note?: string | null }) =>
    request<Obligation>(`/obligations/${obligationId}`, { method: "PATCH", body: JSON.stringify(body) }),
  listAlerts: (params: { reportId?: string; acknowledged?: boolean } = {}) =>
    items(request<Page<Alert>>(`/alerts${qs({ report_id: params.reportId, acknowledged: params.acknowledged, limit: 1000 })}`)),
  acknowledgeAlert: (alertId: string) => request<Alert>(`/alerts/${alertId}/acknowledge`, { method: "POST" }),
  getAuditLog: (reportId: string, params: { actionType?: string; actor?: string } = {}) =>
    items(request<Page<AuditLogEntry>>(`/reports/${reportId}/audit${qs({ action_type: params.actionType, limit: 1000 })}`))
      .then((list) => (params.actor ? list.filter((e) => e.actor.includes(params.actor!)) : list)),
  listTemplates: () => request<Template[]>("/templates"),

  // ---- exports (plain GET links; the session cookie authenticates them)
  exportClaimsUrl: (reportId: string) => `${API_BASE}/reports/${reportId}/export/claims.csv`,
  exportExceptionsUrl: (reportId: string) => `${API_BASE}/reports/${reportId}/export/exceptions.csv`,
  exportAuditCsvUrl: (reportId: string) => `${API_BASE}/reports/${reportId}/export/audit.csv`,
  exportByStatusUrl: (reportId: string) => `${API_BASE}/reports/${reportId}/export/claims.csv`,
};
