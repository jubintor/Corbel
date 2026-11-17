import type {
  Investigation,
  InvestigationStatus,
  Document,
  DocumentCreateRequest,
  DocumentQueryResponse,
  Action,
  ActionStatus,
  Approval,
  ApprovalStatus,
  ActionExecution,
  AuditEvent,
  P2PVerticalSliceDemoRequest,
  P2PVerticalSliceDemoResponse,
} from '../types/governance'
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

export async function listInvestigations(
  token: string,
  orgId: string,
  projectId: string,
  status?: InvestigationStatus,
  limit = 50,
  offset = 0
): Promise<{ items: Investigation[]; total: number }> {
  const params = new URLSearchParams()
  if (status) params.append('status', status)
  params.append('limit', String(limit))
  params.append('offset', String(offset))

  const res = await fetch(
    `${API_BASE_URL}/api/v1/projects/${projectId}/investigations?${params.toString()}`,
    {
      headers: getHeaders(token, orgId),
    }
  )
  return handleResponse<{ items: Investigation[]; total: number }>(res)
}

export async function createInvestigation(
  token: string,
  orgId: string,
  projectId: string,
  payload: { finding_id: string; title?: string; include_rag_documents?: boolean }
): Promise<Investigation> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/investigations`, {
    method: 'POST',
    headers: getHeaders(token, orgId),
    body: JSON.stringify(payload),
  })
  return handleResponse<Investigation>(res)
}

export async function getInvestigation(
  token: string,
  orgId: string,
  projectId: string,
  investigationId: string
): Promise<Investigation> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/projects/${projectId}/investigations/${investigationId}`,
    {
      headers: getHeaders(token, orgId),
    }
  )
  return handleResponse<Investigation>(res)
}

export async function listDocuments(
  token: string,
  orgId: string,
  projectId: string
): Promise<Document[]> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/documents`, {
    headers: getHeaders(token, orgId),
  })
  return handleResponse<Document[]>(res)
}

export async function ingestDocument(
  token: string,
  orgId: string,
  projectId: string,
  payload: DocumentCreateRequest
): Promise<Document> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/documents`, {
    method: 'POST',
    headers: getHeaders(token, orgId),
    body: JSON.stringify(payload),
  })
  return handleResponse<Document>(res)
}

export async function queryDocuments(
  token: string,
  orgId: string,
  projectId: string,
  payload: { query_text: string; top_k?: number; document_type?: string }
): Promise<DocumentQueryResponse> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/documents/query`, {
    method: 'POST',
    headers: getHeaders(token, orgId),
    body: JSON.stringify(payload),
  })
  return handleResponse<DocumentQueryResponse>(res)
}

export async function listActions(
  token: string,
  orgId: string,
  projectId: string,
  status?: ActionStatus
): Promise<Action[]> {
  const params = new URLSearchParams()
  if (status) params.append('status', status)
  const res = await fetch(
    `${API_BASE_URL}/api/v1/projects/${projectId}/actions?${params.toString()}`,
    {
      headers: getHeaders(token, orgId),
    }
  )
  return handleResponse<Action[]>(res)
}

export async function listApprovals(
  token: string,
  orgId: string,
  projectId: string,
  status?: ApprovalStatus
): Promise<Approval[]> {
  const params = new URLSearchParams()
  if (status) params.append('status', status)
  const res = await fetch(
    `${API_BASE_URL}/api/v1/projects/${projectId}/approvals?${params.toString()}`,
    {
      headers: getHeaders(token, orgId),
    }
  )
  return handleResponse<Approval[]>(res)
}

export async function decideApproval(
  token: string,
  orgId: string,
  projectId: string,
  approvalId: string,
  payload: { decision: ApprovalStatus; rationale: string }
): Promise<Approval> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/projects/${projectId}/approvals/${approvalId}/decision`,
    {
      method: 'POST',
      headers: getHeaders(token, orgId),
      body: JSON.stringify(payload),
    }
  )
  return handleResponse<Approval>(res)
}

export async function executeAction(
  token: string,
  orgId: string,
  projectId: string,
  actionId: string,
  payload: { idempotency_key: string }
): Promise<ActionExecution> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/projects/${projectId}/actions/${actionId}/execute`,
    {
      method: 'POST',
      headers: getHeaders(token, orgId),
      body: JSON.stringify(payload),
    }
  )
  return handleResponse<ActionExecution>(res)
}

export async function listAuditEvents(
  token: string,
  orgId: string,
  projectId: string,
  actionType?: string,
  limit = 50,
  offset = 0
): Promise<{ items: AuditEvent[]; total: number }> {
  const params = new URLSearchParams()
  if (actionType) params.append('action_type', actionType)
  params.append('limit', String(limit))
  params.append('offset', String(offset))

  const res = await fetch(
    `${API_BASE_URL}/api/v1/projects/${projectId}/audit-events?${params.toString()}`,
    {
      headers: getHeaders(token, orgId),
    }
  )
  return handleResponse<{ items: AuditEvent[]; total: number }>(res)
}

export async function runP2PDemoSlice(
  token: string,
  orgId: string,
  projectId: string,
  payload: P2PVerticalSliceDemoRequest
): Promise<P2PVerticalSliceDemoResponse> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/demo/p2p-slice`, {
    method: 'POST',
    headers: getHeaders(token, orgId),
    body: JSON.stringify(payload),
  })
  return handleResponse<P2PVerticalSliceDemoResponse>(res)
}
