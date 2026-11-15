import type { Project, ApiError } from '../types/auth'
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

export async function listProjects(token: string, orgId: string): Promise<Project[]> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects`, {
    headers: {
      Authorization: `Bearer ${token}`,
      'X-Organization-ID': orgId,
      Accept: 'application/json',
    },
  })
  return handleResponse<Project[]>(res)
}

export async function createProject(
  token: string,
  orgId: string,
  req: { name: string; slug: string; description?: string }
): Promise<Project> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      'X-Organization-ID': orgId,
    },
    body: JSON.stringify(req),
  })
  return handleResponse<Project>(res)
}

export async function deleteProject(token: string, orgId: string, projectId: string): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}`, {
    method: 'DELETE',
    headers: {
      Authorization: `Bearer ${token}`,
      'X-Organization-ID': orgId,
    },
  })
  await handleResponse<{ message: string }>(res)
}
