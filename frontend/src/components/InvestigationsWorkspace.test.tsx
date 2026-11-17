import { describe, it, expect, vi, beforeEach } from 'vitest'
import '@testing-library/jest-dom/vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { InvestigationsWorkspace } from './InvestigationsWorkspace'
import type { Project } from '../types/auth'
import type {
  Investigation,
  Approval,
  Action,
  Document as RAGDocument,
  AuditEvent,
  P2PVerticalSliceDemoResponse,
} from '../types/governance'

const mockProject: Project = {
  id: 'proj-p2p',
  organization_id: 'org-test',
  name: 'Procure-to-Pay Excellence',
  slug: 'p2p-excellence',
  description: 'P2P investigation and governance workspace',
  status: 'ACTIVE',
  created_at: '2026-11-15T08:00:00Z',
}

const mockInvestigation: Investigation = {
  id: 'inv-1',
  project_id: 'proj-p2p',
  finding_id: 'find-1',
  title: 'Root-Cause Investigation for INV-7844 Variance',
  status: 'COMPLETED',
  financial_impact_usd: 1250.0,
  verified_facts_json: [
    { fact_type: 'THRESHOLD_VIOLATION', entity_id: 'INV-7844', variance: 1250.0 },
  ],
  causal_hypothesis: 'Candidate causal hypothesis: Invoice INV-7844 reflects unapproved freight surcharge.',
  evidence_count: 2,
  created_at: '2026-11-16T08:00:00Z',
  updated_at: '2026-11-16T08:00:00Z',
  evidence_items: [
    {
      id: 'ev-1',
      investigation_id: 'inv-1',
      evidence_type: 'DOCUMENT_CHUNK',
      source_uri: 'rag://docs/msa.txt',
      title: 'MSA Section 4.2 Terms',
      content_snippet: 'Expedited freight requires prior written authorization.',
      confidence_score: 0.95,
      is_verified_fact: true,
      retrieved_at: '2026-11-16T08:00:00Z',
    },
  ],
  recommendations: [
    {
      id: 'rec-1',
      investigation_id: 'inv-1',
      title: 'Hold Discrepant Invoice & Request Credit Memo',
      description: 'Block ERP payment processing and issue credit request.',
      confidence_score: 0.95,
      risk_level: 'LOW',
      recommended_action_type: 'HOLD_INVOICE',
      suggested_payload_json: { invoice_id: 'INV-7844', discrepancy_amount_usd: 1250.0 },
      created_at: '2026-11-16T08:00:00Z',
    },
  ],
}

const mockApproval: Approval = {
  id: 'appr-1',
  action_id: 'act-1',
  assigned_role: 'MANAGER',
  status: 'PENDING',
  approved_payload_hash: null,
  decision_rationale: null,
  created_at: '2026-11-16T08:00:00Z',
}

const mockAction: Action = {
  id: 'act-1',
  project_id: 'proj-p2p',
  recommendation_id: 'rec-1',
  action_type: 'HOLD_INVOICE',
  target_system: 'SimulatedTargetAdapter',
  proposed_payload_json: { invoice_id: 'INV-7844' },
  is_consequential: true,
  status: 'APPROVED',
  created_at: '2026-11-16T08:00:00Z',
  updated_at: '2026-11-16T08:00:00Z',
}

const mockDocument: RAGDocument = {
  id: 'doc-1',
  project_id: 'proj-p2p',
  title: 'Apex Master Services Agreement',
  document_type: 'CONTRACT',
  file_name: 'msa_apex.txt',
  file_format: 'txt',
  chunk_count: 4,
  created_at: '2026-11-16T08:00:00Z',
}

const mockAuditEvent: AuditEvent = {
  id: 'aud-1',
  organization_id: 'org-test',
  project_id: 'proj-p2p',
  actor_type: 'USER',
  actor_id: 'u-1',
  action_type: 'APPROVAL_GRANTED',
  affected_entity_type: 'Approval',
  affected_entity_id: 'appr-1',
  outcome_status: 'SUCCESS',
  timestamp: '2026-11-16T08:05:00Z',
}

