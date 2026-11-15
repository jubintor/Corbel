import type {
  BusinessObject,
  OntologyGraphResponse,
  OntologyTraversalResponse,
  Property,
  PropertyMapping,
  Relationship,
  SemanticDiscoveryResponse,
} from '../types/ontology'
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

export async function seedP2POntology(
  token: string,
  orgId: string,
  projectId: string
): Promise<BusinessObject[]> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/ontology/seed-p2p`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'X-Organization-ID': orgId,
      Accept: 'application/json',
    },
  })
  return handleResponse<BusinessObject[]>(res)
}

export async function getOntologyGraph(
  token: string,
  orgId: string,
  projectId: string
): Promise<OntologyGraphResponse> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/ontology/graph`, {
    headers: {
      Authorization: `Bearer ${token}`,
      'X-Organization-ID': orgId,
      Accept: 'application/json',
    },
  })
  return handleResponse<OntologyGraphResponse>(res)
}

export async function listBusinessObjects(
  token: string,
  orgId: string,
  projectId: string
): Promise<BusinessObject[]> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/ontology/objects`, {
    headers: {
      Authorization: `Bearer ${token}`,
      'X-Organization-ID': orgId,
      Accept: 'application/json',
    },
  })
  return handleResponse<BusinessObject[]>(res)
}

export async function getBusinessObject(
  token: string,
  orgId: string,
  projectId: string,
  objectId: string
): Promise<BusinessObject> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/ontology/objects/${objectId}`, {
    headers: {
      Authorization: `Bearer ${token}`,
      'X-Organization-ID': orgId,
      Accept: 'application/json',
    },
  })
  return handleResponse<BusinessObject>(res)
}

export async function createBusinessObject(
  token: string,
  orgId: string,
  projectId: string,
  payload: {
    name: string
    display_name: string
    description?: string
    primary_key_property?: string
  }
): Promise<BusinessObject> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/ontology/objects`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'X-Organization-ID': orgId,
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(payload),
  })
  return handleResponse<BusinessObject>(res)
}

export async function deleteBusinessObject(
  token: string,
  orgId: string,
  projectId: string,
  objectId: string
): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/ontology/objects/${objectId}`, {
    method: 'DELETE',
    headers: {
      Authorization: `Bearer ${token}`,
      'X-Organization-ID': orgId,
    },
  })
  await handleResponse<void>(res)
}

export async function addProperty(
  token: string,
  orgId: string,
  projectId: string,
  objectId: string,
  payload: {
    name: string
    display_name?: string
    data_type: string
    is_nullable?: boolean
    is_primary_key?: boolean
    description?: string
  }
): Promise<Property> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/projects/${projectId}/ontology/objects/${objectId}/properties`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'X-Organization-ID': orgId,
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify(payload),
    }
  )
  return handleResponse<Property>(res)
}

export async function deleteProperty(
  token: string,
  orgId: string,
  projectId: string,
  objectId: string,
  propertyId: string
): Promise<void> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/projects/${projectId}/ontology/objects/${objectId}/properties/${propertyId}`,
    {
      method: 'DELETE',
      headers: {
        Authorization: `Bearer ${token}`,
        'X-Organization-ID': orgId,
      },
    }
  )
  await handleResponse<void>(res)
}

export async function listRelationships(
  token: string,
  orgId: string,
  projectId: string
): Promise<Relationship[]> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/ontology/relationships`, {
    headers: {
      Authorization: `Bearer ${token}`,
      'X-Organization-ID': orgId,
      Accept: 'application/json',
    },
  })
  return handleResponse<Relationship[]>(res)
}

export async function createRelationship(
  token: string,
  orgId: string,
  projectId: string,
  payload: {
    name: string
    source_object_id: string
    target_object_id: string
    cardinality: string
    description?: string
    join_expression?: Record<string, unknown>
  }
): Promise<Relationship> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/ontology/relationships`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'X-Organization-ID': orgId,
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(payload),
  })
  return handleResponse<Relationship>(res)
}

export async function deleteRelationship(
  token: string,
  orgId: string,
  projectId: string,
  relationshipId: string
): Promise<void> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/projects/${projectId}/ontology/relationships/${relationshipId}`,
    {
      method: 'DELETE',
      headers: {
        Authorization: `Bearer ${token}`,
        'X-Organization-ID': orgId,
      },
    }
  )
  await handleResponse<void>(res)
}

export async function discoverSemanticMappings(
  token: string,
  orgId: string,
  projectId: string,
  payload: {
    dataset_id: string
    dataset_version_id: string
    business_object_id: string
  }
): Promise<SemanticDiscoveryResponse> {
  const res = await fetch(`${API_BASE_URL}/api/v1/projects/${projectId}/ontology/discover-mappings`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'X-Organization-ID': orgId,
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(payload),
  })
  return handleResponse<SemanticDiscoveryResponse>(res)
}

export async function listPropertyMappings(
  token: string,
  orgId: string,
  projectId: string,
  status?: string,
  businessObjectId?: string
): Promise<PropertyMapping[]> {
  const params = new URLSearchParams()
  if (status) params.append('status', status)
  if (businessObjectId) params.append('business_object_id', businessObjectId)

  const url = `${API_BASE_URL}/api/v1/projects/${projectId}/ontology/mappings?${params.toString()}`
  const res = await fetch(url, {
    headers: {
      Authorization: `Bearer ${token}`,
      'X-Organization-ID': orgId,
      Accept: 'application/json',
    },
  })
  return handleResponse<PropertyMapping[]>(res)
}

export async function acceptMapping(
  token: string,
  orgId: string,
  projectId: string,
  mappingId: string
): Promise<PropertyMapping> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/projects/${projectId}/ontology/mappings/${mappingId}/accept`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'X-Organization-ID': orgId,
        Accept: 'application/json',
      },
    }
  )
  return handleResponse<PropertyMapping>(res)
}

export async function rejectMapping(
  token: string,
  orgId: string,
  projectId: string,
  mappingId: string
): Promise<PropertyMapping> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/projects/${projectId}/ontology/mappings/${mappingId}/reject`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'X-Organization-ID': orgId,
        Accept: 'application/json',
      },
    }
  )
  return handleResponse<PropertyMapping>(res)
}

export async function deletePropertyMapping(
  token: string,
  orgId: string,
  projectId: string,
  mappingId: string
): Promise<void> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/projects/${projectId}/ontology/mappings/${mappingId}`,
    {
      method: 'DELETE',
      headers: {
        Authorization: `Bearer ${token}`,
        'X-Organization-ID': orgId,
      },
    }
  )
  await handleResponse<void>(res)
}

export async function traverseOntology(
  token: string,
  orgId: string,
  projectId: string,
  objectId: string
): Promise<OntologyTraversalResponse> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/projects/${projectId}/ontology/objects/${objectId}/traverse`,
    {
      headers: {
        Authorization: `Bearer ${token}`,
        'X-Organization-ID': orgId,
        Accept: 'application/json',
      },
    }
  )
  return handleResponse<OntologyTraversalResponse>(res)
}
