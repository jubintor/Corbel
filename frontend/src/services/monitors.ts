import type {
  Monitor,
  MonitorCreate,
  MonitorUpdate,
  BusinessRule,
  BusinessRuleCreate,
  Finding,
  FindingStatusUpdate,
  MonitorEvaluation,
  FindingStatus,
  RuleSeverity,
} from '../types/monitors'
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

export async function listMonitors(
  token: string,
  orgId: string,
  projectId: string
): Promise<Monitor[]> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/monitors`, {
    headers: {
      Authorization: `Bearer ${token}`,
      'X-Organization-ID': orgId,
      Accept: 'application/json',
    },
  })
  return handleResponse<Monitor[]>(res)
}

export async function getMonitor(
  token: string,
  orgId: string,
  projectId: string,
  monitorId: string
): Promise<Monitor> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/monitors/${monitorId}`, {
    headers: {
      Authorization: `Bearer ${token}`,
      'X-Organization-ID': orgId,
      Accept: 'application/json',
    },
  })
  return handleResponse<Monitor>(res)
}

export async function createMonitor(
  token: string,
  orgId: string,
  projectId: string,
  req: MonitorCreate
): Promise<Monitor> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/monitors`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'X-Organization-ID': orgId,
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(req),
  })
  return handleResponse<Monitor>(res)
}

export async function updateMonitor(
  token: string,
  orgId: string,
  projectId: string,
  monitorId: string,
  req: MonitorUpdate
): Promise<Monitor> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/monitors/${monitorId}`, {
    method: 'PUT',
    headers: {
      Authorization: `Bearer ${token}`,
      'X-Organization-ID': orgId,
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(req),
  })
  return handleResponse<Monitor>(res)
}

export async function deleteMonitor(
  token: string,
  orgId: string,
  projectId: string,
  monitorId: string
): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/monitors/${monitorId}`, {
    method: 'DELETE',
    headers: {
      Authorization: `Bearer ${token}`,
      'X-Organization-ID': orgId,
    },
  })
  return handleResponse<void>(res)
}

export async function addRule(
  token: string,
  orgId: string,
  projectId: string,
  monitorId: string,
  req: BusinessRuleCreate
): Promise<BusinessRule> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/projects/${projectId}/monitors/${monitorId}/rules`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'X-Organization-ID': orgId,
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify(req),
    }
  )
  return handleResponse<BusinessRule>(res)
}

export async function deleteRule(
  token: string,
  orgId: string,
  projectId: string,
  monitorId: string,
  ruleId: string
): Promise<void> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/projects/${projectId}/monitors/${monitorId}/rules/${ruleId}`,
    {
      method: 'DELETE',
      headers: {
        Authorization: `Bearer ${token}`,
        'X-Organization-ID': orgId,
      },
    }
  )
  return handleResponse<void>(res)
}

export async function evaluateMonitor(
  token: string,
  orgId: string,
  projectId: string,
  monitorId: string,
  limit: number = 500
): Promise<MonitorEvaluation> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/projects/${projectId}/monitors/${monitorId}/evaluate?limit=${limit}`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'X-Organization-ID': orgId,
        Accept: 'application/json',
      },
    }
  )
  return handleResponse<MonitorEvaluation>(res)
}

export interface ListFindingsParams {
  monitorId?: string
  status?: FindingStatus
  severity?: RuleSeverity
  limit?: number
  offset?: number
}

export async function listFindings(
  token: string,
  orgId: string,
  projectId: string,
  params?: ListFindingsParams
): Promise<Finding[]> {
  const query = new URLSearchParams()
  if (params?.monitorId) query.set('monitor_id', params.monitorId)
  if (params?.status) query.set('status', params.status)
  if (params?.severity) query.set('severity', params.severity)
  if (params?.limit !== undefined) query.set('limit', String(params.limit))
  if (params?.offset !== undefined) query.set('offset', String(params.offset))

  const queryString = query.toString() ? `?${query.toString()}` : ''
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/findings${queryString}`, {
    headers: {
      Authorization: `Bearer ${token}`,
      'X-Organization-ID': orgId,
      Accept: 'application/json',
    },
  })
  return handleResponse<Finding[]>(res)
}

export async function getFinding(
  token: string,
  orgId: string,
  projectId: string,
  findingId: string
): Promise<Finding> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/findings/${findingId}`, {
    headers: {
      Authorization: `Bearer ${token}`,
      'X-Organization-ID': orgId,
      Accept: 'application/json',
    },
  })
  return handleResponse<Finding>(res)
}

export async function updateFindingStatus(
  token: string,
  orgId: string,
  projectId: string,
  findingId: string,
  req: FindingStatusUpdate
): Promise<Finding> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/projects/${projectId}/findings/${findingId}/status`,
    {
      method: 'PATCH',
      headers: {
        Authorization: `Bearer ${token}`,
        'X-Organization-ID': orgId,
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify(req),
    }
  )
  return handleResponse<Finding>(res)
}

export async function listEvaluations(
  token: string,
  orgId: string,
  projectId: string,
  monitorId?: string,
  limit: number = 20
): Promise<MonitorEvaluation[]> {
  const query = new URLSearchParams()
  if (monitorId) query.set('monitor_id', monitorId)
  query.set('limit', String(limit))

  const res = await fetch(
    `${API_BASE_URL}/api/v1/projects/${projectId}/evaluations?${query.toString()}`,
    {
      headers: {
        Authorization: `Bearer ${token}`,
        'X-Organization-ID': orgId,
        Accept: 'application/json',
      },
    }
  )
  return handleResponse<MonitorEvaluation[]>(res)
}
