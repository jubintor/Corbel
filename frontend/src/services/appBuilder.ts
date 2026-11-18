import type {
  ApplicationCreateRequest,
  ApplicationDefinition,
  ApplicationDetailResponse,
  ApplicationPublishRequest,
  ApplicationResponse,
  ApplicationUpdateRequest,
  ApplicationValidationResponse,
  ApplicationVersionSummary,
  ComponentType,
  PublishedApplicationRuntimeResponse,
  RuntimeActionExecuteRequest,
  RuntimeActionExecuteResponse,
  RuntimeDataQueryRequest,
  RuntimeDataQueryResponse,
} from '../types/api_generated'
import type { ApiError } from '../types/auth'
import { AuthApiError } from './auth'

export interface ComponentCatalogItem {
  component_type: ComponentType
  category: string
  display_name: string
  description: string
  supported_data_sources: string[]
  required_properties: string[]
  default_properties: Record<string, unknown>
  supports_interactions: boolean
}

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

export async function listApplications(
  token: string,
  orgId: string,
  projectId: string
): Promise<ApplicationResponse[]> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/applications`, {
    headers: getHeaders(token, orgId),
  })
  return handleResponse<ApplicationResponse[]>(res)
}

export async function createApplication(
  token: string,
  orgId: string,
  projectId: string,
  data: ApplicationCreateRequest
): Promise<ApplicationDetailResponse> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/applications`, {
    method: 'POST',
    headers: getHeaders(token, orgId),
    body: JSON.stringify(data),
  })
  return handleResponse<ApplicationDetailResponse>(res)
}

export async function getApplication(
  token: string,
  orgId: string,
  projectId: string,
  appId: string
): Promise<ApplicationDetailResponse> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/applications/${appId}`, {
    headers: getHeaders(token, orgId),
  })
  return handleResponse<ApplicationDetailResponse>(res)
}

export async function updateApplication(
  token: string,
  orgId: string,
  projectId: string,
  appId: string,
  data: ApplicationUpdateRequest
): Promise<ApplicationDetailResponse> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/applications/${appId}`, {
    method: 'PUT',
    headers: getHeaders(token, orgId),
    body: JSON.stringify(data),
  })
  return handleResponse<ApplicationDetailResponse>(res)
}

export async function deleteApplication(
  token: string,
  orgId: string,
  projectId: string,
  appId: string
): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/applications/${appId}`, {
    method: 'DELETE',
    headers: getHeaders(token, orgId),
  })
  return handleResponse<void>(res)
}

export async function validateApplication(
  token: string,
  orgId: string,
  projectId: string,
  appId: string,
  definition?: ApplicationDefinition
): Promise<ApplicationValidationResponse> {
  const url = `${API_BASE_URL}/api/v1/projects/${projectId}/applications/${appId}/validate`
  const res = await fetch(url, {
    method: 'POST',
    headers: getHeaders(token, orgId),
    body: definition ? JSON.stringify(definition) : undefined,
  })
  return handleResponse<ApplicationValidationResponse>(res)
}

export async function publishApplication(
  token: string,
  orgId: string,
  projectId: string,
  appId: string,
  data: ApplicationPublishRequest
): Promise<ApplicationDetailResponse> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/applications/${appId}/publish`, {
    method: 'POST',
    headers: getHeaders(token, orgId),
    body: JSON.stringify(data),
  })
  return handleResponse<ApplicationDetailResponse>(res)
}

export async function listApplicationVersions(
  token: string,
  orgId: string,
  projectId: string,
  appId: string
): Promise<ApplicationVersionSummary[]> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/applications/${appId}/versions`, {
    headers: getHeaders(token, orgId),
  })
  return handleResponse<ApplicationVersionSummary[]>(res)
}

export async function getApplicationVersion(
  token: string,
  orgId: string,
  projectId: string,
  appId: string,
  version: number
): Promise<ApplicationVersionSummary> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/projects/${projectId}/applications/${appId}/versions/${version}`,
    {
      headers: getHeaders(token, orgId),
    }
  )
  return handleResponse<ApplicationVersionSummary>(res)
}

export async function listCatalogue(
  token: string,
  orgId: string,
  projectId: string
): Promise<ComponentCatalogItem[]> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/applications/catalogue`, {
    headers: getHeaders(token, orgId),
  })
  return handleResponse<ComponentCatalogItem[]>(res)
}

export async function getRuntimeDefinition(
  token: string,
  orgId: string,
  projectId: string,
  appId: string
): Promise<PublishedApplicationRuntimeResponse> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/applications/${appId}/runtime`, {
    headers: getHeaders(token, orgId),
  })
  return handleResponse<PublishedApplicationRuntimeResponse>(res)
}

export async function queryRuntimeData(
  token: string,
  orgId: string,
  projectId: string,
  appId: string,
  data: RuntimeDataQueryRequest
): Promise<RuntimeDataQueryResponse> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/applications/${appId}/runtime/data`, {
    method: 'POST',
    headers: getHeaders(token, orgId),
    body: JSON.stringify(data),
  })
  return handleResponse<RuntimeDataQueryResponse>(res)
}

export async function executeRuntimeAction(
  token: string,
  orgId: string,
  projectId: string,
  appId: string,
  data: RuntimeActionExecuteRequest
): Promise<RuntimeActionExecuteResponse> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/applications/${appId}/runtime/action`, {
    method: 'POST',
    headers: getHeaders(token, orgId),
    body: JSON.stringify(data),
  })
  return handleResponse<RuntimeActionExecuteResponse>(res)
}
