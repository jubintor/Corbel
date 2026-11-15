/**
 * Authentication and Multi-Tenancy types matching backend Pydantic schemas.
 */

export type OrgRole = 'ORG_ADMIN' | 'MEMBER' | 'AUDITOR'
export type MembershipStatus = 'ACTIVE' | 'INVITED' | 'SUSPENDED' | 'REVOKED'
export type ProjectRole = 'PROJECT_LEAD' | 'ANALYST' | 'VIEWER'

export interface User {
  id: string
  email: string
  full_name: string
  is_active: boolean
  is_superuser?: boolean
  created_at: string
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

export interface Organization {
  id: string
  name: string
  slug: string
  status: string
  created_at: string
}

export interface OrganizationWithRole {
  id: string
  name: string
  slug: string
  status: string
  role: OrgRole
  membership_status: MembershipStatus
  created_at: string
}

export interface Member {
  id: string
  organization_id: string
  user_id: string
  email: string
  full_name: string
  role: OrgRole
  status: MembershipStatus
  created_at: string
}

export interface Project {
  id: string
  organization_id: string
  name: string
  slug: string
  description: string | null
  status: string
  created_at: string
}

export interface ApiError {
  error: string
  message: string
  details?: unknown
  correlation_id?: string | null
}
