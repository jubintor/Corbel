export type InvestigationStatus = 'PENDING' | 'IN_PROGRESS' | 'COMPLETED' | 'FAILED' | 'REJECTED'
export type EvidenceSourceType =
  | 'TRANSACTIONAL_FACT'
  | 'DOCUMENT_CHUNK'
  | 'CAUSAL_HYPOTHESIS'
  | 'MISSING_DATA'
export type DocumentType =
  | 'CONTRACT'
  | 'INVOICE'
  | 'PURCHASE_ORDER'
  | 'RECEIPT'
  | 'POLICY'
  | 'COMMUNICATION'
  | 'OTHER'
export type ActionType =
  | 'HOLD_INVOICE'
  | 'REQUEST_CREDIT_MEMO'
  | 'FLAG_SUPPLIER_REVIEW'
  | 'CUSTOM'
export type ActionStatus =
  | 'PROPOSED'
  | 'AWAITING_APPROVAL'
  | 'APPROVED'
  | 'REJECTED'
  | 'EXECUTING'
  | 'EXECUTED'
  | 'FAILED'
export type ApprovalStatus = 'PENDING' | 'APPROVED' | 'REJECTED' | 'EXPIRED' | 'CANCELLED'
export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
export type ActorType = 'USER' | 'SYSTEM' | 'AI_AGENT'

export interface InvestigationEvidence {
  id: string
  investigation_id: string
  evidence_type: EvidenceSourceType
  evidence_classification?: 'TRANSACTION_FACT' | 'DOCUMENT_EXTRACT' | 'AI_HYPOTHESIS'
  source_uri: string
  title: string
  content_snippet: string
  confidence_score: number
  is_verified_fact: boolean
  metadata_json?: Record<string, unknown> | null
  retrieved_at: string
}

export interface Document {
  id: string
  project_id: string
  title: string
  document_type: DocumentType
  file_name: string
  file_format: string
  version_tag?: string | null
  chunk_count: number
  created_at: string
}

export interface DocumentCreateRequest {
  title: string
  document_type: DocumentType
  file_name: string
  file_format?: string
  version_tag?: string
  raw_text: string
  metadata_json?: Record<string, unknown>
}

export interface DocumentQueryResultItem {
  chunk_id: string
  document_id: string
  document_title: string
  file_name: string
  version_tag?: string
  section_header?: string
  chunk_index: number
  chunk_text: string
  relevance_score: number
  retrieval_method?: string
}

export interface DocumentQueryResponse {
  query_text: string
  results: DocumentQueryResultItem[]
  total_retrieved: number
}

export interface Approval {
  id: string
  action_id: string
  assigned_role: string
  decided_by_user_id?: string | null
  status: ApprovalStatus
  approved_payload_hash?: string | null
  approved_payload_json?: Record<string, unknown> | null
  decision_rationale?: string | null
  decided_at?: string | null
  expires_at?: string | null
  created_at: string
}

export interface Action {
  id: string
  project_id: string
  recommendation_id: string
  action_type: ActionType
  target_system: string
  proposed_payload_json: Record<string, unknown>
  is_consequential: boolean
  status: ActionStatus
  created_at: string
  updated_at: string
  approvals?: Approval[]
}

export interface ActionExecution {
  id: string
  action_id: string
  approval_id: string
  idempotency_key: string
  target_adapter_type: string
  status: string
  attempt_count: number
  dispatched_payload_hash: string
  adapter_response_json?: Record<string, unknown> | null
  error_message?: string | null
  dispatched_at: string
  completed_at?: string | null
}

export interface Recommendation {
  id: string
  investigation_id: string
  title: string
  description: string
  confidence_score: number
  risk_level: RiskLevel
  recommended_action_type: ActionType
  suggested_payload_json: Record<string, unknown>
  created_at: string
  actions?: Action[]
}

export interface Investigation {
  id: string
  project_id: string
  finding_id: string
  title: string
  status: InvestigationStatus
  verified_facts_json?: Array<Record<string, unknown>> | null
  document_extracts_json?: Array<Record<string, unknown>> | null
  causal_hypothesis?: string | null
  missing_evidence_json?: Array<Record<string, unknown>> | null
  financial_impact_usd: number
  created_at: string
  updated_at: string
  completed_at?: string | null
  evidence_count: number
  evidence_items?: InvestigationEvidence[]
  recommendations: Recommendation[]
}

export interface AuditEvent {
  id: string
  organization_id: string
  project_id?: string | null
  actor_type: ActorType
  actor_id: string
  action_type: string
  affected_entity_type: string
  affected_entity_id: string
  execution_context_json?: Record<string, unknown> | null
  outcome_status: string
  timestamp: string
}

export interface P2PVerticalSliceDemoRequest {
  supplier_name?: string
  po_number?: string
  po_amount?: number
  invoice_number?: string
  invoice_amount?: number
  expected_variance?: number
  auto_approve?: boolean
}

export interface P2PVerticalSliceDemoResponse {
  finding_id: string
  investigation_id: string
  financial_impact_usd: number
  verified_facts: Array<Record<string, unknown>>
  causal_hypothesis: string
  retrieved_document_snippets: string[]
  recommendation: Recommendation
  action: Action
  approval?: Approval | null
  execution?: ActionExecution | null
  audit_events_count: number
}
