/**
 * Automatically generated OpenAPI TypeScript contracts for Corbel.
 * Generated from FastAPI specification: Corbel — Enterprise AI Platform v0.1.0
 * DO NOT EDIT MANUALLY - re-run: npm run generate-api or python scripts/generate_openapi.py
 */

/** Request to dispatch an approved action to target adapter. */
export interface ActionExecuteRequest {
  idempotency_key: string;
  /** Simulate adapter failure for resilience testing */
  simulated_failure?: boolean;
}

/** Target-system execution outcome record. */
export interface ActionExecutionResponse {
  id: string;
  action_id: string;
  approval_id: string;
  idempotency_key: string;
  target_adapter_type: string;
  status: ExecutionStatus;
  attempt_count: number;
  dispatched_payload_json: Record<string, unknown>;
  dispatched_payload_hash: string;
  adapter_response_json?: Record<string, unknown> | null;
  error_message?: string | null;
  dispatched_at: string;
  completed_at?: string | null;
}

/** Proposed or executed action. */
export interface ActionResponse {
  id: string;
  project_id: string;
  recommendation_id: string;
  action_type: ActionType;
  target_system: string;
  proposed_payload_json: Record<string, unknown>;
  is_consequential: boolean;
  status: ActionStatus;
  created_at: string;
  updated_at: string;
}

/** Governed lifecycle status for a proposed action. */
export type ActionStatus = 'DRAFT' | 'AWAITING_APPROVAL' | 'APPROVED' | 'EXECUTING' | 'EXECUTED' | 'FAILED' | 'REJECTED';

/** Supported target action types for P2P and operational governance. */
export type ActionType = 'HOLD_INVOICE' | 'REQUEST_CREDIT_MEMO' | 'FLAG_SUPPLIER_REVIEW';

/** Actor identity category for append-only audit events. */
export type ActorType = 'USER' | 'SYSTEM_WORKER' | 'API_KEY';

/** Human decision payload for an approval gate. */
export interface ApprovalDecisionRequest {
  /** Must be APPROVED or REJECTED */
  decision: ApprovalStatus;
  rationale?: string | null;
}

/** Human authorization gate record. */
export interface ApprovalResponse {
  id: string;
  action_id: string;
  assigned_role: string;
  decided_by_user_id?: string | null;
  status: ApprovalStatus;
  approved_payload_hash?: string | null;
  approved_payload_json?: Record<string, unknown> | null;
  decision_rationale?: string | null;
  decided_at?: string | null;
  expires_at?: string | null;
  created_at: string;
}

/** Human decision state for an action approval gate. */
export type ApprovalStatus = 'PENDING' | 'APPROVED' | 'REJECTED' | 'EXPIRED' | 'REVOKED';

/** Paginated list of audit events. */
export interface AuditEventListResponse {
  items: AuditEventResponse[];
  total: number;
}

/** Append-only authoritative audit record. */
export interface AuditEventResponse {
  id: string;
  organization_id: string;
  project_id?: string | null;
  actor_type: ActorType;
  actor_id: string;
  action_type: string;
  affected_entity_type: string;
  affected_entity_id: string;
  execution_context_json?: Record<string, unknown> | null;
  correlation_id?: string | null;
  canonical_payload_hash?: string | null;
  outcome_status: string;
  ip_address?: string | null;
  timestamp: string;
}

/** Export item with cryptographic payload verification result. */
export interface AuditTrailExportItem {
  id: string;
  organization_id: string;
  project_id?: string | null;
  actor_type: ActorType;
  actor_id: string;
  action_type: string;
  affected_entity_type: string;
  affected_entity_id: string;
  execution_context_json?: Record<string, unknown> | null;
  correlation_id?: string | null;
  canonical_payload_hash?: string | null;
  outcome_status: string;
  ip_address?: string | null;
  timestamp: string;
  payload_verification_status: string;
  calculated_payload_hash?: string | null;
}

/** Complete exported audit trail with canonical payload verification.

Note: integrity_verified reflects per-record canonical payload SHA-256 hash matching
and does not provide cryptographic tamper evidence against privileged database
administrators or record deletion/insertion/reordering attacks (which requires
external cryptographic chaining or anchoring, deferred). */
export interface AuditTrailExportResponse {
  organization_id: string;
  project_id?: string | null;
  exported_at: string;
  total_events: number;
  integrity_verified: boolean;
  events: AuditTrailExportItem[];
}

export interface Body_upload_dataset_api_v1_projects__project_id__datasets_upload_post {
  /** Tabular dataset file (CSV, JSON, XLSX) */
  file: string;
  /** Optional custom dataset name */
  name?: string | null;
  /** Optional dataset description */
  description?: string | null;
  /** Optional data source ID */
  data_source_id?: string | null;
}

/** Schema for creating a new Business Object. */
export interface BusinessObjectCreateRequest {
  /** Technical concept name (e.g. Invoice) */
  name: string;
  /** Human-readable title */
  display_name: string;
  /** Business description */
  description?: string | null;
  /** Name of PK property */
  primary_key_property?: string | null;
  /** Initial properties */
  properties?: PropertyCreateRequest[];
}

/** Detailed representation of a Business Object including all properties. */
export interface BusinessObjectDetailResponse {
  id: string;
  project_id: string;
  name: string;
  display_name: string;
  description?: string | null;
  primary_key_property?: string | null;
  version: number;
  property_count?: number;
  created_at: string;
  updated_at: string;
  properties?: PropertyResponse[];
}

/** Summary representation of a Business Object. */
export interface BusinessObjectResponse {
  id: string;
  project_id: string;
  name: string;
  display_name: string;
  description?: string | null;
  primary_key_property?: string | null;
  version: number;
  property_count?: number;
  created_at: string;
  updated_at: string;
}

/** Schema for updating Business Object metadata. */
export interface BusinessObjectUpdateRequest {
  display_name?: string | null;
  description?: string | null;
  primary_key_property?: string | null;
}

