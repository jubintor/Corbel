import { describe, it, expect, vi, beforeEach } from 'vitest'
import '@testing-library/jest-dom/vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ProjectWorkspace } from './ProjectWorkspace'
import type { Project } from '../types/auth'

const mockProjects: Project[] = [
  {
    id: 'proj-p2p',
    organization_id: 'org-test',
    name: 'P2P Dataset Test',
    slug: 'p2p-dataset-test',
    description: 'Procure-to-Pay test project workspace',
    status: 'ACTIVE',
    created_at: '2026-11-15T08:00:00Z',
  },
]

const mockAuth = {
  user: { id: 'u1', email: 'test@example.com', full_name: 'Tester' },
  token: 'fake-jwt-token',
  activeOrg: { id: 'org-test', name: 'Test Org', slug: 'test-org', role: 'ORG_ADMIN' },
}

vi.mock('../context/AuthContext', () => ({
  useAuth: () => mockAuth,
}))

vi.mock('../services/projects', () => ({
  listProjects: vi.fn().mockImplementation(async () => mockProjects),
  createProject: vi.fn(),
  deleteProject: vi.fn(),
}))

vi.mock('../services/datasets', () => ({
  listProjectDatasets: vi.fn().mockResolvedValue([]),
  uploadDataset: vi.fn(),
  deleteDataset: vi.fn(),
  getDatasetPreview: vi.fn(),
}))

describe('ProjectWorkspace Navigation & Selection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders tenant project card with details, created date, and clickable controls', async () => {
    await act(async () => {
      render(<ProjectWorkspace />)
    })

    await waitFor(() => {
      expect(screen.getByText('P2P Dataset Test')).toBeInTheDocument()
      expect(screen.getByText('p2p-dataset-test')).toBeInTheDocument()
      expect(screen.getByText('ACTIVE')).toBeInTheDocument()
      expect(screen.getByText('Procure-to-Pay test project workspace')).toBeInTheDocument()
      expect(screen.getByText(/Created/i)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Open Workspace/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument()
    })
  })

  it('opens DatasetWorkspace when clicking the Open Workspace button', async () => {
    const user = userEvent.setup()
    await act(async () => {
      render(<ProjectWorkspace />)
    })

    await waitFor(() => {
      expect(screen.getByText('P2P Dataset Test')).toBeInTheDocument()
    })

    const openBtn = screen.getByRole('button', { name: /Open Workspace/i })
    await act(async () => {
      await user.click(openBtn)
    })

    // Expect DatasetWorkspace to be mounted with the project title and Data Intelligence badge
    await waitFor(() => {
      expect(screen.getByText('Data Intelligence')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Projects/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Upload Dataset/i })).toBeInTheDocument()
    })
  })

  it('opens DatasetWorkspace when clicking the project card container', async () => {
    const user = userEvent.setup()
    await act(async () => {
      render(<ProjectWorkspace />)
    })

    await waitFor(() => {
      expect(screen.getByTestId('project-card-proj-p2p')).toBeInTheDocument()
    })

    const card = screen.getByTestId('project-card-proj-p2p')
    await act(async () => {
      await user.click(card)
    })

    await waitFor(() => {
      expect(screen.getByText('Data Intelligence')).toBeInTheDocument()
    })
  })

  it('opens DatasetWorkspace when clicking the project title button', async () => {
    const user = userEvent.setup()
    await act(async () => {
      render(<ProjectWorkspace />)
    })

    await waitFor(() => {
      expect(screen.getByText('P2P Dataset Test')).toBeInTheDocument()
    })

    const titleBtn = screen.getByRole('button', { name: 'P2P Dataset Test' })
    await act(async () => {
      await user.click(titleBtn)
    })

    await waitFor(() => {
      expect(screen.getByText('Data Intelligence')).toBeInTheDocument()
    })
  })

  it('allows navigating back to project list from DatasetWorkspace', async () => {
    const user = userEvent.setup()
    await act(async () => {
      render(<ProjectWorkspace />)
    })

    await waitFor(() => {
      expect(screen.getByText('P2P Dataset Test')).toBeInTheDocument()
    })

    // Open project
    const openBtn = screen.getByRole('button', { name: /Open Workspace/i })
    await act(async () => {
      await user.click(openBtn)
    })

    await waitFor(() => {
      expect(screen.getByText('Data Intelligence')).toBeInTheDocument()
    })

    // Click back to projects
    const backBtn = screen.getByRole('button', { name: /Projects/i })
    await act(async () => {
      await user.click(backBtn)
    })

    // Should return to project list
    await waitFor(() => {
      expect(screen.getByText('Tenant Workspaces & Projects')).toBeInTheDocument()
      expect(screen.getByText('P2P Dataset Test')).toBeInTheDocument()
    })
  })
})
