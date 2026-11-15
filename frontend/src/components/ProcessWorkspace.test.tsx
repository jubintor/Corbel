import { describe, it, expect, vi, beforeEach } from 'vitest'
import '@testing-library/jest-dom/vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { ProcessWorkspace } from './ProcessWorkspace'
import type { Project } from '../types/auth'
import type {
  Process,
  ProcessOverview,
  ProcessVariantsResponse,
  DFGResponse,
  ProcessCaseListResponse,
  ProcessCaseDetailResponse,
} from '../types/process'

const mockProject: Project = {
  id: 'proj-p2p',
  organization_id: 'org-test',
  name: 'P2P Test Project',
  slug: 'p2p-test-project',
  description: 'Procure-to-Pay process workspace',
  status: 'ACTIVE',
  created_at: '2026-11-15T08:00:00Z',
}

const mockProcesses: Process[] = [
  {
    id: 'proc-1',
    project_id: 'proj-p2p',
    name: 'Procure-to-Pay Primary',
    description: 'P2P operational process log',
    target_duration_seconds: 86400 * 5,
    is_active: true,
    created_at: '2026-11-15T09:00:00Z',
    updated_at: '2026-11-15T09:00:00Z',
  },
]

const mockOverview: ProcessOverview = {
  process_id: 'proc-1',
  process_name: 'Procure-to-Pay Primary',
  total_cases: 12,
  total_events: 48,
  distinct_variants: 2,
  avg_duration_seconds: 172800,
  median_duration_seconds: 160000,
  min_duration_seconds: 86400,
  max_duration_seconds: 345600,
  sla_breach_count: 1,
  sla_breach_rate: 0.083,
  rework_case_count: 2,
  rework_case_rate: 0.167,
  top_bottleneck: {
    from_activity: 'Goods Received',
    to_activity: 'Invoice Received',
    avg_duration_seconds: 90000,
    transition_count: 10,
    is_bottleneck: true,
  },
}

const mockVariants: ProcessVariantsResponse = {
  process_id: 'proc-1',
  total_variants: 2,
  happy_path_variant: 'PO Created -> Goods Received -> Invoice Received -> Payment Cleared',
  variants: [
    {
      variant_key: 'PO Created -> Goods Received -> Invoice Received -> Payment Cleared',
      activities: ['PO Created', 'Goods Received', 'Invoice Received', 'Payment Cleared'],
      case_count: 10,
      percentage_of_total: 83.33,
      avg_duration_seconds: 160000,
      median_duration_seconds: 160000,
      is_happy_path: true,
    },
    {
      variant_key: 'PO Created -> Invoice Received',
      activities: ['PO Created', 'Invoice Received'],
      case_count: 2,
      percentage_of_total: 16.67,
      avg_duration_seconds: 240000,
      median_duration_seconds: 240000,
      is_happy_path: false,
    },
  ],
}

const mockDFG: DFGResponse = {
  process_id: 'proc-1',
  nodes: [
    { id: 'PO Created', name: 'PO Created', total_occurrences: 12, is_start_activity: true, is_end_activity: false },
    { id: 'Goods Received', name: 'Goods Received', total_occurrences: 10, is_start_activity: false, is_end_activity: false },
    { id: 'Invoice Received', name: 'Invoice Received', total_occurrences: 12, is_start_activity: false, is_end_activity: false },
    { id: 'Payment Cleared', name: 'Payment Cleared', total_occurrences: 10, is_start_activity: false, is_end_activity: true },
  ],
  edges: [
    {
      source: 'PO Created',
      target: 'Goods Received',
      transition_count: 10,
      avg_duration_seconds: 86400,
      median_duration_seconds: 86400,
      min_duration_seconds: 43200,
      max_duration_seconds: 129600,
      is_rework_loop: false,
      is_bottleneck: false,
    },
    {
      source: 'Goods Received',
      target: 'Invoice Received',
      transition_count: 10,
      avg_duration_seconds: 90000,
      median_duration_seconds: 90000,
      min_duration_seconds: 50000,
      max_duration_seconds: 150000,
      is_rework_loop: false,
      is_bottleneck: true,
    },
  ],
  total_transitions: 20,
  bottleneck_count: 1,
}

const mockCases: ProcessCaseListResponse = {
  total: 1,
  page: 1,
  page_size: 25,
  items: [
    {
      id: 'case-1',
      case_identifier: 'PO-9001',
      variant_key: 'PO Created -> Goods Received -> Invoice Received',
      status: 'COMPLETED',
      started_at: '2026-10-01T00:00:00Z',
      ended_at: '2026-10-04T00:00:00Z',
      total_duration_seconds: 259200,
      event_count: 3,
    },
  ],
}

