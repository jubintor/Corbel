import type {
  NaturalLanguageQueryRequest,
  NaturalLanguageQueryResponse,
  QueryExecutionAuditResponse,
  QuerySchemaResponse,
  StructuredQueryRequest,
  StructuredQueryResponse,
} from '../types/query'
import type { ApiError } from '../types/auth'
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
  if (res.status === 204) {
    return {} as T
  }
  return res.json() as Promise<T>
}

export async function getQuerySchema(
  token: string,
  orgId: string,
  projectId: string
): Promise<QuerySchemaResponse> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/query/schema`, {
    headers: {
      Authorization: `Bearer ${token}`,
      'X-Organization-ID': orgId,
      Accept: 'application/json',
    },
  })
  return handleResponse<QuerySchemaResponse>(res)
}

export async function executeStructuredQuery(
  token: string,
  orgId: string,
  projectId: string,
  req: StructuredQueryRequest
): Promise<StructuredQueryResponse> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/query/execute`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'X-Organization-ID': orgId,
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(req),
  })
  return handleResponse<StructuredQueryResponse>(res)
}

export async function compileNaturalLanguageQuery(
  token: string,
  orgId: string,
  projectId: string,
  req: NaturalLanguageQueryRequest
): Promise<NaturalLanguageQueryResponse> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/query/nlq`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'X-Organization-ID': orgId,
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(req),
  })
  return handleResponse<NaturalLanguageQueryResponse>(res)
}

export async function getQueryHistory(
  token: string,
  orgId: string,
  projectId: string,
  limit: number = 50
): Promise<QueryExecutionAuditResponse[]> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/query/history?limit=${limit}`, {
    headers: {
      Authorization: `Bearer ${token}`,
      'X-Organization-ID': orgId,
      Accept: 'application/json',
    },
  })
  return handleResponse<QueryExecutionAuditResponse[]>(res)
}
