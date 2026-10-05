export type ReportStatus =
  | "UPLOADED" | "QUEUED" | "INGESTING" | "WAITING_FOR_REVIEW" | "PROCESSING"
  | "COMPLETE" | "FAILED" | "CANCELLED" | "EXPIRED";
export type SheetStatus = "PENDING_CONFIRMATION" | "CONFIRMED" | "SKIPPED";
export type MappingState = "MAPPED_BY_ALIAS" | "MAPPED_BY_AI" | "UNMAPPED" | "MANUAL";
export type Severity = "CRITICAL" | "HIGH" | "MEDIUM" | "INFO";
export type CheckType = "MANDATORY_FIELD" | "ARITHMETIC" | "DUPLICATE" | "MAPPING_COMPLETENESS" | "DATE" | "CURRENCY" | "STATUS" | "OTHER";
export type ObligationStatus = "OPEN" | "IN_PROGRESS" | "RESOLVED" | "OVERDUE";
export type AlertSource = "COVERAGE" | "MANDATORY_FAIL" | "NOT_EVALUABLE" | "DUPLICATE" | "OVERDUE" | "MAPPING_COMPLETENESS";

export interface Report {
  id: string;
  created_at: string;
  file_name: string;
  file_size_bytes: number;
  sheet_count_total: number;
  rows_processed: number;
  rows_total: number;
  coverage_pct: number | null;
  grade: string | null;
  score: number | null;
  status: ReportStatus;
  processing_error: string | null;
  error_code?: string | null;
  source_sha256?: string | null;
  updated_at?: string | null;
  expires_at?: string | null;
  ingest_notes?: Record<string, unknown> | null;
  job?: Job | null;
  source_channel?: string;
  file_kind?: string | null;
  sender?: string | null;
  programme?: string | null;
  binder_id?: string | null;
  issues_found?: number | null;
}

export interface Job {
  id: string;
  kind: "INGEST" | "PROCESS";
  status: "QUEUED" | "RUNNING" | "RETRYING" | "SUCCEEDED" | "FAILED" | "CANCELLED";
  stage: string | null;
  attempts: number;
  max_attempts: number;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  heartbeat_at: string | null;
  metrics?: Record<string, unknown> | null;
}

export type Role = "OWNER" | "ADMIN" | "ANALYST" | "VIEWER" | "SENDER";
export type OrgType = "capacity_provider" | "mga" | "tpa";

export interface MfaStatus { enabled: boolean; required: boolean; setup_required: boolean }

export interface Me {
  user: { id: string; email: string; display_name: string };
  tenant: { id: string; name: string; retention_days: number; org_type?: OrgType; require_2fa?: boolean };
  role: Role | string;
  can_write: boolean;
  permissions?: string[];
  mfa?: MfaStatus | null;
  csrf_token: string;
}

/** Returned by /auth/login instead of a session when a second factor is needed. */
export interface MfaChallenge { mfa_required: true; mfa_token: string; methods: string[] }

export interface OrgSettings { id: string; name: string; org_type: OrgType; require_2fa: boolean; retention_days: number; anonymise_names?: boolean }
export interface Member { membership_id: string; user_id: string; email: string; display_name: string; role: Role; created_at: string }
export interface Invitation { id: string; email: string; role: Role; created_at: string; expires_at: string }
export interface InvitationCreated extends Invitation { accept_token: string }
export interface SsoConfig {
  configured: boolean; issuer: string | null; client_id: string | null; has_client_secret: boolean;
  token_auth_method: string | null; domains: string[]; jit_provisioning: boolean; default_role: Role | null;
  enabled: boolean; callback_url: string;
}
export interface SsoConfigInput {
  issuer: string; client_id: string; client_secret?: string | null; token_auth_method: string; domains: string[];
  jit_provisioning: boolean; default_role: Role; enabled: boolean;
}

export interface SheetMapping {
  sheet: Sheet;
  headers: string[];
  fields: MappingField[];
}

