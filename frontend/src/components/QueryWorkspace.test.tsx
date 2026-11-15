import { describe, it, expect, vi, beforeEach } from 'vitest'
import '@testing-library/jest-dom/vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryWorkspace } from './QueryWorkspace'
import type { Project } from '../types/auth'
import type {
  QuerySchemaResponse,
  StructuredQueryResponse,
  NaturalLanguageQueryResponse,
  QueryExecutionAuditResponse,
} from '../types/query'

const mockProject: Project = {
  id: 'proj-p2p',
  organization_id: 'org-test',
  name: 'P2P Reference Project',
  slug: 'p2p-reference-project',
  description: 'Procure-to-Pay query workspace',
  status: 'ACTIVE',
  created_at: '2026-11-15T08:00:00Z',
}

const mockSchema: QuerySchemaResponse = {
  project_id: 'proj-p2p',
  entities: [
    {
      name: 'Invoice',
      display_name: 'Vendor Invoice',
      description: 'Billing requests submitted by suppliers',
      properties: [
        {
          name: 'invoice_id',
          display_name: 'Invoice ID',
          data_type: 'STRING',
          is_primary_key: true,
          is_nullable: false,
          is_mapped: true,
          source_column: 'invoice_id',
        },
        {
          name: 'invoice_amount',
          display_name: 'Invoice Amount',
          data_type: 'NUMBER',
          is_primary_key: false,
          is_nullable: false,
          is_mapped: true,
          source_column: 'invoice_amount',
        },
        {
          name: 'status',
          display_name: 'Status',
          data_type: 'STRING',
          is_primary_key: false,
          is_nullable: false,
          is_mapped: true,
          source_column: 'status',
        },
      ],
      available_relationships: ['billed_by_supplier'],
    },
    {
      name: 'PurchaseOrder',
      display_name: 'Purchase Order',
      description: 'Procure-to-Pay purchase order entity',
      properties: [
        {
          name: 'po_number',
          display_name: 'PO Number',
          data_type: 'STRING',
          is_primary_key: true,
          is_nullable: false,
          is_mapped: true,
          source_column: 'po_no',
        },
      ],
      available_relationships: [],
    },
  ],
}

const mockQueryResult: StructuredQueryResponse = {
  entity_name: 'Invoice',
  columns: ['invoice_id', 'invoice_amount', 'status'],
  rows: [
    { invoice_id: 'INV-101', invoice_amount: 1500.0, status: 'PAID' },
    { invoice_id: 'INV-102', invoice_amount: 3200.5, status: 'PENDING' },
  ],
  total_count: 2,
  limit: 50,
  offset: 0,
  compiled_sql: 'SELECT Invoice.invoice_id, Invoice.invoice_amount, Invoice.status FROM Invoice LIMIT ? OFFSET ?',
  parameters: [50, 0],
  execution_time_ms: 1.25,
  query_plan: ['SEARCH TABLE Invoice'],
}

const mockNlqResponse: NaturalLanguageQueryResponse = {
  prompt: 'Show all paid invoices',
  parsed_query: {
    entity_name: 'Invoice',
    fields: ['invoice_id', 'status'],
    filters: [{ field: 'status', operator: 'eq', value: 'PAID' }],
    sorts: [],
    limit: 50,
    offset: 0,
  },
  compiled_sql: "SELECT Invoice.invoice_id, Invoice.status FROM Invoice WHERE Invoice.status = ? LIMIT ? OFFSET ?",
  explanation: 'Filtered Invoice entity where status equals PAID.',
  token_usage: {
    prompt_tokens: 45,
    completion_tokens: 30,
    total_tokens: 75,
  },
  latency_ms: 250.0,
  nlq_reference: 'mock-nlq-ref',
}

const mockHistory: QueryExecutionAuditResponse[] = [
  {
    id: 'exec-1',
    project_id: 'proj-p2p',
    user_id: 'user-1',
    entity_name: 'Invoice',
    query_ast: {
      entity_name: 'Invoice',
      fields: [],
      filters: [],
      sorts: [],
      limit: 50,
      offset: 0,
    },
    compiled_sql: 'SELECT * FROM Invoice',
    row_count: 2,
    execution_time_ms: 2.1,
    is_nlq: false,
    created_at: '2026-11-15T12:00:00Z',
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

vi.mock('../services/query', () => ({
  getQuerySchema: vi.fn().mockImplementation(async () => mockSchema),
  executeStructuredQuery: vi.fn().mockImplementation(async () => mockQueryResult),
  compileNaturalLanguageQuery: vi.fn().mockImplementation(async () => mockNlqResponse),
  getQueryHistory: vi.fn().mockImplementation(async () => mockHistory),
}))

describe('QueryWorkspace Component', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders query schema and entity selector on initial load', async () => {
    render(<QueryWorkspace project={mockProject} onBack={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByText('Structured Querying & Early AI')).toBeInTheDocument()
    })

    expect(screen.getByTestId('entity-select')).toBeInTheDocument()
    expect(screen.getByText('Vendor Invoice (Invoice)')).toBeInTheDocument()
    expect(screen.getByText('Purchase Order (PurchaseOrder)')).toBeInTheDocument()
  })

  it('allows building a filter and executing a structured query', async () => {
    render(<QueryWorkspace project={mockProject} onBack={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByTestId('execute-query-btn')).toBeInTheDocument()
    })

    // Click Add Filter
    const addFilterBtn = screen.getByTestId('add-filter-btn')
    fireEvent.click(addFilterBtn)

    // Execute query
    const execBtn = screen.getByTestId('execute-query-btn')
    fireEvent.click(execBtn)

    await waitFor(() => {
      expect(screen.getByText('INV-101')).toBeInTheDocument()
      expect(screen.getByText('INV-102')).toBeInTheDocument()
      expect(screen.getByText('2 rows returned (2 total matched)')).toBeInTheDocument()
    })
  })

  it('compiles a natural language query with the Early AI assistant', async () => {
    render(<QueryWorkspace project={mockProject} onBack={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByTestId('nlq-input')).toBeInTheDocument()
    })

    const input = screen.getByTestId('nlq-input')
    fireEvent.change(input, { target: { value: 'Show all paid invoices' } })

    const askBtn = screen.getByTestId('nlq-submit-btn')
    fireEvent.click(askBtn)

    await waitFor(() => {
      expect(screen.getByText('AI Compiled Query Successfully')).toBeInTheDocument()
      expect(screen.getByText('Filtered Invoice entity where status equals PAID.')).toBeInTheDocument()
      expect(screen.getByText('Run AI Query Directly')).toBeInTheDocument()
    })
  })

  it('supports CSV export when results are present', async () => {
    // Mock URL.createObjectURL and URL.revokeObjectURL
    const createObjectURL = vi.fn().mockReturnValue('blob:mock-url')
    const revokeObjectURL = vi.fn()
    window.URL.createObjectURL = createObjectURL
    window.URL.revokeObjectURL = revokeObjectURL

    render(<QueryWorkspace project={mockProject} onBack={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByTestId('execute-query-btn')).toBeInTheDocument()
    })

    // Execute query to get results
    fireEvent.click(screen.getByTestId('execute-query-btn'))

    await waitFor(() => {
      expect(screen.getByTestId('export-csv-btn')).toBeInTheDocument()
    })

    // Click Export CSV
    fireEvent.click(screen.getByTestId('export-csv-btn'))
    expect(createObjectURL).toHaveBeenCalled()
  })
})
