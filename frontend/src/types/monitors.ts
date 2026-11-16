export type MonitorTargetType = 'ENTITY' | 'PROCESS' | 'SYSTEM'
export type MonitorStatus = 'ACTIVE' | 'PAUSED'
export type RuleSeverity = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
export type RuleOperator = 'gt' | 'gte' | 'lt' | 'lte' | 'eq' | 'neq'
export type FindingStatus =
  | 'OPEN'
  | 'ACKNOWLEDGED'
  | 'INVESTIGATING'
  | 'RECOMMENDED'
  | 'RESOLVED'
  | 'DISMISSED'
export type EvaluationStatus = 'PENDING' | 'RUNNING' | 'SUCCESS' | 'WARNING' | 'ERROR'

export interface BusinessRule {
  id: string
  monitor_id: string
  rule_code: string
  description?: string | null
  severity: RuleSeverity
  rule_type: string
  field_name: string
  operator: RuleOperator
  threshold_value?: number | null
  threshold_string?: string | null
  secondary_field?: string | null
  parameters_json?: Record<string, unknown> | null
  created_at: string
  updated_at: string
}

export interface BusinessRuleCreate {
  rule_code: string
  description?: string | null
  severity?: RuleSeverity
  rule_type?: string
  field_name: string
  operator: RuleOperator
  threshold_value?: number | null
  threshold_string?: string | null
  secondary_field?: string | null
  parameters_json?: Record<string, unknown> | null
}

export interface Monitor {
  id: string
  project_id: string
  name: string
  description?: string | null
  target_type: MonitorTargetType
  target_id: string
  schedule_cron?: string | null
  status: MonitorStatus
  last_run_at?: string | null
  last_status?: string | null
  created_at: string
  updated_at: string
  rules: BusinessRule[]
  open_findings_count: number
  total_findings_count: number
}

export interface MonitorCreate {
  name: string
  description?: string | null
  target_type: MonitorTargetType
  target_id: string
  schedule_cron?: string | null
  status?: MonitorStatus
  rules?: BusinessRuleCreate[]
}

export interface MonitorUpdate {
  name?: string | null
  description?: string | null
  schedule_cron?: string | null
  status?: MonitorStatus | null
}

export interface Finding {
  id: string
  project_id: string
  monitor_id: string
  rule_id: string
  process_case_id?: string | null
  entity_type: string
  entity_id: string
  finding_type: string
  severity: RuleSeverity
  status: FindingStatus
  summary: string
  deduplication_hash: string
  observed_value?: string | null
  threshold_value?: string | null
  verified_context_json?: Record<string, unknown> | null
  detected_at: string
  acknowledged_at?: string | null
  acknowledged_by?: string | null
  resolved_at?: string | null
  resolved_by?: string | null
  resolution_notes?: string | null
  rule?: BusinessRule | null
}

export interface FindingStatusUpdate {
  status: FindingStatus
  resolution_notes?: string | null
}

export interface MonitorEvaluation {
  id: string
  project_id: string
  monitor_id: string
  status: EvaluationStatus
  records_evaluated: number
  findings_detected: number
  execution_duration_ms: number
  summary_json?: Record<string, unknown> | null
  error_message?: string | null
  evaluated_at: string
}