/** Payload to create a business rule on a monitor. */
export interface BusinessRuleCreate {
  /** Unique rule code identifier */
  rule_code: string;
  /** Human readable description */
  description?: string | null;
  /** Exception severity */
  severity?: RuleSeverity;
  /** Rule evaluation type */
  rule_type?: string;
  /** Target entity property or process metric */
  field_name: string;
  /** Comparison operator */
  operator?: RuleOperator;
  /** Numeric threshold value */
  threshold_value?: number | null;
  /** String threshold value */
  threshold_string?: string | null;
  /** Optional secondary property for comparison */
  secondary_field?: string | null;
  /** Additional rule parameters */
  parameters_json?: Record<string, unknown> | null;
}

/** API response model for a configured business rule. */
export interface BusinessRuleResponse {
  /** Unique rule code identifier */
  rule_code: string;
  /** Human readable description */
  description?: string | null;
  /** Exception severity */
  severity?: RuleSeverity;
  /** Rule evaluation type */
  rule_type?: string;
  /** Target entity property or process metric */
  field_name: string;
  /** Comparison operator */
  operator?: RuleOperator;
  /** Numeric threshold value */
  threshold_value?: number | null;
  /** String threshold value */
  threshold_string?: string | null;
  /** Optional secondary property for comparison */
  secondary_field?: string | null;
  /** Additional rule parameters */
  parameters_json?: Record<string, unknown> | null;
  id: string;
  monitor_id: string;
  created_at: string;
  updated_at: string;
}

/** Comprehensive deterministic profile for a single column. */
export interface ColumnProfile {
  column_name: string;
  detected_type: string;
  total_count?: number;
  null_count: number;
  non_null_count: number;
  null_percentage: number;
  distinct_count: number;
  unique_percentage: number;
  sample_values?: unknown[];
  numeric_stats?: NumericStats | null;
  datetime_stats?: DateTimeStats | null;
  string_stats?: StringStats | null;
  quality_warnings?: string[];
}

/** Discovered column metadata. */
export interface ColumnSchema {
  /** Column header name */
  name: string;
  /** Inferred primitive data type */
  data_type: string;
  /** Whether column accepts nulls */
  nullable?: boolean;
  /** Sample non-null values */
  sample_values?: unknown[];
}

/** Aggregated financial and token spend report. */
export interface CostSummaryResponse {
  total_cost_usd: number;
  total_tokens: number;
  total_cached_tokens: number;
  invocations_count: number;
  successful_tasks_count: number;
  cost_per_successful_task: number;
  breakdown_by_workflow: Record<string, number>;
  breakdown_by_model: Record<string, number>;
}

/** Directed transition between two activities in a Directly-Follows Graph. */
export interface DFGEdge {
  source: string;
  target: string;
  transition_count: number;
  case_count: number;
  avg_duration_seconds: number;
  median_duration_seconds: number;
  min_duration_seconds: number;
  max_duration_seconds: number;
  is_rework: boolean;
  is_bottleneck: boolean;
}

/** Activity node in a Directly-Follows Graph. */
export interface DFGNode {
  name: string;
  frequency: number;
  case_frequency: number;
  avg_duration_from_start_seconds: number;
  is_start_activity: boolean;
  is_end_activity: boolean;
}

/** Directly-Follows Graph representation for process visualizer. */
export interface DFGResponse {
  process_id: string;
  nodes: DFGNode[];
  edges: DFGEdge[];
  bottleneck_edge?: DFGEdge | null;
}

/** Schema for registering a new external data source connection. */
export interface DataSourceCreateRequest {
  /** Human-readable name */
  name: string;
  /** Connector dialect */
  source_type?: SourceType;
  /** Encrypted connection parameters */
  connection_config_encrypted?: string | null;
}

/** Schema representing a registered Data Source. */
export interface DataSourceResponse {
  id: string;
  project_id: string;
  name: string;
  source_type: string;
  status: string;
  created_at: string;
  updated_at: string;
}

/** Health status and latency metrics for PostgreSQL database. */
export interface DatabaseHealth {
  /** Connection status: connected, disconnected, or degraded */
  status: string;
  /** Roundtrip query latency in milliseconds */
  latency_ms?: number | null;
  /** Diagnostic message or error description */
  details?: string | null;
}

/** First N rows preview of a dataset version. */
export interface DatasetPreviewResponse {
  dataset_id: string;
  version_number: number;
  columns: string[];
  rows: Record<string, unknown>[];
  total_preview_rows: number;
}

/** Public metadata response for a logical Dataset container. */
export interface DatasetResponse {
  id: string;
  project_id: string;
  data_source_id: string;
  name: string;
  description?: string | null;
  status: string;
  created_at: string;
  updated_at: string;
  latest_version?: DatasetVersionResponse | null;
  version_count?: number;
}

/** Public metadata response for a Dataset Version snapshot (storage paths withheld). */
export interface DatasetVersionResponse {
  id: string;
  dataset_id: string;
  project_id: string;
  version_number: number;
  file_format: string;
  file_size_bytes: number;
  checksum_hash: string;
  record_count: number | null;
  column_count: number | null;
  status: string;
  error_message?: string | null;
  schema_metadata?: ColumnSchema[] | null;
  profiling_summary?: ProfilingSummary | null;
  imported_at: string;
}

/** Statistical summary for date and datetime columns. */
export interface DateTimeStats {
  earliest?: string | null;
  latest?: string | null;
  range_days?: number | null;
  invalid_count?: number;
}

/** Request to upload an unstructured document for RAG indexing. */
export interface DocumentCreateRequest {
  title: string;
  document_type?: DocumentType;
  file_name: string;
  file_format?: string;
  version_tag?: string;
  raw_text: string;
  metadata_json?: Record<string, unknown> | null;
}

/** Query parameters for RAG retrieval. */
export interface DocumentQueryRequest {
  query_text: string;
  document_type?: DocumentType | null;
  top_k?: number;
}

/** List of retrieved document chunks with retrieval metadata. */
export interface DocumentQueryResponse {
  query_text: string;
  results: DocumentQueryResult[];
  total_retrieved: number;
}

