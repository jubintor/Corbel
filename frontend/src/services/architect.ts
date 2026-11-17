import type {
  UseCaseResponse,
  UseCaseDetailResponse,
  UseCaseCreateRequest,
  UseCaseUpdateRequest,
  DiscoveryTurnResponse,
  UseCaseSpecification,
  SpecificationVersionSummary,
  SpecificationDiffResponse,
} from '../types/api_generated'
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

function getHeaders(token: string, orgId: string): HeadersInit {
  return {
    Authorization: `Bearer ${token}`,
    'X-Organization-ID': orgId,
    'Content-Type': 'application/json',
    Accept: 'application/json',
  }
}

export async function createUseCase(
  token: string,
  orgId: string,
  projectId: string,
  data: UseCaseCreateRequest
): Promise<UseCaseResponse> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/use-cases`, {
    method: 'POST',
    headers: getHeaders(token, orgId),
    body: JSON.stringify(data),
  })
  return handleResponse<UseCaseResponse>(res)
}

export async function listUseCases(
  token: string,
  orgId: string,
  projectId: string
): Promise<UseCaseResponse[]> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/use-cases`, {
    headers: getHeaders(token, orgId),
  })
  return handleResponse<UseCaseResponse[]>(res)
}

export async function getUseCase(
  token: string,
  orgId: string,
  projectId: string,
  useCaseId: string
): Promise<UseCaseDetailResponse> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/projects/${projectId}/use-cases/${useCaseId}`,
    {
      headers: getHeaders(token, orgId),
    }
  )
  return handleResponse<UseCaseDetailResponse>(res)
}

export async function updateUseCase(
  token: string,
  orgId: string,
  projectId: string,
  useCaseId: string,
  data: UseCaseUpdateRequest
): Promise<UseCaseResponse> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/projects/${projectId}/use-cases/${useCaseId}`,
    {
      method: 'PUT',
      headers: getHeaders(token, orgId),
      body: JSON.stringify(data),
    }
  )
  return handleResponse<UseCaseResponse>(res)
}

export async function deleteUseCase(
  token: string,
  orgId: string,
  projectId: string,
  useCaseId: string
): Promise<void> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/projects/${projectId}/use-cases/${useCaseId}`,
    {
      method: 'DELETE',
      headers: getHeaders(token, orgId),
    }
  )
  await handleResponse<void>(res)
}

export async function addDiscoveryMessage(
  token: string,
  orgId: string,
  projectId: string,
  useCaseId: string,
  messageText: string
): Promise<DiscoveryTurnResponse> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/projects/${projectId}/use-cases/${useCaseId}/messages`,
    {
      method: 'POST',
      headers: getHeaders(token, orgId),
      body: JSON.stringify({ message_text: messageText }),
    }
  )
  return handleResponse<DiscoveryTurnResponse>(res)
}

export async function generateSpecification(
  token: string,
  orgId: string,
  projectId: string,
  useCaseId: string
): Promise<UseCaseSpecification> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/projects/${projectId}/use-cases/${useCaseId}/specifications/generate`,
    {
      method: 'POST',
      headers: getHeaders(token, orgId),
    }
  )
  return handleResponse<UseCaseSpecification>(res)
}

export async function listSpecifications(
  token: string,
  orgId: string,
  projectId: string,
  useCaseId: string
): Promise<SpecificationVersionSummary[]> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/projects/${projectId}/use-cases/${useCaseId}/specifications`,
    {
      headers: getHeaders(token, orgId),
    }
  )
  return handleResponse<SpecificationVersionSummary[]>(res)
}

export async function getSpecificationVersion(
  token: string,
  orgId: string,
  projectId: string,
  useCaseId: string,
  version: number
): Promise<UseCaseSpecification> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/projects/${projectId}/use-cases/${useCaseId}/specifications/${version}`,
    {
      headers: getHeaders(token, orgId),
    }
  )
  return handleResponse<UseCaseSpecification>(res)
}

export async function compareSpecifications(
  token: string,
  orgId: string,
  projectId: string,
  useCaseId: string,
  v1: number,
  v2: number
): Promise<SpecificationDiffResponse> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/projects/${projectId}/use-cases/${useCaseId}/specifications/compare?v1=${v1}&v2=${v2}`,
    {
      headers: getHeaders(token, orgId),
    }
  )
  return handleResponse<SpecificationDiffResponse>(res)
}

export async function approveSpecification(
  token: string,
  orgId: string,
  projectId: string,
  useCaseId: string
): Promise<UseCaseResponse> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/projects/${projectId}/use-cases/${useCaseId}/specifications/approve`,
    {
      method: 'POST',
      headers: getHeaders(token, orgId),
    }
  )
  return handleResponse<UseCaseResponse>(res)
}
