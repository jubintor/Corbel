import { describe, it, expect, vi, beforeEach } from 'vitest'
import '@testing-library/jest-dom/vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import App from './App'
import type { SystemHealthResponse } from './types/api'

const mockHealthResponse: SystemHealthResponse = {
  status: 'healthy',
  app_name: 'Corbel',
  version: '0.1.0',
  environment: 'development',
  timestamp: '2026-11-14T19:00:00.000Z',
  database: {
    status: 'connected',
    latency_ms: 1.45,
    details: 'PostgreSQL connection pool healthy',
  },
}

describe('Corbel Frontend Shell', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockHealthResponse,
    }) as unknown as typeof fetch
  })

  it('renders Corbel branding and platform identity', async () => {
    await act(async () => {
      render(<App />)
    })

    expect(screen.getByText('Corbel')).toBeInTheDocument()
    expect(screen.getByText('Enterprise AI & Operational Intelligence Platform')).toBeInTheDocument()
    expect(screen.getByText(/Discover Context. Understand Operations./i)).toBeInTheDocument()
  })

  it('displays real-time infrastructure health card', async () => {
    await act(async () => {
      render(<App />)
    })

    expect(screen.getByText('Infrastructure Health Status')).toBeInTheDocument()
    expect(screen.getByText('FastAPI Backend')).toBeInTheDocument()
    expect(screen.getByText('PostgreSQL 16+')).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getByText('Operational')).toBeInTheDocument()
      expect(screen.getByText('Connected')).toBeInTheDocument()
      expect(screen.getByText('1.45 ms')).toBeInTheDocument()
    })
  })

  it('renders dual development mode operational specifications', async () => {
    await act(async () => {
      render(<App />)
    })

    expect(screen.getByText('Authoritative Dual Local Development Modes')).toBeInTheDocument()
    expect(screen.getByText(/Mode A — Lightweight Local Dev/i)).toBeInTheDocument()
    expect(screen.getByText(/Mode B — Full Containerized Dev/i)).toBeInTheDocument()
    expect(screen.getByText('docker compose up -d corbel-db')).toBeInTheDocument()
  })

  it('renders platform implementation roadmap with Phase 1 highlighted', async () => {
    await act(async () => {
      render(<App />)
    })

    expect(screen.getByText('Platform Implementation Roadmap')).toBeInTheDocument()
    expect(screen.getByText('Application Foundation')).toBeInTheDocument()
    expect(screen.getByText('Authentication & Tenancy')).toBeInTheDocument()
  })

  it('renders authentication actions and multi-tenant workspace prompts', async () => {
    await act(async () => {
      render(<App />)
    })

    expect(screen.getByText('Multi-Tenant Workspaces Require Authentication')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Register' })).toBeInTheDocument()
  })

  it('handles health check fetch rejection gracefully without unhandled rejections', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('Network offline')) as unknown as typeof fetch
    await act(async () => {
      render(<App />)
    })
    expect(screen.getByText('Infrastructure Health Status')).toBeInTheDocument()
  })
})