/** Single matching chunk with relevance and provenance. */
export interface DocumentQueryResult {
  chunk_id: string;
  document_id: string;
  document_title: string;
  file_name: string;
  version_tag: string;
  section_heading?: string | null;
  chunk_text: string;
  relevance_score: number;
  is_untrusted?: boolean;
  retrieval_method?: string;
}

/** Document summary with metadata. */
export interface DocumentResponse {
  id: string;
  project_id: string;
  title: string;
  document_type: string;
  file_name: string;
  file_format: string;
  version_tag: string;
  metadata_json?: Record<string, unknown> | null;
  chunk_count?: number;
  created_at: string;
  updated_at: string;
}

/** Business document category for RAG indexing. */
export type DocumentType = 'CONTRACT' | 'PURCHASE_ORDER_TERMS' | 'INVOICE_SUPPORTING' | 'DELIVERY_NOTE' | 'COMMUNICATION' | 'DISPUTE_POLICY';

/** Standardized API error response format across all Corbel endpoints. */
export interface ErrorResponse {
  /** High-level error code or classification */
  error: string;
  /** Human-readable description of the error */
  message: string;
  /** Detailed validation errors or contextual diagnostic data */
  details?: unknown;
  /** Unique correlation identifier for log tracing */
  correlation_id?: string | null;
}

/** Payload to create an AI evaluation regression benchmark dataset. */
export interface EvaluationDatasetCreate {
  name: string;
  version?: string;
  domain?: string;
  /** List of test cases with expected outputs */
  test_cases: Record<string, unknown>[];
  is_system?: boolean;
}

/** Response model for an evaluation benchmark dataset. */
export interface EvaluationDatasetResponse {
  id: string;
  organization_id?: string | null;
  is_system: boolean;
  name: string;
  version: string;
  domain: string;
  test_cases_json: Record<string, unknown>[];
  created_at: string;
}

/** Individual test case score within an evaluation benchmark run. */
export interface EvaluationResultResponse {
  id: string;
  evaluation_run_id: string;
  test_case_id: string;
  metric_name: string;
  score: number;
  passed: boolean;
  diagnostics_json?: Record<string, unknown> | null;
  created_at: string;
}

/** Payload to execute an automated evaluation benchmark suite. */
export interface EvaluationRunRequest {
  evaluation_dataset_id: string;
  target_prompt_version_id?: string | null;
  target_model_name?: string;
}

/** Response model for an evaluation benchmark suite run. */
export interface EvaluationRunResponse {
  id: string;
  organization_id: string;
  evaluation_dataset_id: string;
  target_prompt_version_id?: string | null;
  target_model_name: string;
  status: string;
  started_at?: string | null;
  ended_at?: string | null;
  summary_metrics_json?: Record<string, unknown> | null;
  created_at: string;
  results?: EvaluationResultResponse[];
}

/** Execution outcome status for a monitor evaluation run. */
export type EvaluationStatus = 'SUCCESS' | 'FAILURE' | 'ERROR';

/** Captured investigative evidence item. */
export interface EvidenceResponse {
  id: string;
  project_id: string;
  investigation_id: string;
  evidence_type: EvidenceSourceType;
  source_identifier: string;
  document_name?: string | null;
  dataset_version_id?: string | null;
  section_or_chunk?: string | null;
  content_snippet: string;
  structured_data_json?: Record<string, unknown> | null;
  metadata_json?: Record<string, unknown> | null;
  is_verified_fact: boolean;
  evidence_classification?: string;
  retrieved_at: string;
}

/** Source classification for retrieved investigative evidence. */
export type EvidenceSourceType = 'BUSINESS_RECORD' | 'PROCESS_EVENT' | 'DOCUMENT_CHUNK' | 'ONTOLOGY_RELATION';

/** Dispatch outcome for a target-system adapter execution. */
export type ExecutionStatus = 'QUEUED' | 'DISPATCHING' | 'SUCCEEDED' | 'FAILED' | 'RECONCILIATION_REQUIRED';

/** API response model representing a detected operational exception finding. */
export interface FindingResponse {
  id: string;
  project_id: string;
  monitor_id: string;
  rule_id: string | null;
  process_case_id: string | null;
  entity_type: string | null;
  entity_id: string | null;
  finding_type: string;
  severity: RuleSeverity;
  status: FindingStatus;
  summary: string;
  deduplication_hash: string;
  observed_value: string | null;
  threshold_value: string | null;
  verified_context_json: Record<string, unknown> | null;
  detected_at: string;
  acknowledged_at: string | null;
  acknowledged_by: string | null;
  resolved_at: string | null;
  resolved_by: string | null;
  resolution_notes: string | null;
}

/** Governed lifecycle status for detected operational exceptions. */
export type FindingStatus = 'OPEN' | 'ACKNOWLEDGED' | 'INVESTIGATING' | 'RECOMMENDED' | 'RESOLVED' | 'DISMISSED';

/** Payload to update the lifecycle state of a finding (e.g. acknowledge or resolve). */
export interface FindingStatusUpdate {
  /** Target lifecycle state */
  status: FindingStatus;
  /** Resolution or dismissal rationale */
  resolution_notes?: string | null;
}

export interface HTTPValidationError {
  detail?: ValidationError[];
}

/** Request to initiate an investigation on an operational finding. */
export interface InvestigationCreateRequest {
  finding_id: string;
  title?: string | null;
  include_rag_documents?: boolean;
}

/** Paginated list of investigations. */
export interface InvestigationListResponse {
  items: InvestigationResponse[];
  total: number;
}

/** Complete investigation record with verified facts, hypothesis, and impact. */
export interface InvestigationResponse {
  id: string;
  project_id: string;
  finding_id: string;
  status: InvestigationStatus;
  title: string;
  summary?: string | null;
  verified_facts_json?: Record<string, unknown>[] | null;
  document_extracts_json?: Record<string, unknown>[] | null;
  causal_hypothesis?: string | null;
  missing_evidence_json?: Record<string, unknown>[] | null;
  financial_impact_usd: number;
  created_at: string;
  updated_at: string;
  completed_at?: string | null;
  evidence_count?: number;
  recommendations?: RecommendationResponse[];
  actions?: ActionResponse[];
}