const mockDemoResponse: P2PVerticalSliceDemoResponse = {
  finding_id: 'find-1',
  investigation_id: 'inv-1',
  financial_impact_usd: 1250.0,
  verified_facts: [{ invoice: 'INV-7844', variance: 1250.0 }],
  causal_hypothesis: 'Unapproved expedited air freight surcharge detected.',
  retrieved_document_snippets: ['Clause 4.2 Expedited freight surcharges require written authorization.'],
  recommendation: mockInvestigation.recommendations[0],
  action: { ...mockAction, status: 'EXECUTED' },
  approval: { ...mockApproval, status: 'APPROVED', approved_payload_hash: 'a1b2c3d4e5f6' },
  execution: {
    id: 'exec-1',
    action_id: 'act-1',
    approval_id: 'appr-1',
    idempotency_key: 'IDEM-1234',
    target_adapter_type: 'SimulatedTargetAdapter',
    status: 'SUCCEEDED',
    attempt_count: 1,
    dispatched_payload_hash: 'a1b2c3d4e5f6',
    dispatched_at: '2026-11-16T08:10:00Z',
  },
  audit_events_count: 5,
}

const mockAuth = {
  user: { id: 'u1', email: 'test@corbel.internal', full_name: 'Lead Reviewer' },
  token: 'fake-jwt-token',
  activeOrg: { id: 'org-test', name: 'Test Global Org', slug: 'test-global', role: 'ORG_ADMIN' },
}

vi.mock('../context/AuthContext', () => ({
  useAuth: () => mockAuth,
}))

vi.mock('../services/governance', () => ({
  listInvestigations: vi.fn().mockImplementation(async () => ({ items: [mockInvestigation], total: 1 })),
  getInvestigation: vi.fn().mockImplementation(async () => mockInvestigation),
  listApprovals: vi.fn().mockImplementation(async () => [mockApproval]),
  decideApproval: vi.fn().mockImplementation(async () => ({ ...mockApproval, status: 'APPROVED' })),
  listActions: vi.fn().mockImplementation(async () => [mockAction]),
  executeAction: vi.fn().mockImplementation(async () => ({
    id: 'exec-1',
    target_adapter_type: 'SimulatedTargetAdapter',
    status: 'SUCCEEDED',
    adapter_response_json: { reference: 'ERP-HOLD-1234' },
  })),
  listDocuments: vi.fn().mockImplementation(async () => [mockDocument]),
  ingestDocument: vi.fn().mockImplementation(async () => mockDocument),
  queryDocuments: vi.fn().mockImplementation(async () => ({
    query_text: 'freight surcharge',
    results: [
      {
        chunk_id: 'chk-1',
        document_id: 'doc-1',
        document_title: 'Apex Master Services Agreement',
        file_name: 'msa_apex.txt',
        chunk_index: 0,
        chunk_text: 'Expedited freight requires written authorization.',
        relevance_score: 2.45,
      },
    ],
    total_retrieved: 1,
  })),
  listAuditEvents: vi.fn().mockImplementation(async () => ({ items: [mockAuditEvent], total: 1 })),
  runP2PDemoSlice: vi.fn().mockImplementation(async () => mockDemoResponse),
}))

