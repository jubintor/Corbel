import { useState } from 'react'
import type {
  ComponentInstance,
  RuntimeDataQueryResponse,
} from '../../types/api_generated'

interface ComponentRendererProps {
  component: ComponentInstance
  data?: RuntimeDataQueryResponse | null
  loading?: boolean
  isDesignMode?: boolean
  onAction?: (actionType: string, payload: Record<string, unknown>) => Promise<void>
  onSelectComponent?: (componentId: string) => void
  isSelected?: boolean
  userRoles?: string[]
}

export function ComponentRenderer({
  component,
  data,
  loading = false,
  isDesignMode = false,
  onAction,
  onSelectComponent,
  isSelected = false,
  userRoles,
}: ComponentRendererProps) {
  const [rationale, setRationale] = useState('')
  const [actionInProgress, setActionInProgress] = useState(false)
  const props = component.properties || {}

  // Role-based visibility enforcement for runtime mode (DEF-012-003)
  if (!isDesignMode && component.visibility_roles && component.visibility_roles.length > 0 && userRoles) {
    const isAuthorized = userRoles.includes('ORG_ADMIN') || component.visibility_roles.some((r) => userRoles.includes(r))
    if (!isAuthorized) {
      return null
    }
  }

  const handleActionClick = async (actionType: string, extraPayload: Record<string, unknown> = {}) => {
    if (!onAction) return
    setActionInProgress(true)
    try {
      await onAction(actionType, {
        component_id: component.id,
        ...extraPayload,
      })
    } finally {
      setActionInProgress(false)
    }
  }

  // Wrapper for design mode selection
  const wrapperClass = `relative transition-all rounded-xl ${
    isDesignMode
      ? `cursor-pointer border-2 ${
          isSelected
            ? 'border-indigo-500 ring-2 ring-indigo-500/30'
            : 'border-dashed border-slate-700 hover:border-slate-500'
        } p-3`
      : 'border border-slate-800 bg-slate-900/90 shadow-lg'
  }`

  const handleClick = (e: React.MouseEvent) => {
    if (isDesignMode && onSelectComponent) {
      e.stopPropagation()
      onSelectComponent(component.id)
    }
  }

  const renderContent = () => {
    switch (component.component_type) {
      case 'METRIC_CARD': {
        const title = (props.title as string) || component.title || component.id
        let value = (props.value as string) || '0'
        if (data && data.rows && data.rows.length > 0) {
          const firstRow = data.rows[0]
          const metricCol = (props.metric_column as string) || (data.columns && data.columns.length > 0 ? data.columns[0] : undefined)
          if (metricCol && firstRow[metricCol] !== undefined) {
            value = String(firstRow[metricCol])
          }
        }
        const unit = (props.unit as string) || ''
        const trend = (props.trend as string) || 'neutral'
        const subtitle = (props.subtitle as string) || ''

        return (
          <div className="p-4 bg-slate-900 rounded-xl">
            <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
              <span className="font-medium truncate">{title}</span>
              {trend === 'up' && <span className="text-emerald-400 font-bold">↑</span>}
              {trend === 'down' && <span className="text-rose-400 font-bold">↓</span>}
            </div>
            <div className="text-2xl font-bold text-white tracking-tight flex items-baseline gap-1">
              <span>{loading ? '...' : value}</span>
              {unit && <span className="text-xs font-normal text-slate-400">{unit}</span>}
            </div>
            {subtitle && <p className="text-[11px] text-slate-500 mt-1">{subtitle}</p>}
          </div>
        )
      }

      case 'DATA_TABLE':
      case 'MONITOR_FINDINGS_LIST': {
        const title = (props.title as string) || component.title || 'Data Records'
        const columns = data?.columns || (props.columns as string[]) || ['id', 'status']
        const rows = data?.rows || []

        return (
          <div className="p-4 bg-slate-900 rounded-xl space-y-3">
            <div className="flex items-center justify-between">
              <h4 className="text-sm font-semibold text-white">{title}</h4>
              <span className="text-xs text-slate-400 font-mono">
                {loading ? 'Loading...' : `${data?.total_rows ?? rows.length} records`}
              </span>
            </div>

            <div className="overflow-x-auto max-h-72 border border-slate-800 rounded-lg">
              <table className="w-full text-left text-xs text-slate-300">
                <thead className="bg-slate-950 text-slate-400 uppercase text-[10px] tracking-wider sticky top-0 border-b border-slate-800">
                  <tr>
                    {columns.map((c) => (
                      <th key={c} className="px-3 py-2 font-medium">
                        {c.replace(/_/g, ' ')}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-mono text-[11px]">
                  {rows.length === 0 ? (
                    <tr>
                      <td colSpan={columns.length} className="px-3 py-6 text-center text-slate-500">
                        {loading ? 'Fetching records...' : 'No records found'}
                      </td>
                    </tr>
                  ) : (
                    rows.map((row, idx) => (
                      <tr key={idx} className="hover:bg-slate-800/40 transition-colors">
                        {columns.map((c) => {
                          const val = row[c]
                          return (
                            <td key={c} className="px-3 py-2 whitespace-nowrap">
                              {typeof val === 'object' && val !== null ? JSON.stringify(val) : String(val ?? '—')}
                            </td>
                          )
                        })}
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )
      }

      case 'STATUS_INDICATOR': {
        const bannerType = (props.banner_type as string) || 'INFO'
        const title = (props.title as string) || component.title || 'Operational Notice'
        const message = (props.message as string) || 'Governance and monitoring active.'

        const colorMap: Record<string, string> = {
          INFO: 'bg-blue-950/40 border-blue-800 text-blue-200',
          WARNING: 'bg-amber-950/40 border-amber-800 text-amber-200',
          ERROR: 'bg-rose-950/40 border-rose-800 text-rose-200',
          SUCCESS: 'bg-emerald-950/40 border-emerald-800 text-emerald-200',
        }

        return (
          <div className={`p-4 border rounded-xl ${colorMap[bannerType] || colorMap.INFO} flex items-start gap-3`}>
            <div className="shrink-0 mt-0.5 font-bold text-sm">●</div>
            <div>
              <h5 className="text-xs font-semibold">{title}</h5>
              <p className="text-xs opacity-90 mt-0.5">{message}</p>
            </div>
          </div>
        )
      }

      case 'RECORD_DETAILS': {
        const title = (props.title as string) || component.title || 'Record Details'
        const row = data?.rows?.[0] || props.sample_data || { status: 'PENDING', amount: '$12,450.00' }

        return (
          <div className="p-4 bg-slate-900 rounded-xl space-y-3">
            <h4 className="text-sm font-semibold text-white">{title}</h4>
            <div className="grid grid-cols-2 gap-2 text-xs">
              {Object.entries(row as Record<string, unknown>).map(([k, v]) => (
                <div key={k} className="p-2 bg-slate-950/60 rounded border border-slate-800">
                  <span className="text-[10px] uppercase text-slate-500 font-mono block">{k.replace(/_/g, ' ')}</span>
                  <span className="font-semibold text-slate-200 truncate block">
                    {typeof v === 'object' && v !== null ? JSON.stringify(v) : String(v ?? '—')}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )
      }

      case 'ACTION_BUTTON': {
        const label = (props.label as string) || component.title || 'Execute Action'
        const variant = (props.variant as string) || 'primary'
        const actionType = component.interaction?.action_type || 'DISPATCH_ACTION'

        const variantClass: Record<string, string> = {
          primary: 'bg-indigo-600 hover:bg-indigo-500 text-white shadow-indigo-600/20',
          danger: 'bg-rose-600 hover:bg-rose-500 text-white shadow-rose-600/20',
          secondary: 'bg-slate-800 hover:bg-slate-700 text-slate-200',
        }

        return (
          <div className="p-3 bg-slate-900 rounded-xl flex items-center justify-between gap-3">
            <div>
              <p className="text-xs font-medium text-slate-300">{(props.description as string) || 'Governed Action'}</p>
            </div>
            <button
              type="button"
              disabled={actionInProgress}
              onClick={() => handleActionClick(actionType, component.interaction?.payload_template || {})}
              className={`px-4 py-2 text-xs font-semibold rounded-lg shadow-md transition-all ${
                variantClass[variant] || variantClass.primary
              } disabled:opacity-50`}
            >
              {actionInProgress ? 'Executing...' : label}
            </button>
          </div>
        )
      }

      case 'APPROVAL_QUEUE': {
        const title = (props.title as string) || component.title || 'Human Authorization Gate'
        const approvals = data?.rows || []
        const currentApproval = approvals[0]

        return (
          <div className="p-4 bg-slate-900 border border-amber-900/40 rounded-xl space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
                <h4 className="text-xs font-bold text-amber-200 uppercase tracking-wider">{title}</h4>
              </div>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">
                Awaiting Approval
              </span>
            </div>

            {currentApproval ? (
              <div className="space-y-3 bg-slate-950/60 p-3 rounded-lg border border-slate-800 text-xs text-slate-300">
                <div className="flex justify-between">
                  <span className="text-slate-400">Approval ID:</span>
                  <span className="font-mono text-slate-200">{String(currentApproval.id).slice(0, 8)}...</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Required Role:</span>
                  <span className="font-semibold text-slate-200">{String(currentApproval.assigned_role || 'PROJECT_LEAD')}</span>
                </div>
                <div>
                  <label className="block text-[11px] text-slate-400 mb-1">Decision Rationale</label>
                  <input
                    type="text"
                    value={rationale}
                    onChange={(e) => setRationale(e.target.value)}
                    placeholder="Enter review notes..."
                    className="w-full px-2.5 py-1.5 bg-slate-900 border border-slate-700 rounded text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                </div>
                <div className="flex gap-2 pt-1">
                  <button
                    type="button"
                    disabled={actionInProgress}
                    onClick={() =>
                      handleActionClick('APPROVE_ACTION', {
                        approval_id: currentApproval.id,
                        rationale: rationale || 'Approved in published portal.',
                      })
                    }
                    className="flex-1 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs rounded transition-colors"
                  >
                    Approve
                  </button>
                  <button
                    type="button"
                    disabled={actionInProgress}
                    onClick={() =>
                      handleActionClick('REJECT_ACTION', {
                        approval_id: currentApproval.id,
                        rationale: rationale || 'Rejected in published portal.',
                      })
                    }
                    className="flex-1 py-1.5 bg-rose-600 hover:bg-rose-500 text-white font-semibold text-xs rounded transition-colors"
                  >
                    Reject
                  </button>
                </div>
              </div>
            ) : (
              <p className="text-xs text-slate-400 italic py-2">No pending approval gates for this context.</p>
            )}
          </div>
        )
      }

      case 'AUDIT_TRAIL_VIEW': {
        const title = (props.title as string) || component.title || 'Audit History'
        const audits = data?.rows || []

        return (
          <div className="p-4 bg-slate-900 rounded-xl space-y-3">
            <h4 className="text-sm font-semibold text-white">{title}</h4>
            <div className="space-y-3 border-l-2 border-slate-800 pl-3 ml-1.5 max-h-60 overflow-y-auto">
              {audits.length === 0 ? (
                <p className="text-xs text-slate-500 italic">No audit records recorded.</p>
              ) : (
                audits.map((a, i) => (
                  <div key={i} className="text-xs space-y-0.5 relative">
                    <div className="w-2 h-2 rounded-full bg-indigo-500 absolute -left-[17px] top-1" />
                    <div className="flex justify-between text-slate-400 text-[11px]">
                      <span className="font-semibold text-slate-200">{String(a.action_type || 'EVENT')}</span>
                      <span className="font-mono">{a.timestamp ? String(a.timestamp).slice(11, 19) : ''}</span>
                    </div>
                    <p className="text-[11px] text-slate-400 font-mono">
                      {String(a.affected_entity_type || 'System')} · {String(a.outcome_status || 'SUCCESS')}
                    </p>
                  </div>
                ))
              )}
            </div>
          </div>
        )
      }

      case 'TEXT_BLOCK': {
        const title = (props.title as string) || component.title || ''
        const content = (props.content as string) || (props.text as string) || 'Instructional context.'
        return (
          <div className="p-4 bg-slate-900 rounded-xl space-y-1">
            {title && <h4 className="text-sm font-semibold text-white">{title}</h4>}
            <p className="text-xs text-slate-400 leading-relaxed">{content}</p>
          </div>
        )
      }

      default: {
        return (
          <div className="p-4 bg-slate-900 rounded-xl border border-slate-800">
            <h4 className="text-xs font-semibold text-slate-300">{component.title || component.id}</h4>
            <p className="text-xs text-slate-500 font-mono">Component: {component.component_type}</p>
          </div>
        )
      }
    }
  }

  return (
    <div className={wrapperClass} onClick={handleClick}>
      {isDesignMode && (
        <div className="absolute top-1 right-2 text-[10px] font-mono text-slate-500 bg-slate-950 px-1.5 py-0.5 rounded border border-slate-800">
          {component.component_type}
        </div>
      )}
      {renderContent()}
    </div>
  )
}
