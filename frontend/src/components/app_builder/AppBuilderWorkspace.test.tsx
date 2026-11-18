import { describe, it, expect, vi, beforeEach } from 'vitest'
import '@testing-library/jest-dom/vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { AppBuilderWorkspace } from './AppBuilderWorkspace'
import type { Project } from '../../types/auth'
import type {
  ApplicationDetailResponse,
  ApplicationResponse,
} from '../../types/api_generated'
import * as appBuilderService from '../../services/appBuilder'
import * as architectService from '../../services/architect'

const mockProject: Project = {
  id: 'proj-p2p',
  organization_id: 'org-test',
  name: 'Procure-to-Pay Intelligence',
  slug: 'p2p-intelligence',
  description: 'P2P application workspace',
  status: 'ACTIVE',
  created_at: '2026-11-15T08:00:00Z',
}

const mockAppSummary: ApplicationResponse = {
  id: 'app-p2p-portal',
  organization_id: 'org-test',
  project_id: 'proj-p2p',
  name: 'P2P Exception Portal',
  description: 'Operational portal for triage of purchase order discrepancies.',
  status: 'PUBLISHED',
  current_version: 1,
  published_version: 1,
  created_by: 'user-lead',
  updated_by: 'user-lead',
  published_by: 'user-lead',
  published_at: '2026-11-18T10:00:00Z',
  created_at: '2026-11-18T09:00:00Z',
  updated_at: '2026-11-18T10:00:00Z',
}

const mockAppDetail: ApplicationDetailResponse = {
  ...mockAppSummary,
  draft_definition: {
    app_id: 'app-p2p-portal',
    name: 'P2P Exception Portal',
    description: 'Operational portal for triage of purchase order discrepancies.',
    navigation: {
      title: 'Main Navigation',
      default_page_id: 'page_overview',
      items: [{ page_id: 'page_overview', label: 'Overview' }],
    },
    pages: [
      {
        id: 'page_overview',
        title: 'Overview',
        sections: [
          {
            id: 'sec_kpis',
            title: 'Key Operational Metrics',
            layout: 'TWO_COLUMNS',
            components: [
              {
                id: 'comp_metric_variances',
                component_type: 'METRIC_CARD',
                title: 'Active Exceptions',
                properties: { value: '42', unit: 'cases' },
              },
            ],
          },
        ],
      },
    ],
  },
}

const mockAuth = {
  user: { id: 'u1', email: 'builder@corbel.internal', full_name: 'Lead Builder' },
  token: 'fake-jwt-token',
  activeOrg: { id: 'org-test', name: 'Test Global Org', slug: 'test-global', role: 'ORG_ADMIN' },
}

vi.mock('../../context/AuthContext', () => ({
  useAuth: () => mockAuth,
}))

describe('AppBuilderWorkspace Component', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(appBuilderService, 'listApplications').mockResolvedValue([mockAppSummary])
    vi.spyOn(appBuilderService, 'getApplication').mockResolvedValue(mockAppDetail)
    vi.spyOn(appBuilderService, 'listCatalogue').mockResolvedValue([
      {
        component_type: 'METRIC_CARD',
        category: 'data',
        display_name: 'Metric Card',
        description: 'Single KPI summary card',
        supported_data_sources: ['STATIC', 'ONTOLOGY_OBJECT'],
        required_properties: [],
        default_properties: { title: 'KPI', value: '0' },
        supports_interactions: false,
      },
    ])
    vi.spyOn(architectService, 'listUseCases').mockResolvedValue([
      {
        id: 'uc-1',
        organization_id: 'org-test',
        project_id: 'proj-p2p',
        title: 'P2P Variance Intelligence',
        description: 'Automate invoice audit checks',
        status: 'APPROVED',
        current_version: 1,
        created_by: 'user-1',
        created_at: '2026-11-17T00:00:00Z',
        updated_at: '2026-11-17T00:00:00Z',
      },
    ])
  })

  it('renders application roster with application cards', async () => {
    render(<AppBuilderWorkspace project={mockProject} onBack={vi.fn()} />)

    expect(screen.getByText('Application Builder & Runtime Portal')).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getByText('P2P Exception Portal')).toBeInTheDocument()
      expect(screen.getByText(/Live v1/)).toBeInTheDocument()
      expect(screen.getByTestId('edit-app-app-p2p-portal')).toBeInTheDocument()
      expect(screen.getByTestId('launch-app-app-p2p-portal')).toBeInTheDocument()
    })
  })

  it('opens Create Application modal and creates blank template application', async () => {
    vi.spyOn(appBuilderService, 'createApplication').mockResolvedValue({
      ...mockAppDetail,
      id: 'app-new-blank',
      name: 'Custom Triage App',
      status: 'DRAFT',
    })

    render(<AppBuilderWorkspace project={mockProject} onBack={vi.fn()} />)

    const createBtn = screen.getByTestId('create-app-button')
    fireEvent.click(createBtn)

    expect(screen.getByText('Create New Application')).toBeInTheDocument()

    // Switch to Blank Template
    fireEvent.click(screen.getByText('Blank Template'))

    // Enter name
    const nameInput = screen.getByPlaceholderText('Procure-to-Pay Portal')
    fireEvent.change(nameInput, { target: { value: 'Custom Triage App' } })

    const submitBtn = screen.getByText('Create & Open Builder')
    fireEvent.click(submitBtn)

    await waitFor(() => {
      expect(appBuilderService.createApplication).toHaveBeenCalledWith(
        expect.any(String),
        expect.any(String),
        'proj-p2p',
        expect.objectContaining({
          name: 'Custom Triage App',
        })
      )
    })
  })

  it('opens Visual Builder when clicking Edit Blueprint', async () => {
    render(<AppBuilderWorkspace project={mockProject} onBack={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByTestId('edit-app-app-p2p-portal')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByTestId('edit-app-app-p2p-portal'))

    await waitFor(() => {
      expect(screen.getByText('Component Catalogue')).toBeInTheDocument()
      expect(screen.getByText('Save Draft')).toBeInTheDocument()
      expect(screen.getByText('Validate Blueprint')).toBeInTheDocument()
      expect(screen.getByText('Publish Version')).toBeInTheDocument()
    })
  })

  it('opens Published App Portal when clicking Launch App', async () => {
    vi.spyOn(appBuilderService, 'getRuntimeDefinition').mockResolvedValue({
      application_id: 'app-p2p-portal',
      name: 'P2P Exception Portal',
      description: 'Live runtime portal',
      version: 1,
      published_at: '2026-11-18T10:00:00Z',
      user_roles: ['PROJECT_LEAD'],
      definition: mockAppDetail.draft_definition,
    })

    render(<AppBuilderWorkspace project={mockProject} onBack={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByTestId('launch-app-app-p2p-portal')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByTestId('launch-app-app-p2p-portal'))

    await waitFor(() => {
      expect(screen.getByText(/Exit App/)).toBeInTheDocument()
      expect(screen.getByText(/Live v/)).toBeInTheDocument()
      expect(screen.getByText('Active Exceptions')).toBeInTheDocument()
    })
  })
})