/** Lifecycle state of an analytical investigation. */
export type InvestigationStatus = 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED';

/** Simple liveness probe response for orchestrator checks. */
export interface LivenessResponse {
  /** Process liveness indicator */
  status?: string;
  /** UTC timestamp */
  timestamp: string;
}

/** Lifecycle status of a column-to-property semantic mapping. */
export type MappingStatus = 'SUGGESTED' | 'CONFIRMED' | 'REJECTED';

/** Payload for adding or inviting a user to an organization. */
export interface MemberAddRequest {
  /** Email address of the user to add */
  email: string;
  /** Organization role */
  role?: OrgRole;
}

/** Organization member response model. */
export interface MemberResponse {
  id: string;
  organization_id: string;
  user_id: string;
  email: string;
  full_name: string;
  role: string;
  status: string;
  created_at: string;
}

/** Payload for updating an organization member's role. */
export interface MemberRoleUpdateRequest {
  /** New organization role */
  role: OrgRole;
}

/** Payload for activating, suspending or revoking an organization membership. */
export interface MemberStatusUpdateRequest {
  /** New membership status */
  status: MembershipStatus;
}

/** Lifecycle status of a user's membership within an organization. */
export type MembershipStatus = 'ACTIVE' | 'INVITED' | 'SUSPENDED' | 'REVOKED';

/** Payload to configure a new operational monitor. */
export interface MonitorCreate {
  /** Monitor display name */
  name: string;
  /** Operational scope and purpose */
  description?: string | null;
  /** Target scope: ENTITY or PROCESS */
  target_type?: MonitorTargetType;
  /** Entity name (e.g. PurchaseOrder) or Process UUID */
  target_id: string;
  /** Cron expression for periodic evaluation */
  schedule_cron?: string | null;
  /** Initial monitor state */
  status?: MonitorStatus;
  /** Associated business rules */
  rules?: BusinessRuleCreate[];
}

/** API response model for a monitor evaluation run execution. */
export interface MonitorEvaluationResponse {
  id: string;
  project_id: string;
  monitor_id: string;
  status: EvaluationStatus;
  records_evaluated: number;
  findings_detected: number;
  execution_duration_ms: number;
  summary_json: Record<string, unknown> | null;
  error_message: string | null;
  evaluated_at: string;
}

/** Request payload to trigger on-demand monitor evaluation. */
export interface MonitorEvaluationRunRequest {
  /** Bounded batch evaluation record limit */
  limit?: number;
}

/** API response model representing an operational monitor with rule configurations. */
export interface MonitorResponse {
  id: string;
  project_id: string;
  name: string;
  description: string | null;
  target_type: MonitorTargetType;
  target_id: string;
  schedule_cron: string | null;
  status: MonitorStatus;
  last_run_at: string | null;
  last_status: string | null;
  created_at: string;
  updated_at: string;
  rules?: BusinessRuleResponse[];
  open_findings_count?: number;
  total_findings_count?: number;
}

/** Lifecycle status of an operational monitor. */
export type MonitorStatus = 'ACTIVE' | 'PAUSED';

/** Scope target of an operational monitor. */
export type MonitorTargetType = 'ENTITY' | 'PROCESS';

/** Payload to modify monitor metadata and state. */
export interface MonitorUpdate {
  name?: string | null;
  description?: string | null;
  schedule_cron?: string | null;
  status?: MonitorStatus | null;
}

/** Request to compile a natural language question into a structured query AST. */
export interface NaturalLanguageQueryRequest {
  /** Natural language query string (e.g. 'Show purchase orders exceeding 10000') */
  prompt: string;
  /** Optional hint specifying the target business entity */
  target_entity?: string | null;
}

/** Response containing parsed query AST, compiled SQL, and explanation. */
export interface NaturalLanguageQueryResponse {
  prompt: string;
  parsed_query: StructuredQueryRequest;
  compiled_sql: string;
  explanation: string;
  token_usage: TokenUsage;
  latency_ms: number;
  /** Server-controlled opaque compilation reference for audit attribution */
  nlq_reference: string;
}

/** Statistical summary for numeric columns. */
export interface NumericStats {
  min?: number | null;
  max?: number | null;
  mean?: number | null;
  stddev?: number | null;
  median?: number | null;
  sum?: number | null;
  zeros_count?: number;
}

/** Edge in the ontology graph representing a directed Relationship. */
export interface OntologyGraphEdge {
  id: string;
  name: string;
  source: string;
  target: string;
  cardinality: string;
  join_expression?: Record<string, unknown> | null;
}

/** Node in the ontology graph representing a Business Object. */
export interface OntologyGraphNode {
  id: string;
  name: string;
  display_name: string;
  description?: string | null;
  properties?: PropertyResponse[];
  mapped_properties_count?: number;
  total_properties_count?: number;
}

/** Complete ontology graph representation for interactive rendering. */
export interface OntologyGraphResponse {
  project_id: string;
  nodes: OntologyGraphNode[];
  edges: OntologyGraphEdge[];
  total_objects: number;
  total_relationships: number;
  total_mapped_properties: number;
}

/** Semantically traversable connected paths from a starting Business Object. */
export interface OntologyTraversalResponse {
  start_object_id: string;
  start_object_name: string;
  outgoing_paths?: TraversalStep[];
  incoming_paths?: TraversalStep[];
}

