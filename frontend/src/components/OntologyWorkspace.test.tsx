import { describe, it, expect, vi, beforeEach } from 'vitest'
import '@testing-library/jest-dom/vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { OntologyWorkspace } from './OntologyWorkspace'
import type { Project } from '../types/auth'
import type {
  BusinessObject,
  Relationship,
  PropertyMapping,
  SemanticDiscoveryResponse,
  OntologyGraphResponse,
} from '../types/ontology'
import type { Dataset } from '../types/dataset'

const mockProject: Project = {
  id: 'proj-p2p',
  organization_id: 'org-test',
  name: 'P2P Reference Project',
  slug: 'p2p-reference-project',
  description: 'Procure-to-Pay ontology testing workspace',
  status: 'ACTIVE',
  created_at: '2026-11-15T08:00:00Z',
}

const mockBusinessObjects: BusinessObject[] = [
  {
    id: 'obj-po',
    project_id: 'proj-p2p',
    name: 'PurchaseOrder',
    display_name: 'Purchase Order',
    description: 'Procure-to-Pay purchase order entity',
    primary_key_property: 'po_number',
    version: 1,
    property_count: 3,
    created_at: '2026-11-15T08:30:00Z',
    updated_at: '2026-11-15T08:30:00Z',
    properties: [
      {
        id: 'prop-po-num',
        business_object_id: 'obj-po',
        name: 'po_number',
        display_name: 'PO Number',
        data_type: 'STRING',
        is_nullable: false,
        is_primary_key: true,
        description: 'Canonical purchase order identifier',
        source_mapping: null,
        created_at: '2026-11-15T08:30:00Z',
      },
      {
        id: 'prop-po-amt',
        business_object_id: 'obj-po',
        name: 'total_amount',
        display_name: 'Total Amount',
        data_type: 'NUMBER',
        is_nullable: false,
        is_primary_key: false,
        description: 'Total monetary value',
        source_mapping: null,
        created_at: '2026-11-15T08:30:00Z',
      },
      {
        id: 'prop-po-status',
        business_object_id: 'obj-po',
        name: 'status',
        display_name: 'Status',
        data_type: 'STRING',
        is_nullable: true,
        is_primary_key: false,
        description: 'Order status lifecycle',
        source_mapping: null,
        created_at: '2026-11-15T08:30:00Z',
      },
    ],
  },
  {
    id: 'obj-sup',
    project_id: 'proj-p2p',
    name: 'Supplier',
    display_name: 'Supplier',
    description: 'Procure-to-Pay vendor entity',
    primary_key_property: 'supplier_id',
    version: 1,
    property_count: 1,
    created_at: '2026-11-15T08:30:00Z',
    updated_at: '2026-11-15T08:30:00Z',
    properties: [
      {
        id: 'prop-sup-id',
        business_object_id: 'obj-sup',
        name: 'supplier_id',
        display_name: 'Supplier ID',
        data_type: 'STRING',
        is_nullable: false,
        is_primary_key: true,
        description: 'Vendor identifier',
        source_mapping: null,
        created_at: '2026-11-15T08:30:00Z',
      },
    ],
  },
]

const mockRelationships: Relationship[] = [
  {
    id: 'rel-supplies',
    project_id: 'proj-p2p',
    name: 'supplies',
    source_object_id: 'obj-sup',
    source_object_name: 'Supplier',
    target_object_id: 'obj-po',
    target_object_name: 'PurchaseOrder',
    cardinality: 'ONE_TO_MANY',
    description: 'Supplier fulfills purchase orders',
    join_expression: { foreign_key_property: 'supplier_id' },
    created_at: '2026-11-15T08:30:00Z',
  },
]

const mockGraph: OntologyGraphResponse = {
  project_id: 'proj-p2p',
  nodes: [],
  edges: [],
  total_objects: 2,
  total_relationships: 1,
  total_mapped_properties: 0,
}

