import { describe, it, expect, vi, beforeEach } from 'vitest'
import '@testing-library/jest-dom/vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MonitorsWorkspace } from './MonitorsWorkspace'
import type { Project } from '../types/auth'
import type {
  Monitor,
  Finding,
  MonitorEvaluation,
} from '../types/monitors'

const mockProject: Project = {
  id: 'proj-p2p',
  organization_id: 'org-test',
  name: 'P2P Test Project',
  slug: 'p2p-test-project',
  description: 'Procure-to-Pay monitoring workspace',
  status: 'ACTIVE',
  created_at: '2026-11-15T08:00:00Z',
}

const mockMonitors: Monitor[] = [
  {
    id: 'mon-1',
    project_id: 'proj-p2p',
    name: 'High Value PO Monitor',
    description: 'Tracks purchase orders above $10,000 threshold',
    target_type: 'ENTITY',
    target_id: 'PurchaseOrder',
    schedule_cron: '0 * * * *',
    status: 'ACTIVE',
    last_run_at: '2026-11-16T08:00:00Z',
    last_status: 'SUCCESS',
    created_at: '2026-11-16T07:00:00Z',
    updated_at: '2026-11-16T07:00:00Z',
    open_findings_count: 1,
    total_findings_count: 2,
    rules: [
      {
        id: 'rule-1',
        monitor_id: 'mon-1',
        rule_code: 'PO_VALUE_LIMIT',
        description: 'PO amount > 10,000',
        severity: 'HIGH',
        rule_type: 'THRESHOLD',
        field_name: 'total_amount',
        operator: 'gt',
        threshold_value: 10000.0,
        threshold_string: null,
        secondary_field: null,
        parameters_json: null,
        created_at: '2026-11-16T07:00:00Z',
        updated_at: '2026-11-16T07:00:00Z',
      },
    ],
  },
]

const mockFindings: Finding[] = [
  {
    id: 'find-1',
    project_id: 'proj-p2p',
    monitor_id: 'mon-1',
    rule_id: 'rule-1',
    process_case_id: null,
    entity_type: 'PurchaseOrder',
    entity_id: 'PO-8002',
    finding_type: 'THRESHOLD',
    severity: 'HIGH',
    status: 'OPEN',
    summary: "PurchaseOrder 'PO-8002' total_amount=16000.00 exceeds threshold (gt 10000.0)",
    deduplication_hash: 'abc123hash',
    observed_value: '16000.00',
    threshold_value: '10000.0',
    verified_context_json: {
      po_number: 'PO-8002',
      supplier: 'Beta Logistics',
      total_amount: 16000.0,
    },
    detected_at: '2026-11-16T08:05:00Z',
    acknowledged_at: null,
    acknowledged_by: null,
    resolved_at: null,
    resolved_by: null,
    resolution_notes: null,
  },
]

