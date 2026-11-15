import type { Dataset, DatasetPreview, DatasetVersion } from '../types/dataset'
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

export async function listProjectDatasets(
  token: string,
  orgId: string,
  projectId: string
): Promise<Dataset[]> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/datasets`, {
    headers: {
      Authorization: `Bearer ${token}`,
      'X-Organization-ID': orgId,
      Accept: 'application/json',
    },
  })
  return handleResponse<Dataset[]>(res)
}

export async function uploadDataset(
  token: string,
  orgId: string,
  projectId: string,
  file: File,
  name?: string,
  description?: string
): Promise<Dataset> {
  const formData = new FormData()
  formData.append('file', file)
  if (name) formData.append('name', name)
  if (description) formData.append('description', description)

  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/datasets/upload`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'X-Organization-ID': orgId,
    },
    body: formData,
  })
  return handleResponse<Dataset>(res)
}

export async function getDataset(
  token: string,
  orgId: string,
  projectId: string,
  datasetId: string
): Promise<Dataset> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/datasets/${datasetId}`, {
    headers: {
      Authorization: `Bearer ${token}`,
      'X-Organization-ID': orgId,
      Accept: 'application/json',
    },
  })
  return handleResponse<Dataset>(res)
}

export async function getDatasetVersion(
  token: string,
  orgId: string,
  projectId: string,
  datasetId: string,
  versionId: string
): Promise<DatasetVersion> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/projects/${projectId}/datasets/${datasetId}/versions/${versionId}`,
    {
      headers: {
        Authorization: `Bearer ${token}`,
        'X-Organization-ID': orgId,
        Accept: 'application/json',
      },
    }
  )
  return handleResponse<DatasetVersion>(res)
}

export async function getDatasetPreview(
  token: string,
  orgId: string,
  projectId: string,
  datasetId: string,
  limit: number = 20
): Promise<DatasetPreview> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/projects/${projectId}/datasets/${datasetId}/preview?limit=${limit}`,
    {
      headers: {
        Authorization: `Bearer ${token}`,
        'X-Organization-ID': orgId,
        Accept: 'application/json',
      },
    }
  )
  return handleResponse<DatasetPreview>(res)
}

export async function deleteDataset(
  token: string,
  orgId: string,
  projectId: string,
  datasetId: string
): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/datasets/${datasetId}`, {
    method: 'DELETE',
    headers: {
      Authorization: `Bearer ${token}`,
      'X-Organization-ID': orgId,
    },
  })
  await handleResponse<Record<string, unknown>>(res)
}
