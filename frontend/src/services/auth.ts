import type { User, TokenResponse, ApiError } from '../types/auth'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) || ''

export class AuthApiError extends Error {
  code: string
  details?: unknown
  correlationId?: string | null

  constructor(apiError: ApiError) {
    super(apiError.message || 'Authentication error')
    this.name = 'AuthApiError'
    this.code = apiError.error || 'UNKNOWN_ERROR'
    this.details = apiError.details
    this.correlationId = apiError.correlation_id
  }
}

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

export async function registerUser(email: string, password: string, fullName: string): Promise<User> {
  const res = await fetch(`${API_BASE_URL}/api/v1/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, full_name: fullName }),
  })
  return handleResponse<User>(res)
}

export async function loginUser(email: string, password: string): Promise<TokenResponse> {
  const res = await fetch(`${API_BASE_URL}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  return handleResponse<TokenResponse>(res)
}

export async function refreshTokens(refreshToken: string): Promise<TokenResponse> {
  const res = await fetch(`${API_BASE_URL}/api/v1/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  })
  return handleResponse<TokenResponse>(res)
}

export async function getMe(accessToken: string): Promise<User> {
  const res = await fetch(`${API_BASE_URL}/api/v1/auth/me`, {
    method: 'GET',
    headers: {
      Authorization: `Bearer ${accessToken}`,
      Accept: 'application/json',
    },
  })
  return handleResponse<User>(res)
}

export async function logoutUser(accessToken: string): Promise<void> {
  try {
    await fetch(`${API_BASE_URL}/api/v1/auth/logout`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
    })
  } catch {
    // Ignore network error on logout
  }
}