/** Operational ROI and MTTR progression metrics for governed workflows. */
export interface OperationalRoiResponse {
  organization_id: string;
  project_id?: string | null;
  incidents_investigated: number;
  incidents_resolved: number;
  /** Assumed reference baseline MTTR for manual discrepancy resolution (48.0 hours = 2880.0 minutes), not an empirically measured value. */
  baseline_mttr_minutes: number;
  /** Realized average MTTR in minutes from detection to terminal successful execution. */
  current_mttr_minutes: number;
  /** Percentage reduction in MTTR compared to the reference manual baseline. */
  mttr_reduction_percentage: number;
  /** Total financial value protected or recovered across all successfully resolved findings. */
  total_financial_impact_addressed_usd: number;
  /** Cumulative AI inference expenditure across model invocations. */
  total_ai_cost_usd: number;
  /** Average AI cost attributed per successfully completed business task. */
  cost_per_successful_task_usd: number;
  /** Benefit-Cost Ratio (BCR) representing financial value protected divided by total AI cost (value multiple). */
  benefit_cost_ratio: number;
  /** Legacy field alias for benefit_cost_ratio (Benefit-Cost Multiple, not conventional net ROI). */
  financial_roi_ratio: number;
}

/** Organization-level roles defining administrative and governance permissions. */
export type OrgRole = 'ORG_ADMIN' | 'MEMBER' | 'AUDITOR';

/** Lifecycle status of an organization tenant. */
export type OrgStatus = 'ACTIVE' | 'SUSPENDED';

/** Payload for creating a new enterprise tenant organization. */
export interface OrganizationCreateRequest {
  /** Organization legal or business name */
  name: string;
  /** URL-safe unique identifier */
  slug?: string | null;
}

/** Organization metadata schema. */
export interface OrganizationResponse {
  id: string;
  name: string;
  slug: string;
  status: string;
  created_at: string;
}

/** Payload for modifying an organization. */
export interface OrganizationUpdateRequest {
  name?: string | null;
  status?: OrgStatus | null;
}

/** Organization metadata with contextual membership role and status for active user. */
export interface OrganizationWithRoleResponse {
  id: string;
  name: string;
  slug: string;
  status: string;
  role: string;
  membership_status: string;
  created_at: string;
}

/** Trigger parameters for demonstrating the full P2P vertical slice. */
export interface P2PVerticalSliceDemoRequest {
  supplier_name?: string;
  po_number?: string;
  po_amount?: number;
  invoice_number?: string;
  invoice_amount?: number;
  expected_variance?: number;
  auto_approve?: boolean;
}

/** End-to-end outcome of the P2P vertical slice demonstration. */
export interface P2PVerticalSliceDemoResponse {
  finding_id: string;
  investigation_id: string;
  financial_impact_usd: number;
  verified_facts: Record<string, unknown>[];
  causal_hypothesis: string;
  retrieved_document_snippets: string[];
  recommendation: RecommendationResponse;
  action: ActionResponse;
  approval?: ApprovalResponse | null;
  execution?: ActionExecutionResponse | null;
  audit_events_count: number;
}

/** Detailed case representation with full event sequence. */
export interface ProcessCaseDetailResponse {
  case: ProcessCaseSummary;
  events: ProcessEventResponse[];
}

/** Summary of a reconstructed process case instance. */
export interface ProcessCaseSummary {
  id: string;
  process_id: string;
  case_identifier: string;
  variant_key: string;
  status: string;
  started_at: string;
  ended_at: string;
  total_duration_seconds: number;
  event_count: number;
}

/** Paginated list of process cases. */
export interface ProcessCasesListResponse {
  items: ProcessCaseSummary[];
  total: number;
  page: number;
  limit: number;
}

/** Request payload to define a new operational process. */
export interface ProcessCreate {
  /** Process name, e.g. Procure-to-Pay */
  name: string;
  description?: string | null;
  /** Target SLA cycle time in seconds */
  target_duration_seconds?: number | null;
  is_active?: boolean;
}

/** Batch ingestion request containing multiple event items. */
export interface ProcessEventBatchIngestRequest {
  events: ProcessEventIngestItem[];
}

/** Single activity event within a process lifecycle. */
export interface ProcessEventIngestItem {
  case_identifier: string;
  activity_name: string;
  timestamp: string;
  event_type?: string;
  resource?: string | null;
  source_system?: string | null;
  source_record_id?: string | null;
  attributes?: Record<string, unknown> | null;
}

/** Public representation of a single process event. */
export interface ProcessEventResponse {
  id: string;
  activity_name: string;
  timestamp: string;
  event_type: string;
  resource: string | null;
  source_system: string | null;
  source_record_id: string | null;
  attributes?: Record<string, unknown> | null;
}

/** Executive process summary with performance KPIs and bottleneck detection. */
export interface ProcessOverviewResponse {
  process_id: string;
  name: string;
  target_duration_seconds: number | null;
  total_cases: number;
  total_events: number;
  distinct_activities_count: number;
  distinct_variants_count: number;
  avg_cycle_time_seconds: number;
  median_cycle_time_seconds: number;
  min_cycle_time_seconds: number;
  max_cycle_time_seconds: number;
  sla_breach_count: number;
  sla_compliance_rate: number;
  rework_case_count: number;
  rework_rate: number;
  primary_bottleneck: string | null;
}

/** Request payload to reconstruct process cases and variants from datasets. */
export interface ProcessReconstructRequest {
  /** Reconstruction mode: 'P2P_ONTOLOGY' or 'DATASET_MAPPING' */
  mode?: string;
  dataset_id?: string | null;
  case_id_column?: string | null;
  activity_column?: string | null;
  timestamp_column?: string | null;
  resource_column?: string | null;
  attributes_columns?: string[] | null;
}

/** Summary of reconstructed process cases and events. */
export interface ProcessReconstructResponse {
  process_id: string;
  cases_reconstructed: number;
  events_reconstructed: number;
  variants_count: number;
  message: string;
}

/** Public representation of an operational process. */
export interface ProcessResponse {
  id: string;
  project_id: string;
  name: string;
  description: string | null;
  target_duration_seconds: number | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  case_count?: number;
  event_count?: number;
}

/** Request payload to update an existing process. */
export interface ProcessUpdate {
  name?: string | null;
  description?: string | null;
  target_duration_seconds?: number | null;
  is_active?: boolean | null;
}

