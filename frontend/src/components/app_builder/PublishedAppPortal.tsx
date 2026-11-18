import { useCallback, useEffect, useState } from 'react'
import {
  executeRuntimeAction,
  getRuntimeDefinition,
  queryRuntimeData,
} from '../../services/appBuilder'
import type {
  AppPage,
  AppSection,
  ComponentInstance,
  LayoutType,
  PublishedApplicationRuntimeResponse,
  RuntimeActionExecuteResponse,
  RuntimeDataQueryResponse,
} from '../../types/api_generated'
import { ComponentRenderer } from './ComponentRenderer'

interface PublishedAppPortalProps {
  token: string
  orgId: string
  projectId: string
  appId: string
  onBack: () => void
}

export function PublishedAppPortal({
  token,
  orgId,
  projectId,
  appId,
  onBack,
}: PublishedAppPortalProps) {
  const [runtimeDef, setRuntimeDef] = useState<PublishedApplicationRuntimeResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activePageId, setActivePageId] = useState<string>('')
  const [componentDataMap, setComponentDataMap] = useState<Record<string, RuntimeDataQueryResponse>>({})
  const [componentLoadingMap, setComponentLoadingMap] = useState<Record<string, boolean>>({})
  const [actionNotice, setActionNotice] = useState<{
    type: 'success' | 'info' | 'error'
    text: string
  } | null>(null)

  // 1. Fetch Published Application Runtime Blueprint
  const loadRuntime = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await getRuntimeDefinition(token, orgId, projectId, appId)
      setRuntimeDef(res)
      if (res.definition.pages && res.definition.pages.length > 0) {
        setActivePageId(res.definition.pages[0].id)
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load published application runtime.')
    } finally {
      setLoading(false)
    }
  }, [token, orgId, projectId, appId])

  useEffect(() => {
    void loadRuntime()
  }, [loadRuntime])

  const activePage = runtimeDef?.definition.pages?.find((p) => p.id === activePageId)
  const userRoles = runtimeDef?.user_roles || []

  // Check role-based component visibility (DEF-012-003)
  const isComponentVisible = useCallback(
    (comp: ComponentInstance) => {
      if (!comp.visibility_roles || comp.visibility_roles.length === 0) {
        return true
      }
      return userRoles.includes('ORG_ADMIN') || comp.visibility_roles.some((r) => userRoles.includes(r))
    },
    [userRoles]
  )

  // 2. Query Runtime Data for all data-bound components on active page
  const fetchPageData = useCallback(async (page: AppPage) => {
    const boundComponents: ComponentInstance[] = []
    for (const sec of page.sections || []) {
      for (const comp of sec.components || []) {
        if (comp.data_binding && isComponentVisible(comp)) {
          boundComponents.push(comp)
        }
      }
    }

    for (const comp of boundComponents) {
      setComponentLoadingMap((prev) => ({ ...prev, [comp.id]: true }))
      try {
        const queryRes = await queryRuntimeData(token, orgId, projectId, appId, {
          page_id: page.id,
          component_id: comp.id,
          limit: comp.data_binding?.limit || 50,
          offset: comp.data_binding?.offset || 0,
        })
        setComponentDataMap((prev) => ({ ...prev, [comp.id]: queryRes }))
      } catch (err: unknown) {
        console.warn(`Failed to resolve runtime data for component ${comp.id}:`, err)
      } finally {
        setComponentLoadingMap((prev) => ({ ...prev, [comp.id]: false }))
      }
    }
  }, [token, orgId, projectId, appId])

  useEffect(() => {
    if (activePage) {
      void fetchPageData(activePage)
    }
  }, [activePage, fetchPageData])

  // 3. Dispatch Governed Actions
  const handleComponentAction = async (
    actionType: string,
    payload: Record<string, unknown>
  ) => {
    if (!activePage) return
    setActionNotice(null)
    try {
      const compId = (payload.component_id as string) || 'action_button'
      const res: RuntimeActionExecuteResponse = await executeRuntimeAction(
        token,
        orgId,
        projectId,
        appId,
        {
          page_id: activePage.id,
          component_id: compId,
          action_type: actionType as any, // eslint-disable-line @typescript-eslint/no-explicit-any
          payload,
        }
      )

      if (res.requires_approval) {
        setActionNotice({
          type: 'info',
          text: `Governed action submitted: Approval ID ${res.approval_id || ''}. Human authorization required before execution.`,
        })
      } else {
        setActionNotice({
          type: 'success',
          text: res.message || 'Action executed successfully.',
        })
      }

      // Refresh data on page
      await fetchPageData(activePage)
    } catch (e: unknown) {
      setActionNotice({
        type: 'error',
        text: e instanceof Error ? e.message : 'Action execution failed.',
      })
    }
  }

  const getLayoutGridClass = (layout?: LayoutType) => {
    switch (layout) {
      case 'SINGLE':
        return 'grid grid-cols-1 gap-4'
      case 'TWO_COLUMNS':
        return 'grid grid-cols-1 md:grid-cols-2 gap-4'
      case 'THREE_COLUMNS':
        return 'grid grid-cols-1 md:grid-cols-3 gap-4'
      case 'GRID':
        return 'grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4'
      case 'CARD':
      case 'TABS':
      default:
        return 'grid grid-cols-1 md:grid-cols-2 gap-4'
    }
  }

  if (loading) {
    return (
      <div className="p-12 text-center text-slate-400 space-y-3">
        <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto" />
        <p className="text-xs">Loading published application runtime...</p>
      </div>
    )
  }

  if (error || !runtimeDef) {
    return (
      <div className="p-8 bg-rose-950/40 border border-rose-800 rounded-2xl text-center space-y-4">
        <h3 className="text-base font-bold text-rose-200">Application Unavailable</h3>
        <p className="text-xs text-rose-300">{error || 'Published runtime definition not found.'}</p>
        <button
          type="button"
          onClick={onBack}
          className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-xs font-semibold transition-colors"
        >
          Return to Applications
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Published Application Runtime Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 p-5 bg-slate-900 border border-slate-800 rounded-2xl shadow-xl">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onBack}
            className="p-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs font-semibold transition-colors"
          >
            ← Exit App
          </button>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-bold text-white">{runtimeDef.name}</h2>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-semibold">
                Live v{runtimeDef.version}
              </span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                Published: {runtimeDef.published_at ? runtimeDef.published_at.slice(0, 10) : ''}
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">{runtimeDef.description}</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => activePage && fetchPageData(activePage)}
            className="px-3.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold rounded-lg transition-colors flex items-center gap-1.5"
          >
            <span>↻ Refresh Data</span>
          </button>
        </div>
      </div>

      {/* Action Execution Notice */}
      {actionNotice && (
        <div
          className={`p-3 rounded-xl text-xs font-medium border flex items-center justify-between ${
            actionNotice.type === 'success'
              ? 'bg-emerald-950/60 border-emerald-800 text-emerald-200'
              : actionNotice.type === 'info'
              ? 'bg-amber-950/60 border-amber-800 text-amber-200'
              : 'bg-rose-950/60 border-rose-800 text-rose-200'
          }`}
        >
          <span>{actionNotice.text}</span>
          <button
            type="button"
            onClick={() => setActionNotice(null)}
            className="text-xs opacity-70 hover:opacity-100"
          >
            ✕
          </button>
        </div>
      )}

      {/* Multi-Page Navigation Bar */}
      {(runtimeDef.definition.pages || []).length > 1 && (
        <div className="flex items-center gap-2 p-1.5 bg-slate-900 border border-slate-800 rounded-xl overflow-x-auto">
          {(runtimeDef.definition.pages || []).map((page) => (
            <button
              key={page.id}
              type="button"
              onClick={() => setActivePageId(page.id)}
              className={`px-4 py-2 rounded-lg text-xs font-semibold transition-all ${
                page.id === activePage?.id
                  ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/20'
                  : 'text-slate-400 hover:text-white hover:bg-slate-800/60'
              }`}
            >
              {page.title}
            </button>
          ))}
        </div>
      )}

      {/* Page Sections and Runtime Component Grid */}
      {activePage ? (
        <div className="space-y-6">
          {(activePage.sections || []).map((section: AppSection) => (
            <div key={section.id} className="space-y-3">
              {section.title && (
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-bold text-slate-200">{section.title}</h3>
                  {section.description && <p className="text-xs text-slate-400">{section.description}</p>}
                </div>
              )}

              <div className={getLayoutGridClass(section.layout)}>
                {(section.components || [])
                  .filter(isComponentVisible)
                  .map((comp: ComponentInstance) => (
                    <ComponentRenderer
                      key={comp.id}
                      component={comp}
                      data={componentDataMap[comp.id] || null}
                      loading={componentLoadingMap[comp.id] || false}
                      isDesignMode={false}
                      onAction={handleComponentAction}
                      userRoles={userRoles}
                    />
                  ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="p-12 text-center text-xs text-slate-500">No pages configured for this application.</div>
      )}
    </div>
  )
}
