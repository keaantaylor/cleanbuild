export type ReportStatus = "PENDING_MAPPING" | "READY_FOR_REVIEW" | "PROCESSING" | "COMPLETE" | "FAILED";
export type SheetStatus = "PENDING_CONFIRMATION" | "CONFIRMED" | "SKIPPED";
export type MappingState = "MAPPED_BY_ALIAS" | "MAPPED_BY_AI" | "UNMAPPED" | "MANUAL";
export type Severity = "CRITICAL" | "HIGH" | "MEDIUM" | "INFO";
export type CheckType = "MANDATORY_FIELD" | "ARITHMETIC" | "DUPLICATE" | "MAPPING_COMPLETENESS" | "DATA_QUALITY";
export type ObligationStatus = "OPEN" | "IN_PROGRESS" | "RESOLVED" | "OVERDUE";
export type AlertSource = "COVERAGE" | "MANDATORY_FAIL" | "NOT_EVALUABLE" | "DUPLICATE" | "OVERDUE";

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
  processing_phase: string | null;
  processing_error: string | null;
}

export interface Sheet {
  id: string;
  sheet_name: string;
  sheet_index: number;
  header_row_index: number | null;
  row_count: number;
  status: SheetStatus;
  skip_reason: string | null;
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

export interface ExceptionRow {
  claim_row_id: string;
  claim_reference: string | null;
  sheet_name: string | null;
  row_index: number;
  amount: number | null;
  check_type: CheckType;
  severity: Severity;
  message: string;
  validation_result_id: string;
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
}

export type NarrativeStatus = "GENERATING" | "COMPLETE" | "UNAVAILABLE" | "FAILED";

export interface ExceptionAggregateCategory {
  check_type: string;
  count: number;
  value_at_stake: number;
  pct_of_total_exceptions: number;
  sheet_count: number;
}

export interface ExceptionAggregateSheet {
  sheet_name: string;
  count: number;
  value_at_stake: number;
  pct_of_total_exceptions: number;
  low_mapping_completeness: boolean;
}

export interface ExceptionAggregateRootCause {
  count: number;
  value_at_stake: number;
  pct_of_total_exceptions: number;
  sheet_count: number;
}

export interface ExceptionAggregate {
  report_id: string;
  file_name: string;
  rows_total: number;
  rows_processed: number;
  total_exceptions: number;
  total_value_at_stake: number;
  arithmetic_not_evaluable_count: number;
  by_category: ExceptionAggregateCategory[];
  by_sheet: ExceptionAggregateSheet[];
  root_cause_split: { ingestion: ExceptionAggregateRootCause; data_quality: ExceptionAggregateRootCause };
  severity_counts: Record<string, number>;
  duplicate_counts: { exact_duplicate: number; probable_duplicate: number };
  mapping_completeness_findings: { sheet_name: string; message: string }[];
}

export interface ExceptionNarrativeAction {
  title: string;
  rationale: string;
  category: "ingestion" | "data_quality" | "duplicate" | "other";
  filter_check_type: string | null;
  filter_sheet_name: string | null;
}

export interface ExceptionNarrative {
  executive_summary: string;
  actions: ExceptionNarrativeAction[];
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
