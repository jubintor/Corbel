import { describe, it, expect, vi, beforeEach } from 'vitest'
import '@testing-library/jest-dom/vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { ArchitectWorkspace } from './ArchitectWorkspace'
import type { Project } from '../types/auth'
import type {
  UseCaseResponse,
  UseCaseDetailResponse,
  UseCaseSpecification,
  SpecificationVersionSummary,
} from '../types/api_generated'
import * as architectService from '../services/architect'

const mockProject: Project = {
  id: 'proj-p2p',
  organization_id: 'org-test',
  name: 'Procure-to-Pay Intelligence',
  slug: 'p2p-intelligence',
  description: 'P2P exception and invoice discrepancy monitoring',
  status: 'ACTIVE',
  created_at: '2026-11-15T08:00:00Z',
}

const mockUseCase: UseCaseResponse = {
  id: 'uc-1',
  organization_id: 'org-test',
  project_id: 'proj-p2p',
  title: 'P2P Invoice Discrepancy Intelligence',
  description: 'Automate detection of supplier price variances across POs and invoices.',
  status: 'DISCOVERY',
  current_version: 1,
  created_by: 'u1',
  approved_by: null,
  approved_at: null,
  created_at: '2026-11-17T10:00:00Z',
  updated_at: '2026-11-17T10:00:00Z',
}

const mockSpecification: UseCaseSpecification = {
  use_case_id: 'uc-1',
  version_number: 1,
  title: 'P2P Invoice Discrepancy Intelligence',
  description: 'Automate detection of supplier price variances across POs and invoices.',
  business_objective: 'Eliminate manual 3-way matching invoice audits.',
  expected_outcomes: ['100% price variance detection', 'Zero unauthorized payments'],
  stakeholders_and_roles: ['Procurement Lead', 'Accounts Payable', 'Finance Controller'],
  workflow_description: 'PO -> Goods Receipt -> Invoice -> Match -> Review -> Credit Note',
  inputs_and_outputs: {
    inputs: ['Purchase Orders', 'Supplier Invoices', 'Goods Receipts'],
    outputs: ['Price Variance Alerts', 'Root-Cause Dossier'],
    decisions: ['Variance Breach Check'],
    actions: ['Request Credit Note', 'Hold Payment'],
  },
  source_systems: ['ERP (SAP/Oracle)', 'Warehouse DB'],
  data_classification: 'CONFIDENTIAL',
  freshness_and_latency: 'Near Real-Time (< 5 min)',
  retrieval_requirements: 'Hybrid Structured SQL & Document RAG',
  required_tools_and_actions: ['Request Credit Note', 'Hold Payment'],
  risk_level: 'HIGH',
  human_approval_requirements: ['Credit notes >$1,000 require Finance Controller approval'],
  proposed_architecture: 'Deterministic Event Monitor Pipeline + Governed Investigation & Document RAG',
  architecture_rationale_and_alternatives: {
    recommended_pattern: 'Deterministic Event Monitor Pipeline + Governed Investigation & Document RAG',
    justification: 'Price variances require 100% deterministic arithmetic, not model guesswork.',
    deterministic_components: ['Price Variance Arithmetic Engine', 'Event Timeline Miner'],
    retrieval_components: ['Vendor Contract pgvector RAG', 'Transactional SQL Queries'],
    agentic_components: ['Bounded Investigation State Machine'],
    alternatives_considered: [
      {
        approach: 'Unconstrained Autonomous Agent',
        pros: ['Flexible'],
        cons: ['Risk of financial hallucination'],
        rejection_reason: 'Enterprise financial math must be deterministic.',
      },
    ],
  },
  implementation_plan: [
    {
      milestone_id: 'M1',
      title: 'P2P Schema Mapping',
      description: 'Profile and map PO and Invoice datasets.',
      target_components: ['Data Intelligence'],
      dependencies: [],
      estimated_effort: '1 sprint (estimate)',
      acceptance_criteria: ['100% type safety'],
    },
  ],
  estimates_and_assumptions: {
    delivery_estimates: ['Estimated 2-3 sprints (estimate)'],
    verified_capabilities: ['PostgreSQL audit logger', 'Deterministic monitors'],
    unverified_assumptions: ['Customer provides read-only DB access'],
  },
  risks_and_dependencies: [
    {
      risk: 'Legacy PO format mismatches',
      severity: 'MEDIUM',
      mitigation: 'Canonical normalization rules',
    },
  ],
  open_questions: ['What is the exact credit note threshold?'],
  success_metrics: ['Over 80% reduction in review time'],
  evaluation_plan: 'Benchmark against historical transaction logs.',
  specification_status: 'REVIEW',
  created_at: '2026-11-17T10:05:00Z',
  updated_at: '2026-11-17T10:05:00Z',
}

const mockDetail: UseCaseDetailResponse = {
  ...mockUseCase,
  messages: [
    {
      id: 'msg-1',
      sender_role: 'USER',
      message_text: 'Automate detection of supplier price variances across POs and invoices.',
      created_at: '2026-11-17T10:00:00Z',
    },
    {
      id: 'msg-2',
      sender_role: 'ASSISTANT',
      message_text: 'Understood P2P problem statement. Formulated clarifying questions.',
      extracted_requirements: {
        business_objective: 'P2P exception detection',
        expected_outcomes: ['Anomaly detection'],
        stakeholders: ['Procurement Lead'],
        workflows: ['Order-to-Pay'],
        inputs: ['Purchase Orders', 'Invoices'],
        outputs: ['Discrepancy Alerts'],
        source_systems: ['ERP (SAP/Oracle)'],
        data_sensitivity: 'CONFIDENTIAL',
        freshness_latency: 'Near Real-Time',
        confirmed_requirements: ['PO and Invoice line item tracking'],
        unverified_assumptions: ['Price variance threshold is 5%'],
      },
      clarification_questions: ['What is the exact variance tolerance percentage?'],
      created_at: '2026-11-17T10:00:05Z',
    },
  ],
  latest_specification: mockSpecification,
}