const mockCaseDetail: ProcessCaseDetailResponse = {
  case: mockCases.items[0],
  events: [
    {
      id: 'evt-1',
      activity_name: 'PO Created',
      timestamp: '2026-10-01T00:00:00Z',
      event_type: 'COMPLETE',
      resource: 'SUP-101',
      source_system: 'ERP',
      source_record_id: 'PO-9001',
      attributes_json: { total_amount: 10000 },
    },
    {
      id: 'evt-2',
      activity_name: 'Goods Received',
      timestamp: '2026-10-03T00:00:00Z',
      event_type: 'COMPLETE',
      resource: 'Warehouse',
      source_system: 'WMS',
      source_record_id: 'GR-101',
      attributes_json: { quantity: 50 },
    },
    {
      id: 'evt-3',
      activity_name: 'Invoice Received',
      timestamp: '2026-10-04T00:00:00Z',
      event_type: 'COMPLETE',
      resource: 'Accounts Payable',
      source_system: 'AP_FINANCE',
      source_record_id: 'INV-101',
      attributes_json: { invoice_amount: 10000 },
    },
  ],
}

const mockAuth = {
  user: { id: 'u1', email: 'test@example.com', full_name: 'Tester' },
  token: 'fake-jwt-token',
  activeOrg: { id: 'org-test', name: 'Test Org', slug: 'test-org', role: 'ORG_ADMIN' },
}

vi.mock('../context/AuthContext', () => ({
  useAuth: () => mockAuth,
}))

vi.mock('../services/process', () => ({
  listProcesses: vi.fn().mockImplementation(async () => mockProcesses),
  createProcess: vi.fn().mockImplementation(async (_t, _o, _p, data) => ({
    id: 'proc-new',
    project_id: 'proj-p2p',
    name: data.name,
    description: data.description,
    target_duration_seconds: data.target_duration_seconds,
    is_active: true,
    created_at: '2026-11-15T10:00:00Z',
    updated_at: '2026-11-15T10:00:00Z',
  })),
  getProcessOverview: vi.fn().mockImplementation(async () => mockOverview),
  getProcessVariants: vi.fn().mockImplementation(async () => mockVariants),
  getDFG: vi.fn().mockImplementation(async () => mockDFG),
  listProcessCases: vi.fn().mockImplementation(async () => mockCases),
  getProcessCaseDetail: vi.fn().mockImplementation(async () => mockCaseDetail),
  reconstructProcess: vi.fn().mockImplementation(async () => ({
    process_id: 'proc-1',
    cases_reconstructed: 12,
    events_reconstructed: 48,
    variants_discovered: 2,
    execution_time_ms: 15.4,
  })),
  deleteProcess: vi.fn().mockImplementation(async () => {}),
}))

describe('ProcessWorkspace Component', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders process workspace with KPIs and flow graph', async () => {
    render(<ProcessWorkspace project={mockProject} onBack={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByText('Process Intelligence & Event Mining')).toBeInTheDocument()
      expect(screen.getByText('Procure-to-Pay Primary')).toBeInTheDocument()
      expect(screen.getByText('12')).toBeInTheDocument() // Total cases
      expect(screen.getByText('Top Bottleneck')).toBeInTheDocument()
      expect(screen.getByText('PO Created')).toBeInTheDocument()
      expect(screen.getAllByText('Goods Received').length).toBeGreaterThan(0)
    })
  })

  it('switches between Process Flow, Variants, and Cases tabs', async () => {
    render(<ProcessWorkspace project={mockProject} onBack={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByTestId('subtab-variants')).toBeInTheDocument()
    })

    // Click Variants tab
    fireEvent.click(screen.getByTestId('subtab-variants'))
    await waitFor(() => {
      expect(screen.getByText('Standard Happy Path')).toBeInTheDocument()
      expect(screen.getByText(/83\.3%/)).toBeInTheDocument()
    })

    // Click Cases tab
    fireEvent.click(screen.getByTestId('subtab-cases'))
    await waitFor(() => {
      expect(screen.getByText('PO-9001')).toBeInTheDocument()
      expect(screen.getByText('Inspect')).toBeInTheDocument()
    })

    // Click Inspect to view case timeline
    fireEvent.click(screen.getByText('Inspect'))
    await waitFor(() => {
      expect(screen.getByText('Case Timeline & Provenance')).toBeInTheDocument()
      expect(screen.getByText(/Warehouse/)).toBeInTheDocument()
    })
  })

  it('allows opening the Create Process modal and creating a new process', async () => {
    render(<ProcessWorkspace project={mockProject} onBack={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByText('New Process')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('New Process'))

    expect(screen.getByText('Create Process Container')).toBeInTheDocument()
    const nameInput = screen.getByPlaceholderText('e.g. Procure-to-Pay Lifecycle')
    fireEvent.change(nameInput, { target: { value: 'Secondary Logistics Process' } })

    fireEvent.click(screen.getByRole('button', { name: 'Create Process' }))

    await waitFor(() => {
      expect(screen.getByText(/Process "Secondary Logistics Process" created successfully/i)).toBeInTheDocument()
    })
  })
})
