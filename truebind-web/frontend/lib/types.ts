export type ReportStatus = "PENDING_MAPPING" | "READY_FOR_REVIEW" | "PROCESSING" | "COMPLETE" | "FAILED";
export type SheetStatus = "PENDING_CONFIRMATION" | "CONFIRMED" | "SKIPPED";
export type MappingState = "MAPPED_BY_ALIAS" | "MAPPED_BY_AI" | "UNMAPPED" | "MANUAL";
export type Severity = "CRITICAL" | "HIGH" | "MEDIUM" | "INFO";
export type CheckType = "MANDATORY_FIELD" | "ARITHMETIC" | "DUPLICATE" | "MAPPING_COMPLETENESS";
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
}

export type SheetMappingStatus = "mapped" | "partial" | "unmapped" | "empty" | "error";

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
}

export interface MappingField {
  field_code: string;
  field_name: string;
  source_column: string | null;
  mapping_state: MappingState;
  confidence_score: number | null;
  sample_values: string[];
  confirmed: boolean;
}

export type ValidationStatus = "PASS" | "FAIL" | "NOT_EVALUABLE";

export interface ExceptionRow {
  claim_row_id: string;
  claim_reference: string | null;
  sheet_name: string | null;
  row_index: number;
  amount: number | null;
  check_type: CheckType;
  status: ValidationStatus;
  severity: Severity;
  message: string;
  validation_result_id: string;
}

export type ExcludedRowReason = "blank" | "subtotal" | "repeated_header";

export interface ExcludedRow {
  id: string;
  sheet_name: string;
  row_number: number;
  reason: ExcludedRowReason;
  detail: string;
  values: Record<string, string>;
}

export type DuplicateReviewStatus = "not_duplicate" | "flagged_for_sender" | "confirmed_duplicate";

export interface DuplicatePair {
  validation_result_id: string;
  match_type: "exact_duplicate" | "probable_duplicate";
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
  report_id: string;
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
  missing_mandatory_by_sheet: Record<string, number>;
  not_evaluable_by_reason: Record<string, number>;
  excluded_row_counts: Record<string, number>;
  skipped_sheets: { sheet_name: string; reason: string }[];
  unmapped_sheets: { sheet_name: string; reason: string }[];
  reconciliation: ReconciliationSummary;
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