/** Statistical summary of a distinct process path / variant. */
export interface ProcessVariantItem {
  variant_key: string;
  activities: string[];
  case_count: number;
  frequency_percentage: number;
  avg_duration_seconds: number;
  median_duration_seconds: number;
  min_duration_seconds: number;
  max_duration_seconds: number;
  is_happy_path: boolean;
}

/** Discovered process variants ranked by execution frequency. */
export interface ProcessVariantsResponse {
  process_id: string;
  variants: ProcessVariantItem[];
  total_variants: number;
}

/** Deterministic profile summary for an entire dataset version. */
export interface ProfilingSummary {
  total_rows: number;
  total_columns: number;
  duplicate_rows_count: number;
  duplicate_rows_pct: number;
  columns: ColumnProfile[];
  dataset_quality_warnings?: string[];
  profiled_at?: string;
}

/** Payload for creating a project workspace within an organization. */
export interface ProjectCreateRequest {
  /** Project workspace name */
  name: string;
  /** URL-safe unique project slug */
  slug?: string | null;
  /** Optional workspace description */
  description?: string | null;
}

/** Payload for assigning an organization user to a project. */
export interface ProjectMemberAddRequest {
  /** User ID belonging to the same Organization */
  user_id: string;
  /** Project-scoped role */
  project_role?: ProjectRole;
}

/** Project member response schema. */
export interface ProjectMemberResponse {
  id: string;
  organization_id: string;
  project_id: string;
  user_id: string;
  email: string;
  full_name: string;
  project_role: string;
  granted_at: string;
}

/** Project workspace response schema. */
export interface ProjectResponse {
  id: string;
  organization_id: string;
  name: string;
  slug: string;
  description: string | null;
  status: string;
  created_at: string;
}

/** Project-scoped roles defining analytical and execution permissions. */
export type ProjectRole = 'PROJECT_LEAD' | 'ANALYST' | 'OPERATOR' | 'APPROVER' | 'VIEWER' | 'AUDITOR';

/** Operational status of a project workspace. */
export type ProjectStatus = 'ACTIVE' | 'ARCHIVED';

/** Payload for updating project workspace metadata. */
export interface ProjectUpdateRequest {
  name?: string | null;
  description?: string | null;
  status?: ProjectStatus | null;
}

/** Payload to create a logical prompt definition asset. */
export interface PromptDefinitionCreate {
  /** Unique prompt asset name */
  name: string;
  /** Target workflow (e.g. 'DATA_DISCOVERY', 'INVESTIGATION') */
  workflow_association: string;
  description?: string | null;
  /** Whether this is a platform-wide system baseline */
  is_system?: boolean;
  /** Optional initial prompt version */
  initial_version?: PromptVersionCreate | null;
}

/** Response model for a logical prompt definition asset. */
export interface PromptDefinitionResponse {
  id: string;
  organization_id?: string | null;
  is_system: boolean;
  name: string;
  workflow_association: string;
  description?: string | null;
  owner_user_id?: string | null;
  created_at: string;
  updated_at: string;
  versions?: PromptVersionResponse[];
}

/** Formal lifecycle progression for immutable prompt versions. */
export type PromptLifecycleState = 'DRAFT' | 'TEST' | 'EVALUATE' | 'APPROVE' | 'DEPLOY' | 'MONITOR' | 'RETIRE';

/** Payload to transition a prompt version through its formal lifecycle. */
export interface PromptLifecycleTransitionRequest {
  /** Target lifecycle state */
  target_state: PromptLifecycleState;
  /** Justification or review notes */
  rationale?: string | null;
}

/** Payload to restore production prompt deployment reference to a prior immutable version. */
export interface PromptRollbackRequest {
  /** Previously approved version tag to restore as active DEPLOY */
  target_version_tag: string;
  /** Rollback reason or regression note */
  rationale?: string | null;
}

/** Payload to create an immutable version iteration of a prompt definition. */
export interface PromptVersionCreate {
  /** Semantic version tag (e.g., '1.0.0') */
  version_tag: string;
  /** Prompt template text with optional {variables} */
  template_text: string;
  /** Target model compatibility */
  model_compatibility?: string;
  token_budget_input?: number;
  token_budget_output?: number;
  /** Pydantic schema dict for input */
  input_schema_json?: Record<string, unknown> | null;
  /** Pydantic schema dict for output */
  output_schema_json?: Record<string, unknown> | null;
}

/** Response model for an immutable prompt version. */
export interface PromptVersionResponse {
  id: string;
  prompt_definition_id: string;
  version_tag: string;
  lifecycle_state: string;
  model_compatibility: string;
  token_budget_input: number;
  token_budget_output: number;
  template_text: string;
  input_schema_json?: Record<string, unknown> | null;
  output_schema_json?: Record<string, unknown> | null;
  created_by?: string | null;
  approved_by?: string | null;
  approved_at?: string | null;
  created_at: string;
}

/** Schema for adding a Property to a Business Object. */
export interface PropertyCreateRequest {
  /** Technical property name */
  name: string;
  /** Human-readable title */
  display_name?: string | null;
  /** Attribute data type */
  data_type?: PropertyType;
  /** Whether attribute can contain null values */
  is_nullable?: boolean;
  /** Whether attribute forms the primary key */
  is_primary_key?: boolean;
  /** Documentation notes */
  description?: string | null;
}

/** Schema for creating an explicit or accepted column-to-property mapping. */
export interface PropertyMappingCreateRequest {
  /** Target Property ID */
  property_id: string;
  /** Source Dataset ID */
  dataset_id: string;
  /** Source Dataset Version ID */
  dataset_version_id: string;
  /** Source column name */
  column_name: string;
  /** Match confidence */
  confidence?: number;
  /** Initial status */
  status?: MappingStatus;
  explanation?: string | null;
}

