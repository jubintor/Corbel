import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  authenticatedFetch,
  refreshTokensSynchronized,
  ACCESS_TOKEN_KEY,
  REFRESH_TOKEN_KEY,
  ACTIVE_ORG_KEY,
} from './apiClient'

describe('apiClient - Synchronized Auth & Interception', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
  })

  it('attaches Bearer and X-Organization-ID headers when present', async () => {
    localStorage.setItem(ACCESS_TOKEN_KEY, 'test-access-token')
    localStorage.setItem(ACTIVE_ORG_KEY, 'org-123')

    const mockFetch = vi.fn().mockResolvedValue({
      status: 200,
      ok: true,
      json: async () => ({ success: true }),
    } as unknown as Response)
    globalThis.fetch = mockFetch

    const res = await authenticatedFetch('/api/v1/projects')
    expect(res.status).toBe(200)

    expect(mockFetch).toHaveBeenCalledTimes(1)
    const callArgs = mockFetch.mock.calls[0]
    const headers = callArgs[1]?.headers as Headers
    expect(headers.get('Authorization')).toBe('Bearer test-access-token')
    expect(headers.get('X-Organization-ID')).toBe('org-123')
  })

  it('queues concurrent 401s and executes only one refresh call', async () => {
    localStorage.setItem(ACCESS_TOKEN_KEY, 'expired-token')
    localStorage.setItem(REFRESH_TOKEN_KEY, 'valid-refresh-token')

    let refreshCallCount = 0

    const mockFetch = vi.fn().mockImplementation(async (url: string) => {
      if (url.includes('/api/v1/auth/refresh')) {
        refreshCallCount++
        return {
          status: 200,
          ok: true,
          json: async () => ({
            access_token: 'new-refreshed-token',
            refresh_token: 'new-next-refresh-token',
            token_type: 'bearer',
            expires_in: 900,
          }),
        } as unknown as Response
      }

      // Initial call with expired token returns 401
      const callHeaders = mockFetch.mock.calls[mockFetch.mock.calls.length - 1][1]?.headers as Headers
      const authHeader = callHeaders?.get?.('Authorization')
      if (authHeader === 'Bearer expired-token') {
        return {
          status: 401,
          ok: false,
          json: async () => ({ error: 'INVALID_CREDENTIALS', message: 'Token expired' }),
        } as unknown as Response
      }

      // Retry with new token succeeds
      return {
        status: 200,
        ok: true,
        json: async () => ({ data: 'protected-data' }),
      } as unknown as Response
    })
    globalThis.fetch = mockFetch

    // Launch 3 concurrent requests that encounter 401
    const [res1, res2, res3] = await Promise.all([
      authenticatedFetch('/api/v1/projects/item1'),
      authenticatedFetch('/api/v1/projects/item2'),
      authenticatedFetch('/api/v1/projects/item3'),
    ])

    expect(res1.status).toBe(200)
    expect(res2.status).toBe(200)
    expect(res3.status).toBe(200)

    // Critical: Exactly ONE refresh was executed despite 3 concurrent 401s
    expect(refreshCallCount).toBe(1)
    expect(localStorage.getItem(ACCESS_TOKEN_KEY)).toBe('new-refreshed-token')
    expect(localStorage.getItem(REFRESH_TOKEN_KEY)).toBe('new-next-refresh-token')
  })

  it('handles refresh failure by clearing tokens and emitting session-expired', async () => {
    localStorage.setItem(ACCESS_TOKEN_KEY, 'bad-token')
    localStorage.setItem(REFRESH_TOKEN_KEY, 'revoked-refresh-token')

    const expiredEventSpy = vi.fn()
    window.addEventListener('corbel:session-expired', expiredEventSpy)

    const mockFetch = vi.fn().mockImplementation(async (url: string) => {
      if (url.includes('/api/v1/auth/refresh')) {
        return {
          status: 401,
          ok: false,
          json: async () => ({ error: 'TOKEN_REVOKED', message: 'Refresh token revoked' }),
        } as unknown as Response
      }
      return {
        status: 401,
        ok: false,
        json: async () => ({ error: 'INVALID_CREDENTIALS' }),
      } as unknown as Response
    })
    globalThis.fetch = mockFetch

    await expect(refreshTokensSynchronized()).rejects.toThrow()
    expect(localStorage.getItem(ACCESS_TOKEN_KEY)).toBeNull()
    expect(localStorage.getItem(REFRESH_TOKEN_KEY)).toBeNull()
    expect(expiredEventSpy).toHaveBeenCalledTimes(1)

    window.removeEventListener('corbel:session-expired', expiredEventSpy)
  })
})