const mockEvaluations: MonitorEvaluation[] = [
  {
    id: 'eval-1',
    project_id: 'proj-p2p',
    monitor_id: 'mon-1',
    status: 'SUCCESS',
    records_evaluated: 5,
    findings_detected: 1,
    execution_duration_ms: 24.5,
    summary_json: { target_type: 'ENTITY', rules_evaluated: 1 },
    error_message: null,
    evaluated_at: '2026-11-16T08:00:00Z',
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

vi.mock('../services/monitors', () => ({
  listMonitors: vi.fn().mockImplementation(async () => mockMonitors),
  createMonitor: vi.fn().mockImplementation(async (_t, _o, _p, data) => ({
    id: 'mon-new',
    project_id: 'proj-p2p',
    name: data.name,
    description: data.description,
    target_type: data.target_type,
    target_id: data.target_id,
    schedule_cron: null,
    status: 'ACTIVE',
    last_run_at: null,
    last_status: null,
    created_at: '2026-11-16T09:00:00Z',
    updated_at: '2026-11-16T09:00:00Z',
    open_findings_count: 0,
    total_findings_count: 0,
    rules: [],
  })),
  updateMonitor: vi.fn().mockImplementation(async () => mockMonitors[0]),
  deleteMonitor: vi.fn().mockImplementation(async () => {}),
  addRule: vi.fn().mockImplementation(async () => mockMonitors[0].rules[0]),
  deleteRule: vi.fn().mockImplementation(async () => {}),
  evaluateMonitor: vi.fn().mockImplementation(async () => ({
    id: 'eval-run',
    project_id: 'proj-p2p',
    monitor_id: 'mon-1',
    status: 'SUCCESS',
    records_evaluated: 10,
    findings_detected: 2,
    execution_duration_ms: 18.2,
    summary_json: {},
    error_message: null,
    evaluated_at: '2026-11-16T09:30:00Z',
  })),
  listFindings: vi.fn().mockImplementation(async () => mockFindings),
  getFinding: vi.fn().mockImplementation(async () => mockFindings[0]),
  updateFindingStatus: vi.fn().mockImplementation(async (_t, _o, _p, id, req) => ({
    ...mockFindings[0],
    id,
    status: req.status,
    resolution_notes: req.resolution_notes || null,
  })),
  listEvaluations: vi.fn().mockImplementation(async () => mockEvaluations),
}))

describe('MonitorsWorkspace Component', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders monitors workspace and displays configured monitors', async () => {
    render(<MonitorsWorkspace project={mockProject} onBack={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByText('High Value PO Monitor')).toBeInTheDocument()
    })

    expect(screen.getByText('Adaptive Monitors & Exception Detection')).toBeInTheDocument()
    expect(screen.getByText('PO_VALUE_LIMIT')).toBeInTheDocument()
    expect(screen.getByText('Evaluate Now')).toBeInTheDocument()
  })

  it('opens create monitor modal and creates monitor', async () => {
    render(<MonitorsWorkspace project={mockProject} onBack={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByText('High Value PO Monitor')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('New Monitor'))
    expect(screen.getByText('Create Operational Monitor')).toBeInTheDocument()

    const nameInput = screen.getByPlaceholderText(/High Value Purchase Order Monitor/i)
    fireEvent.change(nameInput, { target: { value: 'New Test Monitor' } })

    const submitBtn = screen.getByRole('button', { name: /create monitor/i })
    fireEvent.click(submitBtn)

    await waitFor(() => {
      expect(screen.getByText(/Created monitor "New Test Monitor" successfully/i)).toBeInTheDocument()
    })
  })

  it('executes manual evaluate trigger and displays summary banner', async () => {
    render(<MonitorsWorkspace project={mockProject} onBack={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByText('High Value PO Monitor')).toBeInTheDocument()
    })

    const evalBtn = screen.getByText('Evaluate Now')
    fireEvent.click(evalBtn)

    await waitFor(() => {
      expect(screen.getByText(/Evaluation run completed/i)).toBeInTheDocument()
    })
  })

  it('navigates to findings tab, opens details, acknowledges and resolves finding', async () => {
    render(<MonitorsWorkspace project={mockProject} onBack={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByText('High Value PO Monitor')).toBeInTheDocument()
    })

    // Click Findings tab
    const findingsTab = screen.getByText('Operational Exceptions & Findings')
    fireEvent.click(findingsTab)

    await waitFor(() => {
      expect(screen.getByText('PO-8002')).toBeInTheDocument()
    })

    // Click Details button
    fireEvent.click(screen.getByText('Details'))

    await waitFor(() => {
      expect(screen.getByText('Exception Finding Details')).toBeInTheDocument()
      expect(screen.getByText('abc123hash')).toBeInTheDocument()
    })

    // Click Acknowledge
    const ackBtn = screen.getByText('Acknowledge Exception')
    fireEvent.click(ackBtn)

    await waitFor(() => {
      expect(screen.getByText(/acknowledged/i)).toBeInTheDocument()
    })

    // Click Resolve
    const resolveBtn = screen.getByText('Resolve Exception')
    fireEvent.click(resolveBtn)

    await waitFor(() => {
      expect(screen.getByText('Resolve Operational Exception')).toBeInTheDocument()
    })

    const notesInput = screen.getByPlaceholderText(/Price variance verified/i)
    fireEvent.change(notesInput, { target: { value: 'Approved by procurement lead.' } })

    const confirmBtn = screen.getByText('Confirm Resolution')
    fireEvent.click(confirmBtn)

    await waitFor(() => {
      expect(screen.getByText(/resolved with audit note/i)).toBeInTheDocument()
    })
  })

  it('navigates to evaluation audit tab and displays run history', async () => {
    render(<MonitorsWorkspace project={mockProject} onBack={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByText('High Value PO Monitor')).toBeInTheDocument()
    })

    const auditTab = screen.getByText('Evaluation Run Audit')
    fireEvent.click(auditTab)

    await waitFor(() => {
      expect(screen.getByText('24.5 ms')).toBeInTheDocument()
    })
  })
})