const mockDatasets: Dataset[] = [
  {
    id: 'ds-po',
    project_id: 'proj-p2p',
    data_source_id: 'ds-src-1',
    name: 'p2p_purchase_orders.csv',
    status: 'READY',
    created_at: '2026-11-15T08:00:00Z',
    updated_at: '2026-11-15T08:00:00Z',
    version_count: 1,
    latest_version: {
      id: 'ver-po-1',
      dataset_id: 'ds-po',
      project_id: 'proj-p2p',
      version_number: 1,
      file_format: 'CSV',
      file_size_bytes: 1024,
      record_count: 8,
      column_count: 7,
      status: 'READY',
      checksum_hash: 'abcdef123456',
      imported_at: '2026-11-15T08:00:00Z',
    },
  },
]

const mockDiscoveryResult: SemanticDiscoveryResponse = {
  dataset_id: 'ds-po',
  dataset_version_id: 'ver-po-1',
  business_object_id: 'obj-po',
  business_object_name: 'PurchaseOrder',
  total_suggested: 1,
  suggestions: [
    {
      id: 'sugg-1',
      project_id: 'proj-p2p',
      property_id: 'prop-po-num',
      property_name: 'po_number',
      business_object_id: 'obj-po',
      business_object_name: 'PurchaseOrder',
      dataset_id: 'ds-po',
      dataset_name: 'p2p_purchase_orders.csv',
      dataset_version_id: 'ver-po-1',
      column_name: 'po_number',
      confidence: 1.0,
      status: 'SUGGESTED',
      explanation: 'Exact name match (case-insensitive); Type compatible: STRING -> STRING (confidence 1.00)',
      created_at: '2026-11-15T08:35:00Z',
    },
  ],
}

const mockConfirmedMapping: PropertyMapping = {
  id: 'sugg-1',
  project_id: 'proj-p2p',
  property_id: 'prop-po-num',
  property_name: 'po_number',
  business_object_id: 'obj-po',
  business_object_name: 'PurchaseOrder',
  dataset_id: 'ds-po',
  dataset_name: 'p2p_purchase_orders.csv',
  dataset_version_id: 'ver-po-1',
  column_name: 'po_number',
  confidence: 1.0,
  status: 'CONFIRMED',
  explanation: 'Exact name match (case-insensitive); Type compatible: STRING -> STRING (confidence 1.00)',
  created_at: '2026-11-15T08:35:00Z',
}

const mockAuth = {
  user: { id: 'u1', email: 'test@example.com', full_name: 'Tester' },
  token: 'fake-jwt-token',
  activeOrg: { id: 'org-test', name: 'Test Org', slug: 'test-org', role: 'ORG_ADMIN' },
}

vi.mock('../context/AuthContext', () => ({
  useAuth: () => mockAuth,
}))

vi.mock('../services/datasets', () => ({
  listProjectDatasets: vi.fn().mockImplementation(async () => mockDatasets),
}))

vi.mock('../services/ontology', () => ({
  listBusinessObjects: vi.fn().mockImplementation(async () => mockBusinessObjects),
  getBusinessObject: vi.fn().mockImplementation(async (_t, _o, _p, id) => {
    return mockBusinessObjects.find((b) => b.id === id) || mockBusinessObjects[0]
  }),
  createBusinessObject: vi.fn(),
  deleteBusinessObject: vi.fn(),
  addProperty: vi.fn(),
  deleteProperty: vi.fn(),
  listRelationships: vi.fn().mockImplementation(async () => mockRelationships),
  createRelationship: vi.fn(),
  deleteRelationship: vi.fn(),
  seedP2POntology: vi.fn().mockImplementation(async () => mockBusinessObjects),
  getOntologyGraph: vi.fn().mockImplementation(async () => mockGraph),
  listPropertyMappings: vi.fn().mockImplementation(async () => []),
  discoverSemanticMappings: vi.fn().mockImplementation(async () => mockDiscoveryResult),
  acceptMapping: vi.fn().mockImplementation(async () => mockConfirmedMapping),
  rejectMapping: vi.fn(),
  deletePropertyMapping: vi.fn(),
}))