/** Public representation of a column-to-property mapping. */
export interface PropertyMappingResponse {
  id: string;
  project_id: string;
  property_id: string;
  property_name?: string | null;
  business_object_id?: string | null;
  business_object_name?: string | null;
  dataset_id: string;
  dataset_name?: string | null;
  dataset_version_id: string;
  column_name: string;
  confidence: number;
  status: string;
  explanation?: string | null;
  created_at: string;
}

/** Public representation of an ontology property. */
export interface PropertyResponse {
  id: string;
  business_object_id: string;
  name: string;
  display_name?: string | null;
  data_type: string;
  is_nullable: boolean;
  is_primary_key: boolean;
  description?: string | null;
  source_mapping?: Record<string, unknown> | null;
  created_at: string;
}

/** Supported business data types for ontology properties. */
export type PropertyType = 'STRING' | 'NUMBER' | 'DATETIME' | 'BOOLEAN' | 'ENUM';

/** Schema for modifying an existing Property. */
export interface PropertyUpdateRequest {
  display_name?: string | null;
  data_type?: PropertyType | null;
  is_nullable?: boolean | null;
  is_primary_key?: boolean | null;
  description?: string | null;
}

/** Audit record of a structured query execution. */
export interface QueryExecutionAuditResponse {
  id: string;
  project_id: string;
  user_id: string;
  entity_name: string;
  query_ast: Record<string, unknown>;
  compiled_sql: string;
  row_count: number;
  execution_time_ms: number;
  is_nlq: boolean;
  nlq_prompt: string | null;
  token_count: number | null;
  created_at: string;
}

/** Atomic filter condition on a business object property. */
export interface QueryFilter {
  /** Property name to filter on (e.g., 'total_amount', 'status') */
  field: string;
  /** Comparison operator */
  operator?: QueryOperator;
  /** Filter operand value */
  value?: unknown;
}

/** Relationship traversal specification for querying across connected entities. */
export interface QueryJoin {
  /** Name of the confirmed relationship to traverse */
  relationship_name: string;
  /** Properties to project from the joined entity */
  fields?: string[];
}

/** Supported filter operators for structured query AST. */
export type QueryOperator = 'eq' | 'neq' | 'gt' | 'gte' | 'lt' | 'lte' | 'contains' | 'starts_with' | 'ends_with' | 'in' | 'not_in' | 'is_null' | 'is_not_null';

/** Full project ontology query schema describing all queryable entities and properties. */
export interface QuerySchemaResponse {
  project_id: string;
  entities: QueryableEntitySchema[];
}

/** Ordering specification for structured queries. */
export interface QuerySort {
  /** Property name to sort by */
  field: string;
  /** Sort direction: asc or desc */
  direction?: SortDirection;
}

/** Metadata describing an entity available for querying. */
export interface QueryableEntitySchema {
  id: string;
  name: string;
  display_name: string;
  description: string | null;
  properties: QueryablePropertySchema[];
  available_relationships: string[];
}

/** Metadata describing a queryable entity property. */
export interface QueryablePropertySchema {
  name: string;
  display_name: string | null;
  data_type: string;
  is_primary_key: boolean;
  is_nullable: boolean;
  is_mapped: boolean;
  source_column: string | null;
}

/** Structured proposal produced by an investigation. */
export interface RecommendationResponse {
  id: string;
  investigation_id: string;
  title: string;
  description: string;
  confidence_score: number;
  risk_level: RiskLevel;
  recommended_action_type: ActionType;
  suggested_payload_json: Record<string, unknown>;
  created_at: string;
}

/** Payload for refreshing an expired access token. */
export interface RefreshTokenRequest {
  /** Valid cryptographically signed refresh token */
  refresh_token: string;
  /** Optional client-generated idempotency key for safe retry and concurrent deduplication */
  idempotency_key?: string | null;
}

/** Cardinality of directed semantic relationships connecting business objects. */
export type RelationshipCardinality = 'ONE_TO_ONE' | 'ONE_TO_MANY' | 'MANY_TO_ONE' | 'MANY_TO_MANY';

/** Schema for creating a directed relationship between Business Objects. */
export interface RelationshipCreateRequest {
  /** Relationship verb (e.g. billed_in) */
  name: string;
  /** Source Business Object ID */
  source_object_id: string;
  /** Target Business Object ID */
  target_object_id: string;
  /** Multiplicity of the connection */
  cardinality?: RelationshipCardinality;
  description?: string | null;
  /** Join keys, e.g. {'source_property': 'po_id', 'target_property': 'po_id'} */
  join_expression?: Record<string, unknown> | null;
}

/** Public representation of an ontology relationship. */
export interface RelationshipResponse {
  id: string;
  project_id: string;
  name: string;
  source_object_id: string;
  source_object_name?: string | null;
  target_object_id: string;
  target_object_name?: string | null;
  cardinality: string;
  description?: string | null;
  join_expression?: Record<string, unknown> | null;
  created_at: string;
}

/** Risk rating for a proposed remedial action. */
export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH';

/** Deterministic comparison operators for business rule conditions. */
export type RuleOperator = 'gt' | 'gte' | 'lt' | 'lte' | 'eq' | 'neq';

/** Business impact severity classification for rules and findings. */
export type RuleSeverity = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

/** Parameters for running deterministic semantic discovery against a dataset version. */
export interface SemanticDiscoveryRequest {
  /** Dataset ID to inspect */
  dataset_id: string;
  /** Dataset Version snapshot ID */
  dataset_version_id: string;
  /** Target Business Object to map against */
  business_object_id: string;
}

/** Results of a deterministic semantic discovery run. */
export interface SemanticDiscoveryResponse {
  dataset_id: string;
  dataset_version_id: string;
  business_object_id: string;
  business_object_name: string;
  suggestions?: PropertyMappingResponse[];
  total_suggested?: number;
}

/** Sort direction for query ordering. */
export type SortDirection = 'asc' | 'desc';

/** Supported data source connector types. */
export type SourceType = 'FILE_INGEST' | 'POSTGRES' | 'MYSQL' | 'SNOWFLAKE';