export interface MoneyAmount {
  currency: string;
  amount: number;
}

export type SheetMappingStatus = "mapped" | "partial" | "unmapped" | "empty" | "error" | "non_claim_summary";

export interface Sheet {
  id: string;
  sheet_name: string;
  sheet_index: number;
  header_row_index: number | null;
  row_count: number;
  status: SheetStatus;
  skip_reason: string | null;
  // A sheet with 0 mapped fields ("unmapped") is never the same status as
  // a genuinely empty sheet ("empty") -- its rows are still retained.
  mapping_status: SheetMappingStatus;
  fields_mapped: number;
  fields_total: number;
  needs_review?: number;
  source_column_count?: number;
  hidden?: boolean;
  notes?: string[];
  trailing_blank_rows?: number;
}

export interface MappingField {
  field_code: string;
  field_name: string;
  source_column: string | null;
  mapping_state: MappingState;
  confidence_score: number | null;
  sample_values: string[];
  confirmed: boolean;
  required?: boolean;
  review_state?: "HIGH_CONFIDENCE" | "REVIEW" | "AMBIGUOUS" | "UNMAPPED" | "CONFIRMED";
  evidence?: string | null;
  ai_model?: string | null;
}

export type ValidationStatus = "PASS" | "FAIL" | "NOT_EVALUABLE" | "REVIEW";

export interface ExceptionRow {
  claim_row_id: string;
  claim_reference: string | null;
  sheet_name: string | null;
  row_index: number;
  source_row_number?: number | null;
  currency?: string | null;
  rule?: string | null;
  review_status?: string | null;
  assignee?: string | null;
  note?: string | null;
  amount: number | null;
  check_type: CheckType;
  status: ValidationStatus;
  severity: Severity;
  message: string;
  validation_result_id: string;
  /** Additive (reports processed after the strategy pass): where and what, in plain English. */
  field_code?: string | null;
  cell?: string | null;
  source_column?: string | null;
  sentence?: string | null;
  owner?: "sender" | "us" | null;
}

export interface HealthExample {
  sheet: string | null;
  cell: string | null;
  column: string | null;
  claim_ref: string | null;
  where: string;
  sentence: string;
}

export interface HealthRule {
  rule: string;
  label: string;
  severity: Severity;
  outcome: "FAIL" | "REVIEW";
  owner: "sender" | "us";
  check_type: string;
  fix: string;
  findings: number;
  rows: number;
  money_at_risk: { currency: string; amount: number }[];
  examples: HealthExample[];
}

export interface CouldntCheck {
  key: string;
  label: string;
  reason: string;
  rows: number | null;
  fix: "mapping" | "data";
}

export interface GridCell { v: string | null; tone: "ok" | "warn" | "err" | "grey" | null; notes: { result: string; status: string; label: string; text: string; fix: string }[] }
export interface GridRow { row: number; kind: "header" | "structural" | "claim" | "other"; cells: GridCell[]; row_notes: GridCell["notes"] }
export interface GridPage { sheet_id: string; sheet_name: string; total_rows: number; columns: number; header_row: number; offset: number; rows: GridRow[] }

export interface ExceptionGroups {
  groups: { rule: string; label: string; status: ValidationStatus; severity: Severity; count: number; fix: string }[];
  total: number;
  sheets: { id: string; name: string }[];
  columns: string[];
}

export interface QueryLetter {
  subject: string;
  body: string;
  items: number;
  groups: { rule: string; label: string; fix: string; outcome: string; severity: Severity; items: { where: string; claim_ref: string | null; sentence: string }[] }[];
}

export interface MonthOnMonth {
  previous_report_id: string;
  previous_file_name: string;
  threshold_pct: number;
  threshold_min: number;
  claims_compared: number;
  counts: { vanished: number; paid_down: number; reserve_jump: number };
  vanished: { claim_ref: string; previous_status: string | null; previous: string; sentence: string }[];
  paid_down: { claim_ref: string; where: string; previous: number; current: number; currency: string | null; sentence: string }[];
  reserve_jump: { claim_ref: string; where: string; previous: number; current: number; currency: string | null; pct: number; sentence: string }[];
}

