/**
 * Centralized HTTP Client with automatic 401 interception and mutex-protected token refresh.
 *
 * Prevents concurrent refresh token race conditions and refresh token family reuse revocation (P2-LIM-013).
 */

import type { TokenResponse, ApiError } from '../types/auth'
import { AuthApiError } from './auth'
import { generateSecureId } from '../utils/crypto'

export { generateSecureId }
export const ACCESS_TOKEN_KEY = 'corbel_access_token'
export const REFRESH_TOKEN_KEY = 'corbel_refresh_token'
export const ACTIVE_ORG_KEY = 'corbel_active_org_id'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) || ''

let isRefreshing = false
let refreshPromise: Promise<string> | null = null

type QueueItem = {
  resolve: (token: string) => void
  reject: (error: unknown) => void
}

let failedQueue: QueueItem[] = []

const processQueue = (error: unknown, token: string | null = null) => {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error)
    } else if (token) {
      prom.resolve(token)
    }
  })
  failedQueue = []
}

export function getStoredAccessToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY)
}

export function getStoredRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY)
}

export function getStoredActiveOrgId(): string | null {
  return localStorage.getItem(ACTIVE_ORG_KEY)
}

export function setStoredTokens(accessToken: string, refreshToken: string): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken)
  localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken)
}

export function clearStoredAuth(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY)
  localStorage.removeItem(REFRESH_TOKEN_KEY)
  localStorage.removeItem(ACTIVE_ORG_KEY)
}

/**
 * Execute a synchronized refresh of access and refresh tokens.
 * Only one network call is executed at any time; concurrent callers await the same promise.
 */
export async function refreshTokensSynchronized(): Promise<string> {
  if (isRefreshing && refreshPromise) {
    return refreshPromise
  }

  const refreshToken = getStoredRefreshToken()
  if (!refreshToken) {
    clearStoredAuth()
    throw new Error('No refresh token available')
  }

  isRefreshing = true
  const IN_FLIGHT_KEY = 'corbel_refresh_in_flight'
  let idempotencyKey: string
  const existingInFlight = typeof localStorage !== 'undefined' ? localStorage.getItem(IN_FLIGHT_KEY) : null
  if (existingInFlight) {
    try {
      const parsed = JSON.parse(existingInFlight)
      if (parsed.key && (Date.now() - parsed.timestamp) < 10000) {
        idempotencyKey = parsed.key
      } else {
        idempotencyKey = generateSecureId('idemp')
      }
    } catch {
      idempotencyKey = generateSecureId('idemp')
    }
  } else {
    idempotencyKey = generateSecureId('idemp')
  }

  if (typeof localStorage !== 'undefined') {
    try {
      localStorage.setItem(IN_FLIGHT_KEY, JSON.stringify({ key: idempotencyKey, timestamp: Date.now() }))
    } catch {
      // Ignore storage errors in private browsing modes
    }
  }

  refreshPromise = (async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          refresh_token: refreshToken,
          idempotency_key: idempotencyKey,
        }),
      })

      if (!res.ok) {
        let errPayload: ApiError
        try {
          errPayload = (await res.json()) as ApiError
        } catch {
          errPayload = {
            error: 'REFRESH_FAILED',
            message: `HTTP ${res.status}: ${res.statusText}`,
          }
        }
        throw new AuthApiError(errPayload)
      }

      const data = (await res.json()) as TokenResponse
      setStoredTokens(data.access_token, data.refresh_token)
      processQueue(null, data.access_token)
      return data.access_token
    } catch (err) {
      clearStoredAuth()
      processQueue(err, null)
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('corbel:session-expired'))
      }
      throw err
    } finally {
      isRefreshing = false
      refreshPromise = null
      if (typeof localStorage !== 'undefined') {
        try {
          localStorage.removeItem(IN_FLIGHT_KEY)
        } catch {}
      }
    }
  })()

  return refreshPromise
}

/**
 * Authenticated fetch with transparent 401 interception and single-mutex refresh retry.
 */
export async function authenticatedFetch(
  input: string,
  init: RequestInit = {}
): Promise<Response> {
  const url = input.startsWith('http') || input.startsWith('/') ? input : `${API_BASE_URL}/${input}`
  const headers = new Headers(init.headers || {})

  const token = getStoredAccessToken()
  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  const activeOrgId = getStoredActiveOrgId()
  if (activeOrgId && !headers.has('X-Organization-ID')) {
    headers.set('X-Organization-ID', activeOrgId)
  }

  const isAuthEndpoint =
    url.includes('/api/v1/auth/login') ||
    url.includes('/api/v1/auth/register') ||
    url.includes('/api/v1/auth/refresh')

  const initialResponse = await fetch(url, { ...init, headers })

  if (initialResponse.status !== 401 || isAuthEndpoint) {
    return initialResponse
  }

  // Token expired or invalid: attempt synchronized refresh
  try {
    let newAccessToken: string
    if (isRefreshing) {
      newAccessToken = await new Promise<string>((resolve, reject) => {
        failedQueue.push({ resolve, reject })
      })
    } else {
      newAccessToken = await refreshTokensSynchronized()
    }

    const retryHeaders = new Headers(init.headers || {})
    retryHeaders.set('Authorization', `Bearer ${newAccessToken}`)
    if (activeOrgId && !retryHeaders.has('X-Organization-ID')) {
      retryHeaders.set('X-Organization-ID', activeOrgId)
    }

    return await fetch(url, { ...init, headers: retryHeaders })
  } catch {
    return initialResponse
  }
}
