import type { SystemHealthResponse } from '../types/api'

// Base URL configured via environment or defaulting to relative path (handled by Vite proxy / Nginx)
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) || ''

/**
 * Fetch health status from backend FastAPI endpoint (/api/v1/health).
 */
export async function fetchSystemHealth(): Promise<SystemHealthResponse> {
  const url = `${API_BASE_URL}/api/v1/health`
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), 6000)

  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
      },
      signal: controller.signal,
    })

    clearTimeout(timeoutId)

    if (!response.ok) {
      // Even if 503, backend may return detailed health payload
      try {
        const errorData = (await response.json()) as SystemHealthResponse
        if (errorData && errorData.database) {
          return errorData
        }
      } catch {
        // Fallback below
      }
      throw new Error(`HTTP ${response.status}: ${response.statusText}`)
    }

    return (await response.json()) as SystemHealthResponse
  } catch (error: unknown) {
    clearTimeout(timeoutId)
    const message = error instanceof Error ? error.message : 'Network communication failure'
    return {
      status: 'unhealthy',
      app_name: 'Corbel Backend',
      version: 'unknown',
      environment: 'unknown',
      timestamp: new Date().toISOString(),
      database: {
        status: 'disconnected',
        latency_ms: null,
        details: message,
      },
    }
  }
}
