import { describe, it, expect, vi, beforeEach } from 'vitest'
import '@testing-library/jest-dom/vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { PublishedAppPortal } from './PublishedAppPortal'
import * as appBuilderService from '../../services/appBuilder'
import type { PublishedApplicationRuntimeResponse } from '../../types/api_generated'

const mockRuntime: PublishedApplicationRuntimeResponse = {
  application_id: 'app-1',
  name: 'P2P Operations Hub',
  description: 'Live monitoring and triage',
  version: 2,
  published_at: '2026-11-18T10:00:00Z',
  user_roles: ['PROJECT_LEAD'],
  definition: {
    app_id: 'app-1',
    name: 'P2P Operations Hub',
    description: 'Live monitoring and triage',
    navigation: {
      title: 'Main Navigation',
      default_page_id: 'page_triage',
      items: [
        { page_id: 'page_triage', label: 'Triage Queue' },
        { page_id: 'page_analytics', label: 'Spend Analytics' },
      ],
    },
    pages: [
      {
        id: 'page_triage',
        title: 'Triage Queue',
        sections: [
          {
            id: 'sec_1',
            title: 'Exceptions Table',
            layout: 'SINGLE',
            components: [
              {
                id: 'comp_table',
                component_type: 'DATA_TABLE',
                title: 'Unmatched Invoices',
                data_binding: {
                  source_type: 'ONTOLOGY_OBJECT',
                  entity_name: 'Invoice',
                  limit: 25,
                },
              },
              {
                id: 'comp_btn_hold',
                component_type: 'ACTION_BUTTON',
                title: 'Hold Payment',
                properties: { label: 'Hold Selected Invoice', variant: 'danger' },
                interaction: {
                  action_type: 'EXECUTE_ACTION',
                  governed_action_type: 'HOLD_INVOICE',
                },
              },
            ],
          },
        ],
      },
      {
        id: 'page_analytics',
        title: 'Spend Analytics',
        sections: [
          {
            id: 'sec_2',
            title: 'Analytics Metrics',
            layout: 'TWO_COLUMNS',
            components: [
              {
                id: 'comp_metric_spend',
                component_type: 'METRIC_CARD',
                title: 'Total At Risk',
                properties: { value: '$145,200', unit: 'USD' },
              },
            ],
          },
        ],
      },
    ],
  },
}

describe('PublishedAppPortal Component', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(appBuilderService, 'getRuntimeDefinition').mockResolvedValue(mockRuntime)
    vi.spyOn(appBuilderService, 'queryRuntimeData').mockResolvedValue({
      component_id: 'comp_table',
      columns: ['invoice_number', 'amount', 'status'],
      rows: [
        { invoice_number: 'INV-1001', amount: 15400, status: 'PRICE_VARIANCE' },
        { invoice_number: 'INV-1002', amount: 8200, status: 'QUANTITY_MISMATCH' },
      ],
      total_rows: 2,
      execution_time_ms: 12.5,
    })
    vi.spyOn(appBuilderService, 'executeRuntimeAction').mockResolvedValue({
      status: 'SUCCESS',
      message: 'Invoice hold submitted.',
      requires_approval: false,
    })
  })

  it('renders published app header, navigation pages, and data components', async () => {
    render(
      <PublishedAppPortal
        token="token"
        orgId="org-1"
        projectId="proj-1"
        appId="app-1"
        onBack={vi.fn()}
      />
    )

    await waitFor(() => {
      expect(screen.getByText('P2P Operations Hub')).toBeInTheDocument()
      expect(screen.getByText(/Live v/)).toBeInTheDocument()
      expect(screen.getByText('Triage Queue')).toBeInTheDocument()
      expect(screen.getByText('Spend Analytics')).toBeInTheDocument()
      expect(screen.getByText('Unmatched Invoices')).toBeInTheDocument()
      expect(screen.getByText('INV-1001')).toBeInTheDocument()
    })
  })

  it('switches pages when clicking on page navigation tabs', async () => {
    render(
      <PublishedAppPortal
        token="token"
        orgId="org-1"
        projectId="proj-1"
        appId="app-1"
        onBack={vi.fn()}
      />
    )

    await waitFor(() => {
      expect(screen.getByText('Triage Queue')).toBeInTheDocument()
    })

    const analyticsTab = screen.getByText('Spend Analytics')
    fireEvent.click(analyticsTab)

    await waitFor(() => {
      expect(screen.getByText('Total At Risk')).toBeInTheDocument()
      expect(screen.getByText('$145,200')).toBeInTheDocument()
    })
  })

  it('dispatches action when clicking action button and shows feedback notice', async () => {
    render(
      <PublishedAppPortal
        token="token"
        orgId="org-1"
        projectId="proj-1"
        appId="app-1"
        onBack={vi.fn()}
      />
    )

    await waitFor(() => {
      expect(screen.getByText('Hold Selected Invoice')).toBeInTheDocument()
    })

    const actionBtn = screen.getByText('Hold Selected Invoice')
    fireEvent.click(actionBtn)

    await waitFor(() => {
      expect(appBuilderService.executeRuntimeAction).toHaveBeenCalledWith(
        'token',
        'org-1',
        'proj-1',
        'app-1',
        expect.objectContaining({
          action_type: 'EXECUTE_ACTION',
          component_id: 'comp_btn_hold',
        })
      )
      expect(screen.getByText('Invoice hold submitted.')).toBeInTheDocument()
    })
  })

  it('enforces component visibility roles hiding restricted components when user lacks role (DEF-012-003)', async () => {
    const runtimeWithRoleRestrictions: PublishedApplicationRuntimeResponse = {
      ...mockRuntime,
      user_roles: ['ANALYST'],
      definition: {
        ...mockRuntime.definition,
        pages: [
          {
            id: 'page_triage',
            title: 'Triage Queue',
            sections: [
              {
                id: 'sec_1',
                title: 'Exceptions Table',
                layout: 'SINGLE',
                components: [
                  {
                    id: 'comp_table',
                    component_type: 'DATA_TABLE',
                    title: 'Public Invoices',
                    visibility_roles: [],
                  },
                  {
                    id: 'comp_secret_admin_table',
                    component_type: 'DATA_TABLE',
                    title: 'Restricted Executive Summary',
                    visibility_roles: ['PROJECT_LEAD', 'ORG_ADMIN'],
                  },
                ],
              },
            ],
          },
        ],
      },
    }

    vi.spyOn(appBuilderService, 'getRuntimeDefinition').mockResolvedValue(runtimeWithRoleRestrictions)

    render(
      <PublishedAppPortal
        token="token"
        orgId="org-1"
        projectId="proj-1"
        appId="app-1"
        onBack={vi.fn()}
      />
    )

    await waitFor(() => {
      // Public component is visible
      expect(screen.getByText('Public Invoices')).toBeInTheDocument()
      // Restricted component is NOT rendered for ANALYST
      expect(screen.queryByText('Restricted Executive Summary')).not.toBeInTheDocument()
    })
  })
})
