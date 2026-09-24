import type { AuditLogEntry } from "./types";
import type { IconName } from "@/components/ds/Icon";

type Described = { title: string; detail?: string; icon: IconName; tone: "neutral" | "good" | "warn" | "bad" | "info" };

const v = (o: Record<string, unknown> | null | undefined, k: string) => (o && o[k] != null ? String(o[k]) : "");

/** Plain-language rendering of an audit entry. Only restates what the entry
 * records; nothing is inferred. */
export function describeAudit(e: AuditLogEntry): Described {
  const a = e.after_value, b = e.before_value;
  switch (e.action_type) {
    case "REPORT_UPLOADED": return { icon: "upload", tone: "info", title: `File received: ${v(a, "file_name")}`, detail: `${v(a, "kind")} · ${Math.round(Number(v(a, "size")) / 1024) || 1} KB · sha256 ${v(a, "sha256").slice(0, 12)}…` };
    case "UPLOAD_REJECTED": return { icon: "x", tone: "bad", title: `Upload rejected: ${v(a, "file_name")}`, detail: `reason: ${v(a, "code").replace(/_/g, " ")}` };
    case "JOB_QUEUED": return { icon: "clock", tone: "neutral", title: `${v(a, "kind") === "INGEST" ? "Workbook reading" : "Processing"} queued` };
    case "JOB_STARTED": return { icon: "activity", tone: "info", title: `Processing started (attempt ${v(a, "attempt")})` };
    case "JOB_SUCCEEDED": return { icon: "check", tone: "good", title: `${v(a, "kind") === "INGEST" ? "Workbook read; mapping proposed" : "Processing completed"}` };
    case "JOB_FAILED": return { icon: "alertCircle", tone: "bad", title: "Processing failed", detail: v(a, "message") || v(a, "code") };
    case "JOB_CANCELLED": case "JOB_CANCEL_REQUESTED": return { icon: "x", tone: "neutral", title: "Processing cancelled by a user" };
    case "STATUS_CHANGED": return { icon: "arrowRight", tone: "neutral", title: `Status: ${v(b, "status").toLowerCase().replace(/_/g, " ")} → ${v(a, "status").toLowerCase().replace(/_/g, " ")}`, detail: v(a, "reason") };
    case "AI_MAPPING_SUGGESTED": return { icon: "sparkles", tone: "info", title: `AI suggested mappings for sheet ${v(a, "sheet")}`, detail: v(a, "model") };
    case "MAPPING_CONFIRMED": return { icon: "check", tone: "good", title: `Mapping confirmed: ${v(a, "field")}`, detail: v(a, "source_column") ? `← column “${v(a, "source_column")}”` : "left unmapped" };
    case "MAPPING_OVERRIDDEN": return { icon: "layers", tone: "warn", title: `Mapping changed: ${v(a, "field")}`, detail: `“${v(b, "source_column") || "none"}” → “${v(a, "source_column") || "none"}”` };
    case "SOURCE_COLUMN_UNMAPPED": return { icon: "info", tone: "neutral", title: `Source column not mapped: “${v(a, "source_column")}”`, detail: `sheet ${v(a, "sheet")} · values retained` };
    case "EXCEPTION_STATUS_CHANGED": return { icon: "exceptions", tone: "info", title: `Finding marked ${v(a, "review_status").replace(/_/g, " ")}`, detail: [v(a, "assignee") && `assigned to ${v(a, "assignee")}`, v(a, "note")].filter(Boolean).join(" · ") };
    case "EXPORT_GENERATED": return { icon: v(a, "channel") === "email" ? "mail" : "download", tone: "neutral", title: `Export: ${v(a, "export").replace(/_/g, " ")}`, detail: v(a, "channel") === "email" ? `e-mail to ${v(a, "recipient")} · ${v(a, "status").toLowerCase()}` : "downloaded" };
    case "OBLIGATION_STATUS_CHANGED": return { icon: "todo", tone: "neutral", title: "Follow-up updated", detail: [v(a, "status"), v(a, "owner")].filter(Boolean).join(" · ") };
    case "ALERT_ACKNOWLEDGED": return { icon: "bell", tone: "neutral", title: "Alert marked read" };
    case "AI_SUMMARY_GENERATED": return { icon: "sparkles", tone: "info", title: "AI exception summary generated", detail: v(a, "model") };
    case "REPORT_DELETED": return { icon: "x", tone: "warn", title: `Report deleted: ${v(b, "file_name")}` };
    case "REPORT_EXPIRED": return { icon: "clock", tone: "neutral", title: `Report expired (retention): ${v(b, "file_name")}` };
    case "LOGIN_SUCCEEDED": return { icon: "user", tone: "neutral", title: "Signed in" };
    case "LOGIN_FAILED": return { icon: "user", tone: "warn", title: "Failed sign-in attempt" };
    case "LOGOUT": return { icon: "logout", tone: "neutral", title: "Signed out" };
    case "ACCOUNT_CREATED": return { icon: "user", tone: "good", title: "Account created" };
    case "TEMPLATE_CREATED": return { icon: "layers", tone: "neutral", title: `Mapping template created: ${v(a, "name")}` };
    default: return { icon: "info", tone: "neutral", title: e.action_type.toLowerCase().replace(/_/g, " ") };
  }
}
