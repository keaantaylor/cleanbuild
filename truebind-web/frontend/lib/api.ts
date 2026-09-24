import type { Alert, AuditLogEntry, Channels, ClaimRow, Delivery, DuplicatePair, ExceptionRow, ExceptionSummary, ExcludedRow, Job, Me, MappingField, Obligation, Overview, Report, ReportSummary, Sheet, SheetMapping, SystemStatus, Template, WorkQueue } from "./types";

// Default: same hostname as the page, port 8000. Using the page's own host
// matters: a page on localhost calling an API on 127.0.0.1 is cross-site, so
// the session cookie would not be sent and every request would bounce to login.
function defaultApiBase(): string {
  if (typeof window !== "undefined") return `${window.location.protocol}//${window.location.hostname}:8000/api/v1`;
  return "http://localhost:8000/api/v1";
}
export const API_BASE = process.env.NEXT_PUBLIC_API_URL || defaultApiBase();

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
    // Full navigation on purpose: drops every in-memory cache of the expired session.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
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

  listClaimsByRef: (reportId: string, ref: string) =>
    items(request<Page<ClaimRow>>(`/reports/${reportId}/claims${qs({ q: ref, limit: 200 })}`))
      .then((rows) => rows.filter((r) => r.claim_reference === ref)),

  // ---- operations
  systemStatus: () => request<SystemStatus>("/system/status"),
  overview: () => request<Overview>("/overview"),
  workQueue: () => request<WorkQueue>("/work-queue"),
  channels: () => request<Channels>("/channels"),
  countUnreadAlerts: () => request<Page<Alert>>("/alerts?acknowledged=false&limit=1").then((p) => p.total),
  listAlertsPage: (params: { acknowledged?: boolean; limit?: number; offset?: number } = {}) =>
    request<Page<Alert>>(`/alerts${qs({ acknowledged: params.acknowledged, limit: params.limit ?? 100, offset: params.offset ?? 0 })}`),
  reportJobs: (reportId: string) => request<Job[]>(`/reports/${reportId}/jobs`),
  listDeliveries: (limit = 200) => request<Page<Delivery>>(`/deliveries?limit=${limit}`),
  sendDelivery: (reportId: string, kind: string, recipient: string) =>
    request<Delivery>(`/reports/${reportId}/deliveries`, { method: "POST", body: JSON.stringify({ kind, channel: "email", recipient }) }),
  reviewException: (reportId: string, validationResultId: string, body: { review_status: string; assignee?: string | null; note?: string | null }) =>
    request<{ review_status: string }>(`/reports/${reportId}/exceptions/${validationResultId}`, { method: "PATCH", body: JSON.stringify(body) }),
  searchExceptions: (reportId: string, p: { checkType?: string; status?: string; severity?: string; q?: string; sort?: string; limit?: number; offset?: number }) =>
    request<Page<ExceptionRow>>(`/reports/${reportId}/exceptions${qs({ check_type: p.checkType, status: p.status, severity: p.severity, q: p.q, sort: p.sort, limit: p.limit ?? 100, offset: p.offset ?? 0 })}`),
  tenantAudit: (limit = 200) => items(request<Page<AuditLogEntry>>(`/audit?limit=${limit}`)),
  verifyAudit: () => request<{ intact: boolean; entries: number; first_bad_seq: number | null }>("/audit/verify"),
  /** Upload with REAL byte-level progress (XHR upload events). */
  uploadWithProgress: (file: File, meta: { sender?: string; programme?: string }, onProgress: (sent: number, total: number) => void) =>
    new Promise<Report>((resolve, reject) => {
      const form = new FormData();
      form.append("file", file);
      if (meta.sender) form.append("sender", meta.sender);
      if (meta.programme) form.append("programme", meta.programme);
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${API_BASE}/reports/upload`);
      xhr.withCredentials = true;
      const token = getCsrf();
      if (token) xhr.setRequestHeader("X-CSRF-Token", token);
      xhr.timeout = 300_000;
      xhr.upload.onprogress = (e) => { if (e.lengthComputable) onProgress(e.loaded, e.total); };
      xhr.onload = () => {
        let body: { detail?: unknown } | Report | null = null;
        try { body = JSON.parse(xhr.responseText); } catch { body = null; }
        if (xhr.status >= 200 && xhr.status < 300 && body) resolve(body as Report);
        // eslint-disable-next-line @next/next/no-location-assign-relative-destination
        else if (xhr.status === 401) { window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`); reject(new ApiError(401, "Please sign in again.")); }
        else reject(new ApiError(xhr.status, typeof (body as { detail?: unknown })?.detail === "string" ? (body as { detail: string }).detail : `Upload failed (${xhr.status}).`));
      };
      xhr.onerror = () => reject(new ApiError(0, "Network error — the upload could not reach the server."));
      xhr.ontimeout = () => reject(new ApiError(0, "The upload timed out."));
      xhr.send(form);
    }),
  uploadWithMeta: (file: File, meta: { sender?: string; programme?: string }) => {
    const form = new FormData();
    form.append("file", file);
    if (meta.sender) form.append("sender", meta.sender);
    if (meta.programme) form.append("programme", meta.programme);
    return request<Report>("/reports/upload", { method: "POST", body: form, timeoutMs: 300_000 });
  },

  // ---- exports (plain GET links; the session cookie authenticates them)
  exportClaimsUrl: (reportId: string) => `${API_BASE}/reports/${reportId}/export/claims.csv`,
  exportExceptionsUrl: (reportId: string) => `${API_BASE}/reports/${reportId}/export/exceptions.csv`,
  exportAuditCsvUrl: (reportId: string) => `${API_BASE}/reports/${reportId}/export/audit.csv`,
  exportByStatusUrl: (reportId: string) => `${API_BASE}/reports/${reportId}/export/claims.csv`,
};
