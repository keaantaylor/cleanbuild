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
}

export interface Job {
  id: string;
  kind: "INGEST" | "PROCESS";
  status: "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "CANCELLED";
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

export interface Me {
  user: { id: string; email: string; display_name: string };
  tenant: { id: string; name: string; retention_days: number };
  role: string;
  can_write: boolean;
  csrf_token: string;
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
  probable_duplicates: number;
  field_completeness: FieldCompleteness[];
  missing_mandatory_by_sheet?: Record<string, number>;
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
    unmapped_columns?: number; claims?: number;
  };
  trend: { date: string; reports: number; rows: number }[];
  processing: { worker_available: boolean; workers_alive: number; jobs_24h: number; failed_24h: number; median_job_s: number | null };
  alerts: { unread: number; latest: Alert[] };
  latest_reports: Report[];
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

export interface Channel { id: string; name: string; status: "active" | "planned" | "not_configured"; detail: string }
export interface Channels {
  inbound: Channel[];
  outbound: Channel[];
  pipeline: string[];
  limits: { max_upload_mb: number; ai_mapping: boolean };
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