/** Execution summary returned by a bounded state machine. */
export interface StateMachineResult {
  workflow_id: string;
  workflow_type: string;
  status: string;
  steps_executed: number;
  tokens_consumed: number;
  cost_usd: number;
  final_state: string;
  result_data: Record<string, unknown>;
  verified_facts?: Record<string, unknown>[];
  hypotheses?: string[];
}

/** Statistical summary for textual string columns. */
export interface StringStats {
  min_length?: number | null;
  max_length?: number | null;
  avg_length?: number | null;
}

/** Strongly typed query AST representing a validated semantic query. */
export interface StructuredQueryRequest {
  /** Target business entity name (e.g., 'PurchaseOrder') */
  entity_name: string;
  /** List of property names to select (empty selects all mapped properties) */
  fields?: string[];
  /** Filter conditions evaluated with logical AND conjunction */
  filters?: QueryFilter[];
  /** Ordering criteria */
  sorts?: QuerySort[];
  /** Optional relationship traversal joins */
  joins?: QueryJoin[];
  /** Maximum number of rows to return (capped at 500) */
  limit?: number;
  /** Number of rows to skip for pagination */
  offset?: number;
  /** Optional server-issued NLQ compilation reference for execution audit attribution */
  nlq_reference?: string | null;
}

/** Tabular query execution results with safety audit metadata. */
export interface StructuredQueryResponse {
  entity_name: string;
  columns: string[];
  rows: Record<string, unknown>[];
  total_count: number;
  limit: number;
  offset: number;
  compiled_sql: string;
  parameters: unknown[];
  execution_time_ms: number;
  query_plan: string[];
}

/** Comprehensive system health model returned by the health check endpoint. */
export interface SystemHealthResponse {
  /** Overall platform status: healthy, degraded, or unhealthy */
  status: string;
  /** Application name */
  app_name: string;
  /** Semantic application version */
  version: string;
  /** Current deployment environment */
  environment: string;
  /** UTC timestamp of the health check evaluation */
  timestamp: string;
  /** PostgreSQL connectivity health check */
  database: DatabaseHealth;
}

/** Request payload to create and schedule a durable background task. */
export interface TaskCreate {
  /** Category of background work to perform */
  task_type: TaskType;
  /** Optional input payload or configuration for the task */
  input_data?: Record<string, unknown> | null;
  /** Maximum retry attempts on transient failure */
  max_retries?: number;
}

/** Response model for a durable background task execution. */
export interface TaskResponse {
  id: string;
  project_id: string;
  task_type: string;
  status: string;
  worker_id?: string | null;
  lease_expires_at?: string | null;
  last_heartbeat_at?: string | null;
  lease_generation?: number;
  retry_count: number;
  max_retries: number;
  checkpoint_data_json?: Record<string, unknown> | null;
  cancellation_requested: boolean;
  started_at?: string | null;
  ended_at?: string | null;
  error_diagnostics_json?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

/** Operational categories of durable background tasks. */
export type TaskType = 'DATASET_IMPORT' | 'SCHEMA_PROFILING' | 'WORKFLOW_RUN' | 'MONITOR_SWEEP' | 'EVALUATION_RUN';

/** OAuth2 / JWT compatible token response. */
export interface TokenResponse {
  /** Signed JWT access token */
  access_token: string;
  /** Signed JWT refresh token */
  refresh_token: string;
  /** Token type */
  token_type?: string;
  /** Access token expiration window in seconds */
  expires_in: number;
}

/** Token consumption metrics for an AI model invocation, including provider-native prompt caching. */
export interface TokenUsage {
  /** Input prompt tokens consumed */
  prompt_tokens?: number;
  /** Completion tokens produced */
  completion_tokens?: number;
  /** Cached prompt tokens leveraged (Level 1 caching) */
  cached_tokens?: number;
  /** Total tokens consumed */
  total_tokens?: number;
}

/** One step in an ontology graph traversal. */
export interface TraversalStep {
  relationship_id: string;
  relationship_name: string;
  cardinality: string;
  target_object_id: string;
  target_object_name: string;
  join_expression?: Record<string, unknown> | null;
}

/** Payload for user authentication. */
export interface UserLoginRequest {
  /** Registered email address */
  email: string;
  /** User password */
  password: string;
}

/** Payload for registering a new user. */
export interface UserRegisterRequest {
  /** User corporate or standard email address */
  email: string;
  /** Plaintext password (8-72 bytes) */
  password: string;
  /** Full human name */
  full_name: string;
}

/** Public user profile model (never leaks password hashes). */
export interface UserResponse {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  created_at: string;
}

export interface ValidationError {
  loc: (string | number)[];
  msg: string;
  type: string;
  input?: unknown;
  ctx?: Record<string, unknown>;
}

/** Response model for an analytical state machine execution. */
export interface WorkflowExecutionResponse {
  id: string;
  project_id: string;
  task_execution_id?: string | null;
  workflow_type: string;
  workflow_version: string;
  status: string;
  current_state: string;
  step_count: number;
  max_steps: number;
  token_budget: number;
  cost_budget_usd: number;
  input_parameters_json?: Record<string, unknown> | null;
  state_data_json?: Record<string, unknown> | null;
  result_data_json?: Record<string, unknown> | null;
  parent_execution_id?: string | null;
  started_at?: string | null;
  ended_at?: string | null;
  created_at: string;
  updated_at: string;
}

/** Request payload to execute a bounded state machine workflow. */
export interface WorkflowRunRequest {
  /** Type of state machine workflow to execute */
  workflow_type: WorkflowType;
  /** Input parameters and initial context for the workflow */
  input_parameters: Record<string, unknown>;
  /** Hard bound on state machine iteration steps */
  max_steps?: number;
  /** Maximum token consumption limit */
  token_budget?: number;
  /** Maximum expenditure budget in USD */
  cost_budget_usd?: number;
}

/** Predefined bounded state machine workflow types. */
export type WorkflowType = 'DATA_DISCOVERY' | 'PROCESS_MINING' | 'INVESTIGATION' | 'RULE_GENERATION';