/** The health report's single view (backend app/services/health_view.py). */
export interface HealthView {
  version: number;
  verdict: "ready" | "fix";
  verdict_label: string;
  verdict_reason: string;
  counts: { errors: number; error_rows: number; warnings: number; couldnt_check: number; couldnt_check_rows: number };
  top_fixes: HealthRule[];
  rules: HealthRule[];
  by_owner: { sender: string[]; us: string[] };
  couldnt_check: CouldntCheck[];
  duplicates: { exact_pairs: number; probable_pairs: number | null; probable_high_confidence: number; repeat_period_unknown: number; development_pairs: number };
  money_by_currency: NonNullable<ReportSummary["totals_by_currency"]>;
}

export type ExcludedRowReason = "blank" | "blank_run" | "subtotal" | "repeated_header" | "title";

export interface ExcludedRow {
  id: string;
  sheet_name: string;
  row_number: number;
  row_count?: number;
  reason: ExcludedRowReason;
  detail: string;
  values: Record<string, string>;
}

export type DuplicateReviewStatus = "not_duplicate" | "flagged_for_sender" | "confirmed_duplicate";

export interface DuplicatePair {
  validation_result_id: string;
  match_type: "exact_duplicate" | "probable_duplicate" | "repeat_period_unknown";
  row_a: Record<string, unknown>;
  row_b: Record<string, unknown>;
  detail: string;
  review_status: DuplicateReviewStatus | null;
}

export interface Obligation {
  id: string;
  report_id: string;
  claim_row_id: string | null;
  owner: string | null;
  deadline: string | null;
  status: ObligationStatus;
  note: string | null;
  created_by: string | null;
  created_at: string;
  resolved_at: string | null;
}

export interface Alert {
  id: string;
  report_id: string;
  severity: Severity;
  source: AlertSource;
  message: string;
  acknowledged: boolean;
  created_at: string;
}

export interface AuditLogEntry {
  id: string;
  seq?: number;
  entry_hash?: string;
  report_id: string | null;
  action_type: string;
  entity_type: string;
  entity_id: string;
  actor: string;
  before_value: Record<string, unknown> | null;
  after_value: Record<string, unknown> | null;
  created_at: string;
}

export interface FieldCompleteness {
  field_code: string;
  field_name: string;
  present: number;
  denominator: number;
  never_mapped: boolean;
}

export interface ReconciliationSummary {
  source_worksheets: number;
  source_data_rows: number;
  mapped_rows: number;
  unmapped_rows: number;
  rejected_rows: number;
  duplicate_rows: number;
  exported_rows: number;
  rows_requiring_review: number;
  non_claim_summary_rows: number;
  reconciles: boolean;
}

export interface ReportSummary {
  report: Report;
  sheets_total: number;
  sheets_processed: number;
  missing_mandatory_rows: number;
  arithmetic_mismatches: number;
  arithmetic_not_evaluable: number;
  exact_duplicates: number;
  /** null when the probable-duplicate check was not run (see not_assessed_checks). */
  probable_duplicates: number | null;
  not_assessed_checks?: { check: string; label: string; reason: string }[];
  coverage_statement?: string;
  field_completeness: FieldCompleteness[];
  missing_mandatory_by_sheet?: Record<string, number>;
  health_view?: HealthView;
  totals_by_currency?: { currency: string; rows: number; paid_to_date: number; reserve: number; incurred: number; fees_paid_to_date?: number; fees_rows?: number; paid_rows?: number; reserve_rows?: number; incurred_rows?: number }[];
  score_reliable?: boolean;
  unmapped_source_columns?: { sheet_name: string; columns: string[] }[];
  development_pairs?: number;
  development_refs?: string[];
  recommendations?: Recommendation[];
  total_claims?: number;
  grade?: number | string;
  grade_label?: string;
  composite_score?: number;
  exception_counts_by_rule?: Record<string, number>;
  sheet_audit?: { sheet_name: string; status: string; reason: string; rows_processed: number; rows_rejected: number; fields_mapped: number }[];
  arithmetic_matches?: number;
  period_unknown_repeats?: number;
  definitions?: Record<string, string>;
  claim_status_counts?: Record<string, number>;
  reporting_periods?: Record<string, number>;
  not_evaluable_by_reason: Record<string, number>;
  excluded_row_counts: Record<string, number>;
  skipped_sheets: { sheet_name: string; reason: string }[];
  unmapped_sheets: { sheet_name: string; reason: string }[];
  non_claim_summary_sheets: { sheet_name: string; reason: string }[];
  reconciliation: ReconciliationSummary;
}

