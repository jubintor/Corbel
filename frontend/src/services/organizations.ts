import type {
  Organization,
  OrganizationWithRole,
  Member,
  OrgRole,
  ApiError,
} from '../types/auth'
import { AuthApiError } from './auth'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) || ''

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let errPayload: ApiError
    try {
      errPayload = (await res.json()) as ApiError
    } catch {
      errPayload = {
        error: 'NETWORK_ERROR',
        message: `HTTP ${res.status}: ${res.statusText}`,
      }
    }
    throw new AuthApiError(errPayload)
  }
  return res.json() as Promise<T>
}

export async function listUserOrganizations(token: string): Promise<OrganizationWithRole[]> {
  const res = await fetch(`${API_BASE_URL}/api/v1/organizations`, {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/json',
    },
  })
  return handleResponse<OrganizationWithRole[]>(res)
}

export async function createOrganization(
  token: string,
  req: { name: string; slug: string }
): Promise<Organization> {
  const res = await fetch(`${API_BASE_URL}/api/v1/organizations`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(req),
  })
  return handleResponse<Organization>(res)
}

export async function listOrgMembers(token: string, orgId: string): Promise<Member[]> {
  const res = await fetch(`${API_BASE_URL}/api/v1/organizations/${orgId}/members`, {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/json',
    },
  })
  return handleResponse<Member[]>(res)
}

export async function addOrgMember(
  token: string,
  orgId: string,
  req: { email: string; role: OrgRole }
): Promise<Member> {
  const res = await fetch(`${API_BASE_URL}/api/v1/organizations/${orgId}/members`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(req),
  })
  return handleResponse<Member>(res)
}
