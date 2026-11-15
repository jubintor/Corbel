import { describe, it, expect, vi, beforeEach } from 'vitest'
import '@testing-library/jest-dom/vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DatasetWorkspace } from './DatasetWorkspace'
import type { Dataset } from '../types/dataset'
import type { Project } from '../types/auth'

const mockProject: Project = {
  id: 'proj-123',
  organization_id: 'org-456',
  name: 'Procure-to-Pay Intelligence',
  slug: 'p2p-intelligence',
  description: 'P2P test workspace',
  status: 'ACTIVE',
  created_at: '2026-11-15T09:00:00Z',
}

const mockDataset: Dataset = {
  id: 'ds-789',
  project_id: 'proj-123',
  data_source_id: 'src-111',
  name: 'suppliers',
  description: 'Vendor master catalog',
  status: 'PROFILED',
  created_at: '2026-11-15T09:30:00Z',
  updated_at: '2026-11-15T09:30:00Z',
  version_count: 1,
  latest_version: {
    id: 'ver-001',
    dataset_id: 'ds-789',
    project_id: 'proj-123',
    version_number: 1,
    file_format: 'CSV',
    file_size_bytes: 4096,
    checksum_hash: 'abc123sha256hash',
    record_count: 150,
    column_count: 4,
    status: 'READY',
    imported_at: '2026-11-15T09:30:00Z',
    schema_metadata: [
      { name: 'supplier_id', data_type: 'STRING', nullable: false, sample_values: ['SUP-1', 'SUP-2'] },
      { name: 'total_spend', data_type: 'FLOAT', nullable: true, sample_values: [1500.5, 9200.0] },
    ],
    profiling_summary: {
      total_rows: 150,
      total_columns: 4,
      duplicate_rows_count: 0,
      duplicate_rows_pct: 0,
      columns: [
        {
          column_name: 'supplier_id',
          detected_type: 'STRING',
          total_count: 150,
          null_count: 0,
          non_null_count: 150,
          null_percentage: 0,
          distinct_count: 150,
          unique_percentage: 100,
          sample_values: ['SUP-1'],
          quality_warnings: ['POTENTIAL_PRIMARY_KEY'],
        },
        {
          column_name: 'total_spend',
          detected_type: 'FLOAT',
          total_count: 150,
          null_count: 5,
          non_null_count: 145,
          null_percentage: 3.33,
          distinct_count: 140,
          unique_percentage: 93.33,
          sample_values: [1500.5],
          numeric_stats: {
            min: 100.0,
            max: 50000.0,
            mean: 12500.0,
            stddev: 8500.0,
            median: 9500.0,
            sum: 1812500.0,
            zeros_count: 0,
          },
          quality_warnings: [],
        },
      ],
      dataset_quality_warnings: [],
      profiled_at: '2026-11-15T09:30:00Z',
    },
  },
}

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 'u1', email: 'test@example.com', full_name: 'Tester' },
    token: 'fake-jwt-token',
    activeOrg: { id: 'org-456', name: 'Acme Corp', slug: 'acme', role: 'ORG_ADMIN' },
  }),
}))

describe('DatasetWorkspace Component', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders dataset list when datasets are loaded', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [mockDataset],
    }) as unknown as typeof fetch

    await act(async () => {
      render(<DatasetWorkspace project={mockProject} onBack={vi.fn()} />)
    })

    expect(screen.getByText('Procure-to-Pay Intelligence')).toBeInTheDocument()
    expect(screen.getByText('Data Intelligence')).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getByText('suppliers')).toBeInTheDocument()
      expect(screen.getByText('CSV')).toBeInTheDocument()
      expect(screen.getByText('150')).toBeInTheDocument()
      expect(screen.getByText('PROFILED')).toBeInTheDocument()
    })
  })

  it('opens upload dataset modal when clicking Upload Dataset', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [],
    }) as unknown as typeof fetch

    const user = userEvent.setup()
    await act(async () => {
      render(<DatasetWorkspace project={mockProject} onBack={vi.fn()} />)
    })

    const uploadButtons = screen.getAllByRole('button', { name: /Upload Dataset/i })
    await user.click(uploadButtons[0])

    expect(screen.getByText('Upload & Profile Dataset')).toBeInTheDocument()
    expect(screen.getByLabelText(/Select Tabular File/i)).toBeInTheDocument()
  })

  it('inspects dataset details, schema, and profiling metrics', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [mockDataset],
    }) as unknown as typeof fetch

    const user = userEvent.setup()
    await act(async () => {
      render(<DatasetWorkspace project={mockProject} onBack={vi.fn()} />)
    })

    await waitFor(() => {
      expect(screen.getByText('suppliers')).toBeInTheDocument()
    })

    const inspectBtn = screen.getByRole('button', { name: /Inspect Profile/i })
    await user.click(inspectBtn)

    // Verify Inspector Header & Tabs
    expect(screen.getByText('Close Inspection')).toBeInTheDocument()
    expect(screen.getByText('Discovered Schema')).toBeInTheDocument()
    expect(screen.getByText('Data Profiling Metrics')).toBeInTheDocument()

    // Switch to Profiling tab
    const profilingTab = screen.getByRole('button', { name: /Data Profiling Metrics/i })
    await user.click(profilingTab)

    expect(screen.getByText('POTENTIAL_PRIMARY_KEY')).toBeInTheDocument()
    expect(screen.getByText('1812500')).toBeInTheDocument() // sum
  })
})