const mockVersion: SpecificationVersionSummary = {
  version: 1,
  created_by: 'u1',
  created_at: '2026-11-17T10:05:00Z',
  title: mockSpecification.title,
  proposed_architecture: mockSpecification.proposed_architecture,
  risk_level: mockSpecification.risk_level || 'HIGH',
}

const mockAuth = {
  user: { id: 'u1', email: 'architect@corbel.internal', full_name: 'Lead Architect' },
  token: 'fake-jwt-token',
  activeOrg: { id: 'org-test', name: 'Test Global Org', slug: 'test-global', role: 'ORG_ADMIN' },
}

vi.mock('../context/AuthContext', () => ({
  useAuth: () => mockAuth,
}))

vi.mock('../services/architect', () => ({
  listUseCases: vi.fn(),
  getUseCase: vi.fn(),
  createUseCase: vi.fn(),
  addDiscoveryMessage: vi.fn(),
  generateSpecification: vi.fn(),
  listSpecifications: vi.fn(),
  compareSpecifications: vi.fn(),
  approveSpecification: vi.fn(),
}))

describe('ArchitectWorkspace Component', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(architectService.listUseCases).mockResolvedValue([mockUseCase])
    vi.mocked(architectService.getUseCase).mockResolvedValue(mockDetail)
    vi.mocked(architectService.listSpecifications).mockResolvedValue([mockVersion])
  })

  it('renders the workspace and lists project use cases', async () => {
    render(<ArchitectWorkspace project={mockProject} onBack={vi.fn()} />)

    expect(screen.getByText('Use-Case Architect')).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByText('P2P Invoice Discrepancy Intelligence')).toBeInTheDocument()
    })
    expect(screen.getByText('Phase 11')).toBeInTheDocument()
  })

  it('displays discovery messages and distinguishes confirmed requirements from assumptions', async () => {
    render(<ArchitectWorkspace project={mockProject} onBack={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByText('Understood P2P problem statement. Formulated clarifying questions.')).toBeInTheDocument()
    })

    expect(screen.getByText('✓ Confirmed Requirements:')).toBeInTheDocument()
    expect(screen.getByText('PO and Invoice line item tracking')).toBeInTheDocument()
    expect(screen.getByText('? Unverified Assumptions:')).toBeInTheDocument()
    expect(screen.getByText('Price variance threshold is 5%')).toBeInTheDocument()
    expect(screen.getByText('What is the exact variance tolerance percentage?')).toBeInTheDocument()
  })

  it('allows answering clarification questions in the discovery dialogue', async () => {
    vi.mocked(architectService.addDiscoveryMessage).mockResolvedValue({
      user_message: {
        id: 'msg-3',
        sender_role: 'USER',
        message_text: 'Variance threshold is strictly 5%.',
        created_at: '2026-11-17T10:01:00Z',
      },
      assistant_message: {
        id: 'msg-4',
        sender_role: 'ASSISTANT',
        message_text: 'Confirmed 5% threshold.',
        created_at: '2026-11-17T10:01:05Z',
      },
      can_generate_specification: true,
    })

    render(<ArchitectWorkspace project={mockProject} onBack={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/Answer clarification questions/i)).toBeInTheDocument()
    })

    const input = screen.getByPlaceholderText(/Answer clarification questions/i)
    fireEvent.change(input, { target: { value: 'Variance threshold is strictly 5%.' } })
    fireEvent.click(screen.getByRole('button', { name: /Send/i }))

    await waitFor(() => {
      expect(architectService.addDiscoveryMessage).toHaveBeenCalledWith(
        'fake-jwt-token',
        'org-test',
        'proj-p2p',
        'uc-1',
        'Variance threshold is strictly 5%.'
      )
    })
  })

  it('switches to Technical Architecture tab and renders proposed pattern and alternatives', async () => {
    render(<ArchitectWorkspace project={mockProject} onBack={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByText('Technical Architecture')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Technical Architecture'))

    expect(screen.getByText(/Deterministic Event Monitor Pipeline \+ Governed Investigation/i)).toBeInTheDocument()
    expect(screen.getByText('Deterministic Components')).toBeInTheDocument()
    expect(screen.getByText('Price Variance Arithmetic Engine')).toBeInTheDocument()
    expect(screen.getByText('Alternatives Considered & Rejection Rationale')).toBeInTheDocument()
    expect(screen.getByText('Unconstrained Autonomous Agent')).toBeInTheDocument()
    expect(screen.getByText(/Enterprise financial math must be deterministic/i)).toBeInTheDocument()
  })

  it('allows approving the specification and verifies state update', async () => {
    vi.mocked(architectService.approveSpecification).mockResolvedValue({
      ...mockUseCase,
      status: 'APPROVED',
      approved_by: 'u1',
      approved_at: '2026-11-17T10:10:00Z',
    })

    render(<ArchitectWorkspace project={mockProject} onBack={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Approve Specification/i })).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Approve Specification/i }))

    await waitFor(() => {
      expect(architectService.approveSpecification).toHaveBeenCalledWith(
        'fake-jwt-token',
        'org-test',
        'proj-p2p',
        'uc-1'
      )
    })
  })
})
