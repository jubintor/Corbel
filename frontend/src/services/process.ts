import type {
  Process,
  ProcessCreateRequest,
  ProcessOverview,
  ProcessVariantsResponse,
  DFGResponse,
  ProcessCaseListResponse,
  ProcessCaseDetailResponse,
  ProcessReconstructRequest,
  ProcessReconstructResponse,
} from '../types/process'
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

export async function listProcesses(
  token: string,
  orgId: string,
  projectId: string
): Promise<Process[]> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/process`, {
    headers: {
      Authorization: `Bearer ${token}`,
      'X-Organization-ID': orgId,
      Accept: 'application/json',
    },
  })
  return handleResponse<Process[]>(res)
}

export async function createProcess(
  token: string,
  orgId: string,
  projectId: string,
  data: ProcessCreateRequest
): Promise<Process> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/process`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'X-Organization-ID': orgId,
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(data),
  })
  return handleResponse<Process>(res)
}

export async function getProcess(
  token: string,
  orgId: string,
  projectId: string,
  processId: string
): Promise<Process> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/process/${processId}`, {
    headers: {
      Authorization: `Bearer ${token}`,
      'X-Organization-ID': orgId,
      Accept: 'application/json',
    },
  })
  return handleResponse<Process>(res)
}

export async function deleteProcess(
  token: string,
  orgId: string,
  projectId: string,
  processId: string
): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/process/${processId}`, {
    method: 'DELETE',
    headers: {
      Authorization: `Bearer ${token}`,
      'X-Organization-ID': orgId,
    },
  })
  await handleResponse<void>(res)
}

export async function reconstructProcess(
  token: string,
  orgId: string,
  projectId: string,
  processId: string,
  data: ProcessReconstructRequest
): Promise<ProcessReconstructResponse> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/process/${processId}/reconstruct`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'X-Organization-ID': orgId,
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(data),
  })
  return handleResponse<ProcessReconstructResponse>(res)
}

export async function getProcessOverview(
  token: string,
  orgId: string,
  projectId: string,
  processId: string
): Promise<ProcessOverview> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/process/${processId}/overview`, {
    headers: {
      Authorization: `Bearer ${token}`,
      'X-Organization-ID': orgId,
      Accept: 'application/json',
    },
  })
  return handleResponse<ProcessOverview>(res)
}

export async function getProcessVariants(
  token: string,
  orgId: string,
  projectId: string,
  processId: string
): Promise<ProcessVariantsResponse> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/process/${processId}/variants`, {
    headers: {
      Authorization: `Bearer ${token}`,
      'X-Organization-ID': orgId,
      Accept: 'application/json',
    },
  })
  return handleResponse<ProcessVariantsResponse>(res)
}

export async function getDFG(
  token: string,
  orgId: string,
  projectId: string,
  processId: string
): Promise<DFGResponse> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/process/${processId}/dfg`, {
    headers: {
      Authorization: `Bearer ${token}`,
      'X-Organization-ID': orgId,
      Accept: 'application/json',
    },
  })
  return handleResponse<DFGResponse>(res)
}

export async function listProcessCases(
  token: string,
  orgId: string,
  projectId: string,
  processId: string,
  page: number = 1,
  pageSize: number = 20
): Promise<ProcessCaseListResponse> {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  })
  const res = await fetch(
    `${API_BASE_URL}/api/v1/projects/${projectId}/process/${processId}/cases?${params.toString()}`,
    {
      headers: {
        Authorization: `Bearer ${token}`,
        'X-Organization-ID': orgId,
        Accept: 'application/json',
      },
    }
  )
  return handleResponse<ProcessCaseListResponse>(res)
}

export async function getProcessCaseDetail(
  token: string,
  orgId: string,
  projectId: string,
  processId: string,
  caseId: string
): Promise<ProcessCaseDetailResponse> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/projects/${projectId}/process/${processId}/cases/${caseId}`,
    {
      headers: {
        Authorization: `Bearer ${token}`,
        'X-Organization-ID': orgId,
        Accept: 'application/json',
      },
    }
  )
  return handleResponse<ProcessCaseDetailResponse>(res)
}
