import type { Alert, AuditLogEntry, Billing, Binder, Preflight, SanctionsList, Scorecard, Submission, BinderInput, Disposition, ModuleFinding, ModuleRun, Channels, ClaimRow, Delivery, DuplicatePair, ExceptionRow, ExceptionSummary, ExcludedRow, Invitation, InvitationCreated, Job, Me, MappingField, MonthOnMonth, QueryLetter, Member, MfaChallenge, MfaStatus, Obligation, OrgSettings, Overview, Report, ReportSummary, Role, Sheet, SheetMapping, SftpDestination, SftpInput, SsoConfig, SsoConfigInput, SystemStatus, Template, WebhookDelivery, WebhookEndpoint, WebhookEvent, WorkQueue } from "./types";

// Default: same hostname as the page, port 8000. Using the page's own host
// matters: a page on localhost calling an API on 127.0.0.1 is cross-site, so
// the session cookie would not be sent and every request would bounce to login.
function defaultApiBase(): string {
  if (typeof window !== "undefined") return `${window.location.protocol}//${window.location.hostname}:8000/api/v1`;
  return "http://localhost:8000/api/v1";
}
export const API_BASE = process.env.NEXT_PUBLIC_API_URL || defaultApiBase();

export function isMfaChallenge(r: Me | MfaChallenge): r is MfaChallenge {
  return (r as MfaChallenge).mfa_required === true;
}

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
  // A non-secret hint (never the session itself) so public pages such as
  // onboarding only ask /auth/me when someone may be signed in, instead of
  // logging a 401 for every visitor.
  if (typeof document !== "undefined") document.cookie = token ? "tb_hint=1; path=/; samesite=lax" : "tb_hint=; path=/; max-age=0; samesite=lax";
}

