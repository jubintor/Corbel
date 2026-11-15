/**
 * TypeScript types for Data Intelligence & Profiling (Phase 3).
 */

export interface ColumnSchema {
  name: string
  data_type: string
  nullable: boolean
  sample_values: any[]
}

export interface NumericStats {
  min: number | null
  max: number | null
  mean: number | null
  stddev: number | null
  median: number | null
  sum: number | null
  zeros_count: number
}

export interface DateTimeStats {
  earliest: string | null
  latest: string | null
  range_days: number | null
  invalid_count: number
}

export interface StringStats {
  min_length: number | null
  max_length: number | null
  avg_length: number | null
}

export interface ColumnProfile {
  column_name: string
  detected_type: string
  total_count: number
  null_count: number
  non_null_count: number
  null_percentage: number
  distinct_count: number
  unique_percentage: number
  sample_values: any[]
  numeric_stats?: NumericStats | null
  datetime_stats?: DateTimeStats | null
  string_stats?: StringStats | null
  quality_warnings: string[]
}

export interface ProfilingSummary {
  total_rows: number
  total_columns: number
  duplicate_rows_count: number
  duplicate_rows_pct: number
  columns: ColumnProfile[]
  dataset_quality_warnings: string[]
  profiled_at: string
}

export interface DatasetVersion {
  id: string
  dataset_id: string
  project_id: string
  version_number: number
  file_format: string
  file_size_bytes: number
  checksum_hash: string
  record_count: number | null
  column_count: number | null
  status: 'UPLOADED' | 'PROFILING' | 'READY' | 'FAILED'
  error_message?: string | null
  schema_metadata?: ColumnSchema[] | null
  profiling_summary?: ProfilingSummary | null
  imported_at: string
}

export interface Dataset {
  id: string
  project_id: string
  data_source_id: string
  name: string
  description?: string | null
  status: 'PENDING' | 'READY' | 'PROFILED' | 'ERROR'
  created_at: string
  updated_at: string
  latest_version?: DatasetVersion | null
  version_count: number
}

export interface DatasetPreview {
  dataset_id: string
  version_number: number
  columns: string[]
  rows: Record<string, any>[]
  total_preview_rows: number
}