// AI exception-triage summary (routes/exception_summary.py). `aggregate`
// is deterministic (built from the same validation-result rows the
// Exceptions page already shows); `narrative` is the LLM's explanation
// of it, generated separately so report completion is never blocked or
// delayed by the AI call.
export type NarrativeStatus = "GENERATING" | "COMPLETE" | "FAILED" | "UNAVAILABLE";

export interface ExceptionCategoryBucket {
  check_type: string;
  count: number;
  value_at_stake: MoneyAmount[];
  pct_of_total_exceptions: number;
  sheet_count: number;
}

export interface ExceptionSheetBucket {
  sheet_name: string;
  count: number;
  value_at_stake: MoneyAmount[];
  pct_of_total_exceptions: number;
  low_mapping_completeness: boolean;
}

export interface RootCauseBucket {
  count: number;
  pct_of_total_exceptions: number;
}

export interface ExceptionAggregate {
  report_id: string;
  file_name: string;
  rows_total: number;
  rows_processed: number;
  total_exceptions: number;
  total_value_at_stake: MoneyAmount[];
  arithmetic_not_evaluable_count: number;
  by_category: ExceptionCategoryBucket[];
  by_sheet: ExceptionSheetBucket[];
  root_cause_split: { ingestion: RootCauseBucket; data_quality: RootCauseBucket };
  severity_counts: Record<string, number>;
  duplicate_counts: Record<string, number>;
  mapping_completeness_findings: { sheet_name: string; message: string }[];
}

export interface NarrativeAction {
  title: string;
  rationale: string;
  category: "ingestion" | "data_quality" | "duplicate" | "other";
  filter_check_type: string | null;
  filter_sheet_name: string | null;
}

export interface ExceptionNarrative {
  executive_summary: string;
  actions: NarrativeAction[];
  ingestion_issues: string[];
  data_issues: string[];
}

