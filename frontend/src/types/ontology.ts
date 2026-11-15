export type PropertyType = 'STRING' | 'NUMBER' | 'DATETIME' | 'BOOLEAN' | 'ENUM'

export type RelationshipCardinality = 'ONE_TO_ONE' | 'ONE_TO_MANY' | 'MANY_TO_ONE' | 'MANY_TO_MANY'

export type MappingStatus = 'SUGGESTED' | 'CONFIRMED' | 'REJECTED'

export interface Property {
  id: string
  business_object_id: string
  name: string
  display_name?: string | null
  data_type: PropertyType
  is_nullable: boolean
  is_primary_key: boolean
  description?: string | null
  source_mapping?: {
    dataset_id: string
    dataset_version_id: string
    column_name: string
    confidence: number
    status: MappingStatus
    explanation?: string | null
  } | null
  created_at: string
}

export interface BusinessObject {
  id: string
  project_id: string
  name: string
  display_name: string
  description?: string | null
  primary_key_property?: string | null
  version: number
  property_count: number
  created_at: string
  updated_at: string
  properties?: Property[]
}

export interface Relationship {
  id: string
  project_id: string
  name: string
  source_object_id: string
  source_object_name?: string | null
  target_object_id: string
  target_object_name?: string | null
  cardinality: RelationshipCardinality
  description?: string | null
  join_expression?: Record<string, unknown> | null
  created_at: string
}

export interface PropertyMapping {
  id: string
  project_id: string
  property_id: string
  property_name?: string | null
  business_object_id?: string | null
  business_object_name?: string | null
  dataset_id: string
  dataset_name?: string | null
  dataset_version_id: string
  column_name: string
  confidence: number
  status: MappingStatus
  explanation?: string | null
  created_at: string
}

export interface SemanticDiscoveryResponse {
  dataset_id: string
  dataset_version_id: string
  business_object_id: string
  business_object_name: string
  suggestions: PropertyMapping[]
  total_suggested: number
}

export interface OntologyGraphNode {
  id: string
  name: string
  display_name: string
  description?: string | null
  properties: Property[]
  mapped_properties_count: number
  total_properties_count: number
}

export interface OntologyGraphEdge {
  id: string
  name: string
  source: string
  target: string
  cardinality: string
  join_expression?: Record<string, unknown> | null
}

export interface OntologyGraphResponse {
  project_id: string
  nodes: OntologyGraphNode[]
  edges: OntologyGraphEdge[]
  total_objects: number
  total_relationships: number
  total_mapped_properties: number
}

export interface TraversalStep {
  relationship_id: string
  relationship_name: string
  cardinality: string
  target_object_id: string
  target_object_name: string
  join_expression?: Record<string, unknown> | null
}

export interface OntologyTraversalResponse {
  start_object_id: string
  start_object_name: string
  outgoing_paths: TraversalStep[]
  incoming_paths: TraversalStep[]
}