describe('InvestigationsWorkspace Component', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders workspace title, project context and investigations table', async () => {
    render(<InvestigationsWorkspace project={mockProject} onBack={vi.fn()} />)

    expect(screen.getByText('Governed Investigation & Approvals')).toBeInTheDocument()
    expect(screen.getByText(/Phase 9 Vertical Slice/i)).toBeInTheDocument()
    expect(screen.getByText(/Procure-to-Pay Excellence/i)).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getByText('Root-Cause Investigation for INV-7844 Variance')).toBeInTheDocument()
      expect(screen.getByText('$1,250.00')).toBeInTheDocument()
    })
  })

  it('opens investigation detail inspection with verified facts vs hypotheses', async () => {
    render(<InvestigationsWorkspace project={mockProject} onBack={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByText('Inspect')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Inspect'))

    await waitFor(() => {
      expect(screen.getByText(/Deterministic Financial Impact/i)).toBeInTheDocument()
      expect(screen.getByText(/Verified Transactional Facts/i)).toBeInTheDocument()
      expect(screen.getByText(/Causal Hypotheses \(AI Generated\)/i)).toBeInTheDocument()
      expect(screen.getByText(/Candidate causal hypothesis/i)).toBeInTheDocument()
    })
  })

  it('navigates to Human Approvals tab and allows decision submission', async () => {
    render(<InvestigationsWorkspace project={mockProject} onBack={vi.fn()} />)

    fireEvent.click(screen.getByText('Human Approvals'))

    await waitFor(() => {
      expect(screen.getByText('Pending Human Approval Gates (1)')).toBeInTheDocument()
      expect(screen.getByText('Review & Decide')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Review & Decide'))

    await waitFor(() => {
      expect(screen.getByText(/Review Consequential Action Approval/i)).toBeInTheDocument()
    })

    const rationaleInput = screen.getByLabelText(/Decision Audit Rationale/i)
    fireEvent.change(rationaleInput, { target: { value: 'Verified unapproved freight. Authorization approved.' } })

    fireEvent.click(screen.getByText('Sign & Authorize'))

    await waitFor(() => {
      expect(screen.getByText(/Approval approved successfully/i)).toBeInTheDocument()
    })
  })

  it('navigates to Governed Actions tab and dispatches an approved action', async () => {
    render(<InvestigationsWorkspace project={mockProject} onBack={vi.fn()} />)

    fireEvent.click(screen.getByText('Governed Actions'))

    await waitFor(() => {
      expect(screen.getByText('Governed Action Dispatcher (1)')).toBeInTheDocument()
      expect(screen.getByText('Dispatch Action')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Dispatch Action'))

    await waitFor(() => {
      expect(screen.getByText(/Action dispatched to SimulatedTargetAdapter/i)).toBeInTheDocument()
    })
  })

  it('navigates to RAG Documents tab and queries indexed chunks', async () => {
    render(<InvestigationsWorkspace project={mockProject} onBack={vi.fn()} />)

    fireEvent.click(screen.getByText('RAG Documents'))

    await waitFor(() => {
      expect(screen.getByText('Apex Master Services Agreement')).toBeInTheDocument()
    })

    const queryInput = screen.getByPlaceholderText(/e\.g\. freight surcharge/i)
    fireEvent.change(queryInput, { target: { value: 'freight surcharge' } })

    fireEvent.click(screen.getByText('Search'))

    await waitFor(() => {
      expect(screen.getByText(/Retrieved 1 ranked chunks/i)).toBeInTheDocument()
      expect(screen.getByText(/Score: 2.450/i)).toBeInTheDocument()
    })
  })

  it('executes the full P2P Vertical Slice demonstration flow', async () => {
    render(<InvestigationsWorkspace project={mockProject} onBack={vi.fn()} />)

    fireEvent.click(screen.getByText('P2P Slice Demo'))

    await waitFor(() => {
      expect(screen.getByText(/Procure-to-Pay \(P2P\) Vertical Slice Demonstration/i)).toBeInTheDocument()
      expect(screen.getByText('Execute Full Demonstration')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Execute Full Demonstration'))

    await waitFor(() => {
      expect(screen.getByText(/P2P Vertical Slice executed successfully!/i)).toBeInTheDocument()
      expect(screen.getByText('Demonstration Execution Result')).toBeInTheDocument()
      expect(screen.getByText('1. Anomaly & Facts')).toBeInTheDocument()
      expect(screen.getByText('2. RAG Citations')).toBeInTheDocument()
      expect(screen.getByText('3. Execution & ERP')).toBeInTheDocument()
    })
  })
})
