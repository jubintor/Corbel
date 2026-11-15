export type QueryOperator =
  | 'eq'
  | 'neq'
  | 'gt'
  | 'gte'
  | 'lt'
  | 'lte'
  | 'contains'
  | 'starts_with'
  | 'ends_with'
  | 'in'
  | 'not_in'
  | 'is_null'
  | 'is_not_null'

export type SortDirection = 'asc' | 'desc'

export interface QueryFilter {
  field: string
  operator: QueryOperator
  value?: unknown
}

export interface QuerySort {
  field: string
  direction: SortDirection
}

export interface QueryJoin {
  relationship_name: string
  fields: string[]
}

export interface StructuredQueryRequest {
  entity_name: string
  fields: string[]
  filters: QueryFilter[]
  sorts: QuerySort[]
  joins?: QueryJoin[]
  limit: number
  offset: number
  nlq_reference?: string
}

export interface StructuredQueryResponse {
  entity_name: string
  columns: string[]
  rows: Record<string, unknown>[]
  total_count: number
  limit: number
  offset: number
  compiled_sql: string
  parameters: unknown[]
  execution_time_ms: number
  query_plan: string[]
}

export interface NaturalLanguageQueryRequest {
  prompt: string
  target_entity?: string
}

export interface NaturalLanguageQueryResponse {
  prompt: string
  parsed_query: StructuredQueryRequest
  compiled_sql: string
  explanation: string
  token_usage: {
    prompt_tokens: number
    completion_tokens: number
    total_tokens: number
    cached_tokens?: number
  }
  latency_ms: number
  nlq_reference: string
}

export interface QueryablePropertySchema {
  name: string
  display_name?: string | null
  data_type: string
  is_primary_key: boolean
  is_nullable: boolean
  is_mapped: boolean
  source_column?: string | null
}

export interface QueryableEntitySchema {
  name: string
  display_name: string
  description?: string | null
  properties: QueryablePropertySchema[]
  available_relationships: string[]
}

export interface QuerySchemaResponse {
  project_id: string
  entities: QueryableEntitySchema[]
}

export interface QueryExecutionAuditResponse {
  id: string
  project_id: string
  user_id: string
  entity_name: string
  query_ast: StructuredQueryRequest
  compiled_sql: string
  row_count: number
  execution_time_ms: number
  is_nlq: boolean
  nlq_prompt?: string | null
  token_count?: number | null
  created_at: string
}
