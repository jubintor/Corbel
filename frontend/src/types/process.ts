export interface Process {
  id: string
  project_id: string
  name: string
  description?: string | null
  target_duration_seconds?: number | null
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface ProcessCreateRequest {
  name: string
  description?: string
  target_duration_seconds?: number
  is_active?: boolean
}

export interface BottleneckSummary {
  from_activity: string
  to_activity: string
  avg_duration_seconds: number
  transition_count: number
  is_bottleneck: boolean
}

export interface ProcessOverview {
  process_id: string
  process_name: string
  total_cases: number
  total_events: number
  distinct_variants: number
  avg_duration_seconds: number
  median_duration_seconds: number
  min_duration_seconds: number
  max_duration_seconds: number
  sla_breach_count: number
  sla_breach_rate: number
  rework_case_count: number
  rework_case_rate: number
  top_bottleneck?: BottleneckSummary | null
}

export interface ProcessVariant {
  variant_key: string
  activities: string[]
  case_count: number
  percentage_of_total: number
  avg_duration_seconds: number
  median_duration_seconds: number
  is_happy_path: boolean
}

export interface ProcessVariantsResponse {
  process_id: string
  total_variants: number
  happy_path_variant?: string | null
  variants: ProcessVariant[]
}

export interface DFGNode {
  id: string
  name: string
  total_occurrences: number
  is_start_activity: boolean
  is_end_activity: boolean
}

export interface DFGEdge {
  source: string
  target: string
  transition_count: number
  avg_duration_seconds: number
  median_duration_seconds: number
  min_duration_seconds: number
  max_duration_seconds: number
  is_rework_loop: boolean
  is_bottleneck: boolean
}

export interface DFGResponse {
  process_id: string
  nodes: DFGNode[]
  edges: DFGEdge[]
  total_transitions: number
  bottleneck_count: number
}

export interface ProcessCaseItem {
  id: string
  case_identifier: string
  variant_key: string
  status: string
  started_at: string
  ended_at: string
  total_duration_seconds: number
  event_count: number
}

export interface ProcessCaseListResponse {
  total: number
  page: number
  page_size: number
  items: ProcessCaseItem[]
}

export interface ProcessEventItem {
  id: string
  activity_name: string
  timestamp: string
  event_type: string
  resource?: string | null
  source_system?: string | null
  source_record_id?: string | null
  attributes_json: Record<string, any>
}

export interface ProcessCaseDetailResponse {
  case: ProcessCaseItem
  events: ProcessEventItem[]
}

export interface ProcessReconstructRequest {
  mode: 'P2P_ONTOLOGY' | 'DATASET_MAPPING'
  dataset_id?: string
  case_id_column?: string
  activity_column?: string
  timestamp_column?: string
  resource_column?: string
}

export interface ProcessReconstructResponse {
  process_id: string
  cases_reconstructed: number
  events_reconstructed: number
  variants_discovered: number
  execution_time_ms: number
}