/** True when this browser may hold a signed-in session (see setCsrf). */
export function mayHaveSession(): boolean {
  if (typeof document === "undefined") return false;
  return /(?:^|; )tb_hint=1/.test(document.cookie) || getCsrf() !== null;
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
  if (res.status === 403 && res.headers.get("X-TrueBind-Reason") === "mfa_setup_required" && typeof window !== "undefined"
      && !window.location.pathname.startsWith("/settings")) {
    // The organisation requires 2FA and this session has not set it up yet.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.href = "/settings?tab=security&required=1";
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
  /** Either a session (Me) or, when 2FA is on, a challenge to complete with verifyMfa. */
  login: async (email: string, password: string): Promise<Me | MfaChallenge> => {
    const res = await request<Me | MfaChallenge>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
    if (!isMfaChallenge(res)) setCsrf(res.csrf_token);
    return res;
  },
  verifyMfa: async (mfaToken: string, factor: { code: string } | { recovery_code: string }) => {
    const me = await request<Me>("/auth/2fa/verify", { method: "POST", body: JSON.stringify({ mfa_token: mfaToken, ...factor }) });
    setCsrf(me.csrf_token);
    return me;
  },
  acceptInvitation: async (token: string, displayName: string, password: string) => {
    const me = await request<Me>("/auth/invitations/accept", { method: "POST", body: JSON.stringify({ token, display_name: displayName, password }) });
    setCsrf(me.csrf_token);
    return me;
  },
  /** Full-page navigation: the IdP flow is a browser redirect, not a fetch. */
  ssoStartUrl: (email: string) => `${API_BASE}/auth/sso/start?email=${encodeURIComponent(email)}`,
  mfaStatus: () => request<MfaStatus>("/auth/2fa"),
  mfaSetup: () => request<{ secret: string; otpauth_uri: string }>("/auth/2fa/setup", { method: "POST" }),
  mfaEnable: (code: string) => request<{ recovery_codes: string[] }>("/auth/2fa/enable", { method: "POST", body: JSON.stringify({ code }) }),
  mfaDisable: (code: string) => request<void>("/auth/2fa/disable", { method: "POST", body: JSON.stringify({ code }) }),

  // ---- organisation
  getOrg: () => request<OrgSettings>("/org"),
  updateOrg: (body: Partial<Pick<OrgSettings, "name" | "org_type" | "require_2fa" | "retention_days" | "anonymise_names">>) =>
    request<OrgSettings>("/org", { method: "PATCH", body: JSON.stringify(body) }),
  listMembers: () => request<Member[]>("/org/members"),
  changeRole: (membershipId: string, role: Role) =>
    request<Member>(`/org/members/${membershipId}`, { method: "PATCH", body: JSON.stringify({ role }) }),
  removeMember: (membershipId: string) => request<void>(`/org/members/${membershipId}`, { method: "DELETE" }),
  listInvitations: () => request<Invitation[]>("/org/invitations"),
  invite: (email: string, role: Role) =>
    request<InvitationCreated>("/org/invitations", { method: "POST", body: JSON.stringify({ email, role }) }),
  revokeInvitation: (id: string) => request<void>(`/org/invitations/${id}`, { method: "DELETE" }),
  getSso: () => request<SsoConfig>("/org/sso"),
  saveSso: (body: SsoConfigInput) => request<SsoConfig>("/org/sso", { method: "PATCH", body: JSON.stringify(body) }),
  removeSso: () => request<void>("/org/sso", { method: "DELETE" }),
  getInbound: () => request<{ address: string | null; configured: boolean }>("/org/inbound"),
  rotateInbound: () => request<{ address: string | null; configured: boolean }>("/org/inbound/rotate", { method: "POST" }),
  listWebhooks: () => request<WebhookEndpoint[]>("/org/webhooks"),
  createWebhook: (url: string, events: WebhookEvent[]) =>
    request<WebhookEndpoint & { secret: string }>("/org/webhooks", { method: "POST", body: JSON.stringify({ url, events }) }),
  deleteWebhook: (id: string) => request<void>(`/org/webhooks/${id}`, { method: "DELETE" }),
  testWebhook: (id: string) => request<WebhookDelivery>(`/org/webhooks/${id}/test`, { method: "POST" }),
  webhookDeliveries: (id: string) => request<WebhookDelivery[]>(`/org/webhooks/${id}/deliveries`),
  replayWebhook: (deliveryId: string) => request<WebhookDelivery>(`/org/webhooks/deliveries/${deliveryId}/replay`, { method: "POST" }),
  getSftp: () => request<SftpDestination | null>("/org/sftp"),
  saveSftp: (body: SftpInput) => request<SftpDestination>("/org/sftp", { method: "PUT", body: JSON.stringify(body) }),
  removeSftp: () => request<void>("/org/sftp", { method: "DELETE" }),
  testSftp: () => request<{ ok: boolean; message: string }>("/org/sftp/test", { method: "POST" }),
  refreshFx: () => request<{ rows_written: number; latest_rate_date: string | null }>("/fx/refresh", { method: "POST" }),
  signup: async (body: { email: string; password: string; display_name: string; organisation: string }) => {
    const me = await request<Me>("/auth/signup", { method: "POST", body: JSON.stringify(body) });
    setCsrf(me.csrf_token);
    return me;
  },
  me: async () => {
    try {
      const me = await request<Me>("/auth/me");
      setCsrf(me.csrf_token);
      return me;
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) setCsrf(null);
      throw e;
    }
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
  includeSheet: (reportId: string, sheetId: string) =>
    request<Sheet>(`/reports/${reportId}/sheets/${sheetId}/include`, { method: "POST" }),
  skipSheet: (reportId: string, sheetId: string) =>
    request<Sheet>(`/reports/${reportId}/sheets/${sheetId}/skip`, { method: "POST" }),
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

  // ---- check modules and binders (P3+)
  listChecks: (reportId: string) => request<ModuleRun[]>(`/reports/${reportId}/checks`),
  runCheck: (reportId: string, module: string) =>
    request<ModuleRun>(`/reports/${reportId}/checks/${encodeURIComponent(module)}/run`, { method: "POST" }),
  listModuleFindings: (reportId: string, params: { module?: string; status?: string; disposition?: string; limit?: number; offset?: number } = {}) =>
    request<Page<ModuleFinding>>(`/reports/${reportId}/checks/findings${qs(params)}`),
  disposeFinding: (reportId: string, findingId: string, disposition: Disposition, note?: string) =>
    request<ModuleFinding>(`/reports/${reportId}/checks/findings/${findingId}`, { method: "PATCH", body: JSON.stringify({ disposition, note: note || null }) }),
  assignBinder: (reportId: string, binderId: string | null) =>
    request<ModuleRun[]>(`/reports/${reportId}/binder`, { method: "PUT", body: JSON.stringify({ binder_id: binderId }) }),
  listBinders: () => request<Binder[]>("/binders"),
  createBinder: (body: BinderInput) => request<Binder>("/binders", { method: "POST", body: JSON.stringify(body) }),
  deleteBinder: (id: string) => request<void>(`/binders/${id}`, { method: "DELETE" }),
  getBilling: () => request<Billing>("/billing"),
  billingCheckout: (plan: string) => request<{ url: string }>("/billing/checkout", { method: "POST", body: JSON.stringify({ plan }) }),
  billingPortal: () => request<{ url: string }>("/billing/portal", { method: "POST" }),
  senderPreflight: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<Preflight>("/sender/preflight", { method: "POST", body: form, timeoutMs: 300_000 });
  },
  senderSubmit: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<Submission>("/sender/submissions", { method: "POST", body: form, timeoutMs: 300_000 });
  },
  senderSubmissions: () => request<Submission[]>("/sender/submissions"),
  getScorecard: (since?: string) => request<Scorecard>(`/scorecard${qs({ since })}`),
  listSanctionsLists: () => request<SanctionsList[]>("/sanctions/lists"),
  loadSanctionsList: (name: string, file: File) => {
    const form = new FormData();
    form.append("name", name);
    form.append("file", file);
    return request<SanctionsList>("/sanctions/lists", { method: "POST", body: form, timeoutMs: 300_000 });
  },
  deleteSanctionsList: (id: string) => request<void>(`/sanctions/lists/${id}`, { method: "DELETE" }),

  // ---- exports (plain GET links; the session cookie authenticates them)
  exportClaimsUrl: (reportId: string) => `${API_BASE}/reports/${reportId}/export/claims.csv`,
  exportExceptionsUrl: (reportId: string) => `${API_BASE}/reports/${reportId}/export/exceptions.csv`,
  auditPackUrl: (reportId: string) => `${API_BASE}/reports/${reportId}/audit-pack.zip`,
  annotatedWorkbookUrl: (reportId: string) => `${API_BASE}/reports/${reportId}/export/annotated.xlsx`,
  correctedWorkbookUrl: (reportId: string) => `${API_BASE}/reports/${reportId}/export/corrected.xlsx`,
  queryLetter: (reportId: string) => request<QueryLetter>(`/reports/${reportId}/query-letter`),
  compareReports: (reportId: string, previousId: string, pct: number, min: number) =>
    request<MonthOnMonth>(`/reports/${reportId}/compare${qs({ previous_report_id: previousId, reserve_jump_pct: pct, reserve_jump_min: min })}`),
  exportAuditCsvUrl: (reportId: string) => `${API_BASE}/reports/${reportId}/export/audit.csv`,
  exportByStatusUrl: (reportId: string) => `${API_BASE}/reports/${reportId}/export/claims.csv`,
};
