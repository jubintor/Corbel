import { useState } from 'react'
import type { ComponentCatalogItem } from '../../services/appBuilder'
import type {
  ApplicationDefinition,
  ApplicationDetailResponse,
  ApplicationValidationResponse,
  AppPage,
  AppSection,
  ComponentInstance,
  DataSourceType,
  InteractionActionType,
  LayoutType,
} from '../../types/api_generated'
import { ComponentRenderer } from './ComponentRenderer'

interface VisualBuilderProps {
  app: ApplicationDetailResponse
  catalogue: ComponentCatalogItem[]
  onSaveDraft: (definition: ApplicationDefinition) => Promise<void>
  onValidate: (definition: ApplicationDefinition) => Promise<ApplicationValidationResponse>
  onPublish: (changelog: string) => Promise<void>
  onBack: () => void
  userRole?: string
}

export function VisualBuilder({
  app,
  catalogue,
  onSaveDraft,
  onValidate,
  onPublish,
  onBack,
  userRole = 'PROJECT_LEAD',
}: VisualBuilderProps) {
  const [definition, setDefinition] = useState<ApplicationDefinition>(
    JSON.parse(JSON.stringify(app.draft_definition)) as ApplicationDefinition
  )
  const [activePageId, setActivePageId] = useState<string>(
    definition.pages && definition.pages.length > 0 ? definition.pages[0].id : ''
  )
  const [selectedComponentId, setSelectedComponentId] = useState<string | null>(null)
  const [isPreviewMode, setIsPreviewMode] = useState(false)
  const [saving, setSaving] = useState(false)
  const [validating, setValidating] = useState(false)
  const [publishing, setPublishing] = useState(false)
  const [validationResult, setValidationResult] = useState<ApplicationValidationResponse | null>(null)
  const [showPublishModal, setShowPublishModal] = useState(false)
  const [changelog, setChangelog] = useState('')
  const [statusMsg, setStatusMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const activePage = definition.pages?.find((p) => p.id === activePageId) || definition.pages?.[0]

  // Find selected component
  let selectedComponent: ComponentInstance | null = null
  let selectedComponentSectionId: string | null = null
  if (selectedComponentId && activePage) {
    for (const sec of activePage.sections || []) {
      for (const comp of sec.components || []) {
        if (comp.id === selectedComponentId) {
          selectedComponent = comp
          selectedComponentSectionId = sec.id
          break
        }
      }
    }
  }

  // --- Actions ---

  const handleSave = async () => {
    setSaving(true)
    setStatusMsg(null)
    try {
      await onSaveDraft(definition)
      setStatusMsg({ type: 'success', text: 'Application draft saved successfully.' })
    } catch (e: unknown) {
      setStatusMsg({ type: 'error', text: e instanceof Error ? e.message : 'Failed to save draft.' })
    } finally {
      setSaving(false)
    }
  }

  const handleValidate = async () => {
    setValidating(true)
    setStatusMsg(null)
    try {
      const res = await onValidate(definition)
      setValidationResult(res)
      if (res.is_valid) {
        setStatusMsg({ type: 'success', text: 'Application blueprint passed validation!' })
      } else {
        const errCount = res.errors ? res.errors.length : 0
        setStatusMsg({ type: 'error', text: `Blueprint has ${errCount} validation errors.` })
      }
    } catch (e: unknown) {
      setStatusMsg({ type: 'error', text: e instanceof Error ? e.message : 'Validation request failed.' })
    } finally {
      setValidating(false)
    }
  }

  const handlePublishSubmit = async () => {
    setPublishing(true)
    setStatusMsg(null)
    try {
      await onPublish(changelog || 'Published updated blueprint.')
      setShowPublishModal(false)
      setStatusMsg({ type: 'success', text: 'Application version published successfully!' })
    } catch (e: unknown) {
      setStatusMsg({ type: 'error', text: e instanceof Error ? e.message : 'Failed to publish application.' })
    } finally {
      setPublishing(false)
    }
  }

  const handleAddPage = () => {
    const pageNum = (definition.pages?.length || 0) + 1
    const newPageId = `page_${pageNum}`
    const newPage: AppPage = {
      id: newPageId,
      title: `Page ${pageNum}`,
      sections: [
        {
          id: `sec_${newPageId}_1`,
          title: 'Main Section',
          layout: 'TWO_COLUMNS',
          components: [],
        },
      ],
    }
    const updated = {
      ...definition,
      pages: [...(definition.pages || []), newPage],
    }
    setDefinition(updated)
    setActivePageId(newPageId)
  }

  const handleAddComponent = (sectionId: string, item: ComponentCatalogItem) => {
    const compId = `${item.component_type.toLowerCase()}_${Date.now().toString().slice(-4)}`
    const newComp: ComponentInstance = {
      id: compId,
      component_type: item.component_type,
      title: item.display_name,
      properties: { ...item.default_properties, title: item.display_name },
      data_binding: item.supported_data_sources.length > 0 ? {
        source_type: item.supported_data_sources[0] as DataSourceType,
        limit: 50,
      } : undefined,
    }

    const updatedPages = (definition.pages || []).map((p) => {
      if (p.id !== activePage?.id) return p
      const updatedSecs = (p.sections || []).map((s) => {
        if (s.id !== sectionId) return s
        return {
          ...s,
          components: [...(s.components || []), newComp],
        }
      })
      return { ...p, sections: updatedSecs }
    })

    setDefinition({ ...definition, pages: updatedPages })
    setSelectedComponentId(compId)
  }

  const handleDeleteComponent = (sectionId: string, compId: string) => {
    const updatedPages = (definition.pages || []).map((p) => {
      if (p.id !== activePage?.id) return p
      const updatedSecs = (p.sections || []).map((s) => {
        if (s.id !== sectionId) return s
        return {
          ...s,
          components: (s.components || []).filter((c) => c.id !== compId),
        }
      })
      return { ...p, sections: updatedSecs }
    })
    setDefinition({ ...definition, pages: updatedPages })
    if (selectedComponentId === compId) {
      setSelectedComponentId(null)
    }
  }

  const handleUpdateComponentProperty = (key: string, val: unknown) => {
    if (!selectedComponent || !selectedComponentSectionId) return

    const updatedPages = (definition.pages || []).map((p) => {
      if (p.id !== activePage?.id) return p
      const updatedSecs = (p.sections || []).map((s) => {
        if (s.id !== selectedComponentSectionId) return s
        const updatedComps = (s.components || []).map((c) => {
          if (c.id !== selectedComponent?.id) return c
          return {
            ...c,
            properties: { ...c.properties, [key]: val },
          }
        })
        return { ...s, components: updatedComps }
      })
      return { ...p, sections: updatedSecs }
    })

    setDefinition({ ...definition, pages: updatedPages })
  }

  const handleUpdateComponentBinding = (sourceType: DataSourceType, entityName?: string) => {
    if (!selectedComponent || !selectedComponentSectionId) return

    const updatedPages = (definition.pages || []).map((p) => {
      if (p.id !== activePage?.id) return p
      const updatedSecs = (p.sections || []).map((s) => {
        if (s.id !== selectedComponentSectionId) return s
        const updatedComps = (s.components || []).map((c) => {
          if (c.id !== selectedComponent?.id) return c
          return {
            ...c,
            data_binding: {
              ...c.data_binding,
              source_type: sourceType,
              entity_name: entityName || c.data_binding?.entity_name,
            },
          }
        })
        return { ...s, components: updatedComps }
      })
      return { ...p, sections: updatedSecs }
    })

    setDefinition({ ...definition, pages: updatedPages })
  }

  const handleUpdateComponentInteraction = (actionType: InteractionActionType) => {
    if (!selectedComponent || !selectedComponentSectionId) return

    const updatedPages = (definition.pages || []).map((p) => {
      if (p.id !== activePage?.id) return p
      const updatedSecs = (p.sections || []).map((s) => {
        if (s.id !== selectedComponentSectionId) return s
        const updatedComps = (s.components || []).map((c) => {
          if (c.id !== selectedComponent?.id) return c
          return {
            ...c,
            interaction: {
              action_type: actionType,
            },
          }
        })
        return { ...s, components: updatedComps }
      })
      return { ...p, sections: updatedSecs }
    })

    setDefinition({ ...definition, pages: updatedPages })
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

  const isAnalyst = userRole === 'ANALYST'

  return (
    <div className="space-y-4">
      {/* Top Navigation & Action Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-4 bg-slate-900 border border-slate-800 rounded-xl">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onBack}
            className="p-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs font-semibold transition-colors flex items-center gap-1"
          >
            ← Back
          </button>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-base font-bold text-white">{app.name}</h3>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                Draft v{app.current_version}
              </span>
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                Status: {app.status}
              </span>
            </div>
            <p className="text-xs text-slate-400">{app.description}</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setIsPreviewMode(!isPreviewMode)}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors flex items-center gap-1.5 ${
              isPreviewMode ? 'bg-indigo-600 text-white' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
            }`}
          >
            <span>{isPreviewMode ? 'Exit Preview' : 'Preview Live'}</span>
          </button>

          <button
            type="button"
            disabled={validating}
            onClick={handleValidate}
            className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold rounded-lg transition-colors"
          >
            {validating ? 'Validating...' : 'Validate Blueprint'}
          </button>

          <button
            type="button"
            disabled={saving}
            onClick={handleSave}
            className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold rounded-lg transition-colors"
          >
            {saving ? 'Saving...' : 'Save Draft'}
          </button>

          <button
            type="button"
            disabled={publishing || isAnalyst}
            title={isAnalyst ? 'Project Lead or Org Admin required to publish' : undefined}
            onClick={() => setShowPublishModal(true)}
            className="px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white text-xs font-semibold rounded-lg transition-colors shadow-lg shadow-emerald-600/20"
          >
            Publish Version
          </button>
        </div>
      </div>

      {/* Status banner */}
      {statusMsg && (
        <div
          className={`p-3 rounded-lg text-xs font-medium border ${
            statusMsg.type === 'success'
              ? 'bg-emerald-950/60 border-emerald-800 text-emerald-200'
              : 'bg-rose-950/60 border-rose-800 text-rose-200'
          }`}
        >
          {statusMsg.text}
        </div>
      )}

      {/* Validation alert drawer if errors exist */}
      {validationResult && !validationResult.is_valid && validationResult.errors && (
        <div className="p-4 bg-rose-950/40 border border-rose-800 rounded-xl space-y-2">
          <h4 className="text-xs font-bold text-rose-200 uppercase tracking-wider">
            Blueprint Validation Issues ({validationResult.errors.length})
          </h4>
          <ul className="text-xs text-rose-300 list-disc list-inside space-y-1 font-mono">
            {validationResult.errors.map((err, i) => (
              <li key={i}>{err.message}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Visual Builder Workspace Body */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Left Panel: Component Catalogue (Hidden in Preview Mode) */}
        {!isPreviewMode && (
          <div className="lg:col-span-3 bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-slate-800">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300">Component Catalogue</h4>
              <span className="text-[10px] font-mono text-slate-500">{catalogue.length} items</span>
            </div>

            <div className="space-y-3 max-h-[600px] overflow-y-auto pr-1">
              {catalogue.map((item) => (
                <div
                  key={item.component_type}
                  className="p-3 bg-slate-950/70 border border-slate-800 rounded-lg space-y-2 hover:border-slate-700 transition-colors"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-slate-200">{item.display_name}</span>
                    <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-400">
                      {item.category}
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400">{item.description}</p>
                  <button
                    type="button"
                    onClick={() => {
                      if (activePage?.sections && activePage.sections.length > 0) {
                        handleAddComponent(activePage.sections[0].id, item)
                      }
                    }}
                    className="w-full py-1 bg-indigo-600/20 hover:bg-indigo-600/40 text-indigo-300 border border-indigo-500/30 rounded text-[11px] font-semibold transition-colors"
                  >
                    + Add to Page
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Center Panel: Interactive Canvas */}
        <div
          className={`${
            isPreviewMode ? 'lg:col-span-12' : selectedComponent ? 'lg:col-span-6' : 'lg:col-span-9'
          } bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-4`}
        >
          {/* Page Selector & Management */}
          <div className="flex items-center justify-between pb-3 border-b border-slate-800">
            <div className="flex items-center gap-1.5 overflow-x-auto">
              {(definition.pages || []).map((page) => (
                <button
                  key={page.id}
                  type="button"
                  onClick={() => {
                    setActivePageId(page.id)
                    setSelectedComponentId(null)
                  }}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                    page.id === activePage?.id
                      ? 'bg-indigo-600 text-white'
                      : 'bg-slate-800 text-slate-400 hover:text-white'
                  }`}
                >
                  {page.title}
                </button>
              ))}
              {!isPreviewMode && (
                <button
                  type="button"
                  onClick={handleAddPage}
                  className="px-2.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white rounded-lg text-xs font-semibold transition-colors"
                >
                  + Page
                </button>
              )}
            </div>

            <div className="text-xs text-slate-400 font-mono">
              Layout: {activePage?.sections?.[0]?.layout || 'TWO_COLUMNS'}
            </div>
          </div>

          {/* Active Page Sections & Renderers */}
          {activePage ? (
            <div className="space-y-6">
              {(activePage.sections || []).map((section: AppSection) => (
                <div key={section.id} className="space-y-3">
                  {!isPreviewMode && (
                    <div className="flex items-center justify-between text-xs text-slate-400">
                      <span className="font-semibold text-slate-300">{section.title || section.id}</span>
                      <span className="font-mono text-[10px] text-slate-500">Layout: {section.layout}</span>
                    </div>
                  )}

                  <div className={getLayoutGridClass(section.layout)}>
                    {(section.components || []).length === 0 ? (
                      <div className="col-span-full p-8 border border-dashed border-slate-800 rounded-xl text-center text-xs text-slate-500">
                        Section is empty. Select a component from the left catalogue to add.
                      </div>
                    ) : (
                      (section.components || []).map((comp: ComponentInstance) => (
                        <div key={comp.id} className="relative group">
                          <ComponentRenderer
                            component={comp}
                            isDesignMode={!isPreviewMode}
                            isSelected={selectedComponentId === comp.id}
                            onSelectComponent={(id) => setSelectedComponentId(id)}
                          />
                          {!isPreviewMode && (
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation()
                                handleDeleteComponent(section.id, comp.id)
                              }}
                              className="absolute top-2 right-2 p-1 bg-rose-950/80 hover:bg-rose-900 border border-rose-800 text-rose-300 rounded text-[10px] opacity-0 group-hover:opacity-100 transition-opacity"
                              title="Delete component"
                            >
                              ✕
                            </button>
                          )}
                        </div>
                      ))
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="p-8 text-center text-xs text-slate-500">No pages found in this application draft.</div>
          )}
        </div>

        {/* Right Panel: Property Inspector (Hidden in Preview Mode or when none selected) */}
        {!isPreviewMode && selectedComponent && (
          <div className="lg:col-span-3 bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-slate-800">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300">Property Inspector</h4>
              <button
                type="button"
                onClick={() => setSelectedComponentId(null)}
                className="text-slate-500 hover:text-slate-300 text-xs"
              >
                ✕
              </button>
            </div>

            <div className="space-y-4 max-h-[600px] overflow-y-auto pr-1 text-xs">
              <div>
                <label className="block text-[11px] font-medium text-slate-400 mb-1">Component ID</label>
                <input
                  type="text"
                  disabled
                  value={selectedComponent.id}
                  className="w-full px-2.5 py-1.5 bg-slate-950 border border-slate-800 rounded font-mono text-[11px] text-slate-400"
                />
              </div>

              <div>
                <label className="block text-[11px] font-medium text-slate-400 mb-1">Title / Label</label>
                <input
                  type="text"
                  value={String(selectedComponent.properties?.title || selectedComponent.properties?.label || selectedComponent.title || '')}
                  onChange={(e) => handleUpdateComponentProperty('title', e.target.value)}
                  className="w-full px-2.5 py-1.5 bg-slate-950 border border-slate-700 rounded text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>

              {/* Data Binding Controls */}
              <div className="pt-2 border-t border-slate-800 space-y-3">
                <h5 className="text-[11px] font-bold text-slate-300 uppercase tracking-wider">Data Source Binding</h5>
                <div>
                  <label className="block text-[11px] font-medium text-slate-400 mb-1">Source Type</label>
                  <select
                    value={selectedComponent.data_binding?.source_type || 'STATIC'}
                    onChange={(e) => handleUpdateComponentBinding(e.target.value as DataSourceType)}
                    className="w-full px-2.5 py-1.5 bg-slate-950 border border-slate-700 rounded text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  >
                    <option value="ONTOLOGY_OBJECT">Ontology Business Object</option>
                    <option value="MONITOR_FINDING">Monitor Findings</option>
                    <option value="APPROVAL">Governance Approvals</option>
                    <option value="AUDIT_TRAIL">Audit Trail</option>
                    <option value="STATIC">Static Mock</option>
                  </select>
                </div>

                {selectedComponent.data_binding?.source_type === 'ONTOLOGY_OBJECT' && (
                  <div>
                    <label className="block text-[11px] font-medium text-slate-400 mb-1">Target Entity Name</label>
                    <input
                      type="text"
                      value={selectedComponent.data_binding?.entity_name || 'PurchaseOrder'}
                      onChange={(e) =>
                        handleUpdateComponentBinding('ONTOLOGY_OBJECT', e.target.value)
                      }
                      placeholder="PurchaseOrder"
                      className="w-full px-2.5 py-1.5 bg-slate-950 border border-slate-700 rounded text-slate-200 font-mono focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    />
                  </div>
                )}
              </div>

              {/* Interaction Controls */}
              <div className="pt-2 border-t border-slate-800 space-y-3">
                <h5 className="text-[11px] font-bold text-slate-300 uppercase tracking-wider">Interaction Action</h5>
                <div>
                  <label className="block text-[11px] font-medium text-slate-400 mb-1">Action Type</label>
                  <select
                    value={selectedComponent.interaction?.action_type || 'REFRESH_DATA'}
                    onChange={(e) =>
                      handleUpdateComponentInteraction(e.target.value as InteractionActionType)
                    }
                    className="w-full px-2.5 py-1.5 bg-slate-950 border border-slate-700 rounded text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  >
                    <option value="REFRESH_DATA">Refresh Data</option>
                    <option value="DISPATCH_ACTION">Dispatch Governed Action</option>
                    <option value="TRIGGER_APPROVAL">Trigger Human Approval Gate</option>
                    <option value="APPROVE_ACTION">Approve Governed Action</option>
                    <option value="REJECT_ACTION">Reject Governed Action</option>
                    <option value="NAVIGATE_PAGE">Navigate Page</option>
                  </select>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Publish Version Modal */}
      {showPublishModal && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 max-w-md w-full shadow-2xl space-y-4">
            <h3 className="text-base font-bold text-white">Publish Application Version</h3>
            <p className="text-xs text-slate-400">
              Publishing snapshots the current draft into an immutable, versioned runtime blueprint. Published
              applications become immediately available to authorized operators.
            </p>

            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1">Version Changelog</label>
              <textarea
                rows={3}
                value={changelog}
                onChange={(e) => setChangelog(e.target.value)}
                placeholder="e.g. Added exception triage table and invoice hold approval gate."
                className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setShowPublishModal(false)}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 font-semibold text-xs rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={publishing}
                onClick={handlePublishSubmit}
                className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-semibold text-xs rounded-lg transition-colors shadow-lg shadow-emerald-600/20"
              >
                {publishing ? 'Publishing...' : 'Confirm & Publish'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