export interface ExceptionSummary {
  id: string;
  report_id: string;
  narrative_status: NarrativeStatus;
  aggregate: ExceptionAggregate;
  narrative: ExceptionNarrative | null;
  narrative_model: string | null;
  narrative_error: string | null;
  narrative_warning: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface Template {
  id: string;
  name: string;
  sender_identifier: string | null;
  field_mappings: Record<string, string>;
  is_standard: boolean;
  is_deletable: boolean;
  created_by: string | null;
  created_at: string;
}


export interface SystemStatus {
  workers_alive: number;
  worker_available: boolean;
  worker_modes: string[];
  last_worker_check_in_s: number | null;
  embedded_worker_configured: boolean;
  stale_after_s: number;
  queued: number;
  running: number;
  oldest_queued_s: number | null;
}

export interface Recommendation {
  id: string;
  severity: Severity;
  title: string;
  evidence: string;
  action: string;
  target: string | null;
  report_id?: string;
  file_name?: string;
}

export interface Overview {
  reports: { total: number; complete: number; awaiting_review: number; in_flight: number; failed: number };
  received: { last_24h: number; last_7d: number };
  findings: {
    open_by_severity: Record<string, number>;
    missing_mandatory_rows?: number; arithmetic_mismatches?: number; exact_duplicates?: number;
    probable_duplicates?: number; development_pairs?: number; arithmetic_not_evaluable?: number;
    unmapped_columns?: number; claims?: number; reports_with_checks_not_assessed?: number;
  };
  trend: { date: string; reports: number; rows: number }[];
  processing: { worker_available: boolean; workers_alive: number; jobs_24h: number; failed_24h: number; median_job_s: number | null };
  alerts: { unread: number; latest: Alert[] };
  latest_reports: Report[];
  in_flight_reports?: Report[];
  recommendations: Recommendation[];
  activity: AuditLogEntry[];
}

export interface WorkItem {
  kind: string;
  priority: Severity;
  title: string;
  detail: string;
  count: number;
  report_id: string | null;
  file_name: string | null;
  href: string | null;
}
export interface WorkQueue { items: WorkItem[]; total: number }

export type ChannelStatus = "active" | "not_set_up" | "not_configured" | "planned";
export interface Channel { id: string; name: string; status: ChannelStatus; detail: string; address?: string | null }
export interface Channels {
  inbound: Channel[];
  outbound: Channel[];
  services?: {
    ai: { configured: boolean; provider: string | null; region: string | null; model: string | null };
    fx: { source: string; latest_rate_date: string | null; auto_refresh: boolean };
  };
  pipeline: string[];
  limits: { max_upload_mb: number; ai_mapping: boolean };
}

export type WebhookEvent = "report.completed" | "report.failed" | "report.waiting_for_review";
export interface WebhookEndpoint { id: string; url: string; events: WebhookEvent[]; description: string | null; enabled: boolean; created_at: string }
export interface WebhookDelivery {
  id: string; event_type: string; message_id: string; status: "PENDING" | "DELIVERED" | "FAILED" | "EXHAUSTED";
  attempts: number; last_status_code: number | null; last_error: string | null; next_attempt_at: string | null;
  created_at: string; delivered_at: string | null;
}
export interface SftpDestination {
  host: string; port: number; username: string; auth: "password" | "private_key"; host_key_fingerprint: string;
  remote_dir: string; auto_deliver: boolean; enabled: boolean; created_at: string;
}
export interface SftpInput {
  host: string; port: number; username: string; password?: string | null; private_key?: string | null;
  host_key_fingerprint: string; remote_dir: string; auto_deliver: boolean; enabled: boolean;
}

export interface Delivery {
  id: string;
  report_id: string;
  kind: string;
  channel: string;
  destination: string | null;
  file_name: string;
  size_bytes: number | null;
  status: "DELIVERED" | "FAILED" | "NOT_CONFIGURED";
  error: string | null;
  created_by: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface ClaimRow {
  id: string;
  sheet_id: string;
  source_row_number: number | null;
  claim_reference: string | null;
  insured_name: string | null;
  claim_status: string | null;
  date_of_loss: string | null;
  reporting_period: string | null;
  currency: string | null;
  paid_amount: number | null;
  reserve_amount: number | null;
  incurred_amount: number | null;
  fees_paid_to_date?: number | null;
  unmapped_values?: Record<string, unknown> | null;
}

// ---------------------------------------------------------------- check modules (P3+)
export type ModuleState = "ASSESSED" | "PARTIAL" | "NOT_ASSESSED" | "NOT_RUN";
export interface CheckRule { code: string; label: string; assessed: number; not_assessed: number; reasons: string[] }
export interface ModuleRun {
  module: string; label: string; state: ModuleState; reason: string | null; rules: CheckRule[];
  finding_count: number; open_count: number; ran_at: string | null; ran_by: string | null; coverage_statement: string;
  exposure: Record<string, string>; unpriced_findings: number;
}
export type Disposition = "OPEN" | "CONFIRMED" | "DISMISSED";
export interface ModuleFinding {
  id: string; module: string; rule_code: string; status: "FAIL" | "REVIEW"; severity: string; title: string;
  explanation: string; sheet_name: string | null; row_number: number | null; field_code: string | null;
  source_column: string | null; claim_row_id: string | null; claim_reference: string | null;
  amount: string | null; currency: string | null; evidence: Record<string, unknown> | null;
  disposition: Disposition; disposition_note: string | null; disposed_by: string | null; disposed_at: string | null;
}
export interface BinderInput {
  name: string; umr: string | null; coverholder: string | null; inception_date: string; expiry_date: string;
  currencies: string[]; limit_currency: string; claims_authority: string | null; aggregate_limit: string | null;
}
export interface Binder extends BinderInput { id: string; created_at: string; created_by: string }
export interface SanctionsList {
  id: string; name: string; source: "OFSI" | "OFAC" | "EU" | "UN" | "CUSTOM"; file_name: string; sha256: string;
  entry_count: number; uploaded_at: string; uploaded_by: string;
}
export interface SenderScore {
  sender: string; reports: number; rows: number; first_report_at: string; latest_report_at: string;
  latest_grade: string | null; latest_score: number | null; average_score: number | null; score_trend: number[];
  exceptions_per_1000_rows: number | null; resubmissions_per_1000_rows: number | null; binder_breaches: number;
  sanctions_open_matches: number; leakage_exposure: Record<string, string>; mapping_first_time_right_pct: number;
}
export interface Scorecard { since: string | null; senders: SenderScore[]; not_assessed: string[] }
export interface PreflightSheet { sheet_name: string; rows: number; mapped_fields: string[]; missing_required_fields: string[]; unmapped_columns: string[]; notes: string[] }
export interface Preflight {
  file_name: string; sha256: string; ready: boolean; verdict: string; rows: number; missing_mandatory_rows: number;
  arithmetic_mismatches: number; exact_duplicates: number; sheets: PreflightSheet[];
  issues: { sheet_name: string | null; row_number: number | null; check: string; message: string }[];
  issues_total: number; coverage_statement: string;
}
export interface Submission { id: string; file_name: string; status: string; created_at: string; rows_total: number }
export interface BillingPlan { name: string; label: string; modules: string[]; monthly_rows: number | null; seats: number | null; purchasable: boolean }
export interface Billing {
  enforced: boolean; plan: string | null; status: string | null; period_end: string | null; modules: string[] | null;
  monthly_rows: number | null; seats: number | null; rows_this_month: number; seats_used: number; plans: BillingPlan[]; customer: boolean;
}

/** One issue record (GET /reports/{id}/issues). */
export interface Issue {
  id: string; rule: string | null; rule_version: string | null; ruleset_version: string | null; label: string;
  severity: string; outcome: string; status: string; sheet: string | null; cell: string | null; column: string | null;
  field_code: string | null; row: number | null; claim_reference: string | null;
  expected: number | string | null; actual: number | string | null; difference: number | null;
  evidence: string | null; sentence: string | null; suggested_action: string | null; root_cause: string | null;
  auto_fix: boolean; symptom_of: string | null; history: { at: string; status: string; actor: string; note?: string | null }[];
  lineage?: { file: string; sheet: string | null; row: number | null; cell: string | null; column: string | null; original_value: string | null; normalised_value: string | number | null; mapped_field: { code: string; name: string } | null; transformation: string };
}

/** Issues sharing one cause: one card, one decision. */
export interface RootCause {
  root_cause: string; rule: string | null; rule_version: string | null; label: string; column: string | null; sheet: string | null;
  severity: string; outcome: string; owner: "sender" | "us"; auto_fix: boolean; fix: string;
  count: number; open: number; rows: number; symptoms: number; kind: "cause" | "symptom";
  caused_by: { root_cause: string; count: number }[]; amount_affected: { currency: string | null; amount: number }[];
  first_issue_id: string; first_open_issue_id: string | null;
}

export interface IssueList { total: number; items: Issue[]; by_status: Record<string, number>; root_causes: RootCause[] }

export type BulkAction = "apply_safe_fix" | "send_to_sender" | "override" | "resolve";