describe('OntologyWorkspace Component', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders ontology header and seeded business entities with properties', async () => {
    await act(async () => {
      render(<OntologyWorkspace project={mockProject} onBack={vi.fn()} />)
    })

    await waitFor(() => {
      expect(screen.getByText('Ontology Engine & Semantic Discovery')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Seed P2P Ontology/i })).toBeInTheDocument()
      expect(screen.getByText('Entities & Properties (2)')).toBeInTheDocument()
      expect(screen.getAllByText('Purchase Order').length).toBeGreaterThanOrEqual(1)
      expect(screen.getByText('Supplier')).toBeInTheDocument()
    })

    // Verify properties table for active entity (Purchase Order)
    await waitFor(() => {
      expect(screen.getAllByText('po_number').length).toBeGreaterThanOrEqual(1)
      expect(screen.getByText('PRIMARY KEY')).toBeInTheDocument()
      expect(screen.getByText('total_amount')).toBeInTheDocument()
    })
  })

  it('invokes seedP2POntology when clicking Seed P2P Ontology button', async () => {
    const user = userEvent.setup()
    const { seedP2POntology } = await import('../services/ontology')

    await act(async () => {
      render(<OntologyWorkspace project={mockProject} onBack={vi.fn()} />)
    })

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Seed P2P Ontology/i })).toBeInTheDocument()
    })

    const seedBtn = screen.getByRole('button', { name: /Seed P2P Ontology/i })
    await act(async () => {
      await user.click(seedBtn)
    })

    await waitFor(() => {
      expect(seedP2POntology).toHaveBeenCalledWith('fake-jwt-token', 'org-test', 'proj-p2p')
      expect(screen.getByText(/Successfully initialized P2P Canonical Ontology/i)).toBeInTheDocument()
    })
  })

  it('renders relationships and knowledge graph summary in Relationships tab', async () => {
    const user = userEvent.setup()

    await act(async () => {
      render(<OntologyWorkspace project={mockProject} onBack={vi.fn()} />)
    })

    await waitFor(() => {
      expect(screen.getByText(/Relationships & Graph/i)).toBeInTheDocument()
    })

    const relTab = screen.getByRole('button', { name: /Relationships & Graph/i })
    await act(async () => {
      await user.click(relTab)
    })

    await waitFor(() => {
      expect(screen.getByText('Typed Relationships & Knowledge Graph')).toBeInTheDocument()
      expect(screen.getByText('Supplier fulfills purchase orders')).toBeInTheDocument()
      expect(screen.getByText('ONE_TO_MANY')).toBeInTheDocument()
    })
  })

  it('runs semantic discovery and allows accepting candidate suggestions', async () => {
    const user = userEvent.setup()
    const { discoverSemanticMappings, acceptMapping } = await import('../services/ontology')

    await act(async () => {
      render(<OntologyWorkspace project={mockProject} onBack={vi.fn()} />)
    })

    // Navigate to Semantic Discovery tab
    const discTab = screen.getByRole('button', { name: /Semantic Discovery/i })
    await act(async () => {
      await user.click(discTab)
    })

    await waitFor(() => {
      expect(screen.getByText('Deterministic Semantic Discovery & Human Approval Gate')).toBeInTheDocument()
      expect(screen.getByText(/Configure Discovery Run/i)).toBeInTheDocument()
    })

    // Select target business object
    const selects = screen.getAllByRole('combobox')
    // Select 1: Dataset, Select 2: Target Entity
    await act(async () => {
      await user.selectOptions(selects[1], 'obj-po')
    })

    // Click Discover Candidate Mappings
    const discoverBtn = screen.getByRole('button', { name: /Discover Candidate Mappings/i })
    await act(async () => {
      await user.click(discoverBtn)
    })

    await waitFor(() => {
      expect(discoverSemanticMappings).toHaveBeenCalledWith('fake-jwt-token', 'org-test', 'proj-p2p', {
        dataset_id: 'ds-po',
        dataset_version_id: 'ver-po-1',
        business_object_id: 'obj-po',
      })
      expect(screen.getByText('Exact name match (case-insensitive); Type compatible: STRING -> STRING (confidence 1.00)')).toBeInTheDocument()
      expect(screen.getByText('100%')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Accept' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Reject' })).toBeInTheDocument()
    })

    // Accept suggestion
    const acceptBtn = screen.getByRole('button', { name: 'Accept' })
    await act(async () => {
      await user.click(acceptBtn)
    })

    await waitFor(() => {
      expect(acceptMapping).toHaveBeenCalledWith('fake-jwt-token', 'org-test', 'proj-p2p', 'sugg-1')
      expect(screen.getByText('CONFIRMED')).toBeInTheDocument()
      expect(screen.getByText('Approved & Active')).toBeInTheDocument()
    })
  })
})
