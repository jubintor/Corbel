import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../../context/AuthContext'
import { listUseCases } from '../../services/architect'
import {
  createApplication,
  deleteApplication,
  getApplication,
  listApplications,
  listApplicationVersions,
  listCatalogue,
  publishApplication,
  updateApplication,
  validateApplication,
  type ComponentCatalogItem,
} from '../../services/appBuilder'
import type {
  ApplicationDefinition,
  ApplicationDetailResponse,
  ApplicationResponse,
  ApplicationValidationResponse,
  ApplicationVersionSummary,
  UseCaseResponse,
} from '../../types/api_generated'
import type { Project } from '../../types/auth'
import { PublishedAppPortal } from './PublishedAppPortal'
import { VisualBuilder } from './VisualBuilder'

interface AppBuilderWorkspaceProps {
  project: Project
  onBack: () => void
}

export function AppBuilderWorkspace({ project, onBack }: AppBuilderWorkspaceProps) {
  const { token, activeOrg } = useAuth()
  const [apps, setApps] = useState<ApplicationResponse[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Subview states: 'list' | 'builder' | 'portal'
  const [subView, setSubView] = useState<'list' | 'builder' | 'portal'>('list')
  const [activeAppId, setActiveAppId] = useState<string | null>(null)
  const [activeAppDetail, setActiveAppDetail] = useState<ApplicationDetailResponse | null>(null)
  const [catalogue, setCatalogue] = useState<ComponentCatalogItem[]>([])

  // Create Application Modal state
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [createMode, setCreateMode] = useState<'approved_spec' | 'blank'>('approved_spec')
  const [useCases, setUseCases] = useState<UseCaseResponse[]>([])
  const [selectedUseCaseId, setSelectedUseCaseId] = useState<string>('')
  const [appName, setAppName] = useState('')
  const [appDescription, setAppDescription] = useState('')
  const [createLoading, setCreateLoading] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)

  // Version History Modal
  const [showVersionHistoryModal, setShowVersionHistoryModal] = useState(false)
  const [versionHistory, setVersionHistory] = useState<ApplicationVersionSummary[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)

  // 1. Load Applications
  const loadApplications = useCallback(async () => {
    if (!token || !activeOrg) return
    setLoading(true)
    setError(null)
    try {
      const data = await listApplications(token, activeOrg.id, project.id)
      setApps(data)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load applications.')
    } finally {
      setLoading(false)
    }
  }, [token, activeOrg?.id, project.id])

  useEffect(() => {
    void loadApplications()
  }, [loadApplications])

  // Load Component Catalogue and Use Cases when needed
  const loadMetadata = useCallback(async () => {
    if (!token || !activeOrg) return
    try {
      const [cats, ucs] = await Promise.all([
        listCatalogue(token, activeOrg.id, project.id),
        listUseCases(token, activeOrg.id, project.id),
      ])
      setCatalogue(cats)
      setUseCases(ucs.filter((u) => u.status === 'APPROVED' || u.status === 'IMPLEMENTING'))
      if (ucs.length > 0) {
        setSelectedUseCaseId(ucs[0].id)
      }
    } catch (e: unknown) {
      console.warn('Metadata load error:', e)
    }
  }, [token, activeOrg?.id, project.id])

  useEffect(() => {
    void loadMetadata()
  }, [loadMetadata])

  // 2. Open Builder
  const handleOpenBuilder = async (appId: string) => {
    if (!token || !activeOrg) return
    setLoading(true)
    try {
      const detail = await getApplication(token, activeOrg.id, project.id, appId)
      setActiveAppDetail(detail)
      setActiveAppId(appId)
      setSubView('builder')
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to open application blueprint.')
    } finally {
      setLoading(false)
    }
  }

  // 3. Open Live Portal
  const handleOpenPortal = (appId: string) => {
    setActiveAppId(appId)
    setSubView('portal')
  }

  // 4. Create Application
  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!token || !activeOrg) return
    setCreateLoading(true)
    setCreateError(null)

    try {
      let created: ApplicationDetailResponse
      if (createMode === 'approved_spec') {
        const uc = useCases.find((u) => u.id === selectedUseCaseId)
        created = await createApplication(token, activeOrg.id, project.id, {
          name: appName.trim() || (uc ? `${uc.title} Application` : 'Generated App'),
          description: appDescription.trim() || (uc?.description ?? 'Domain operational application.'),
          source_use_case_id: selectedUseCaseId || undefined,
        })
      } else {
        created = await createApplication(token, activeOrg.id, project.id, {
          name: appName.trim(),
          description: appDescription.trim(),
        })
      }

      setShowCreateModal(false)
      setAppName('')
      setAppDescription('')
      await loadApplications()
      await handleOpenBuilder(created.id)
    } catch (e: unknown) {
      setCreateError(e instanceof Error ? e.message : 'Failed to create application.')
    } finally {
      setCreateLoading(false)
    }
  }

  // 5. Delete Application
  const handleDeleteApp = async (appId: string, name: string) => {
    if (!token || !activeOrg) return
    if (!window.confirm(`Are you sure you want to delete application "${name}"? This action cannot be undone.`)) {
      return
    }

    try {
      await deleteApplication(token, activeOrg.id, project.id, appId)
      await loadApplications()
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : 'Failed to delete application.')
    }
  }

  // 6. View Version History
  const handleViewVersions = async (appId: string) => {
    if (!token || !activeOrg) return
    setHistoryLoading(true)
    setShowVersionHistoryModal(true)
    try {
      const vers = await listApplicationVersions(token, activeOrg.id, project.id, appId)
      setVersionHistory(vers)
    } catch (e: unknown) {
      console.warn('Failed to load version history:', e)
    } finally {
      setHistoryLoading(false)
    }
  }

  // 7. Builder Callbacks
  const handleSaveDraft = async (definition: ApplicationDefinition) => {
    if (!token || !activeOrg || !activeAppId) return
    const updated = await updateApplication(token, activeOrg.id, project.id, activeAppId, {
      draft_definition: definition,
    })
    setActiveAppDetail(updated)
    await loadApplications()
  }

  const handleValidateDraft = async (
    definition: ApplicationDefinition
  ): Promise<ApplicationValidationResponse> => {
    if (!token || !activeOrg || !activeAppId) {
      throw new Error('No active application.')
    }
    return validateApplication(token, activeOrg.id, project.id, activeAppId, definition)
  }

  const handlePublishDraft = async (changelog: string) => {
    if (!token || !activeOrg || !activeAppId) return
    const published = await publishApplication(token, activeOrg.id, project.id, activeAppId, {
      changelog,
    })
    setActiveAppDetail(published)
    await loadApplications()
  }

  // --- Subview Renderers ---

  if (subView === 'portal' && activeAppId && token && activeOrg) {
    return (
      <PublishedAppPortal
        token={token}
        orgId={activeOrg.id}
        projectId={project.id}
        appId={activeAppId}
        onBack={() => setSubView('list')}
      />
    )
  }

  if (subView === 'builder' && activeAppDetail) {
    return (
      <VisualBuilder
        app={activeAppDetail}
        catalogue={catalogue}
        onSaveDraft={handleSaveDraft}
        onValidate={handleValidateDraft}
        onPublish={handlePublishDraft}
        onBack={() => setSubView('list')}
      />
    )
  }

  // Default: Application Roster View
  return (
    <div className="space-y-6">
      {/* Workspace Subheader */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onBack}
              className="p-1 bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white rounded text-xs transition-colors"
            >
              ←
            </button>
            <h3 className="text-base font-bold text-white">Application Builder & Runtime Portal</h3>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
              Project: {project.slug}
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Build the platform once. Create, configure, validate, publish, and operate domain-specific applications
            through declarative blueprints.
          </p>
        </div>

        <button
          type="button"
          data-testid="create-app-button"
          onClick={() => setShowCreateModal(true)}
          className="inline-flex items-center gap-2 px-3.5 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold rounded-lg transition-colors shadow-lg shadow-indigo-600/20 shrink-0"
        >
          <span>+ Create Application</span>
        </button>
      </div>

      {error && (
        <div className="p-3 bg-rose-950/60 border border-rose-800 text-rose-200 rounded-xl text-xs">
          {error}
        </div>
      )}

      {/* Applications Grid */}
      {loading ? (
        <div className="p-12 text-center text-slate-400 space-y-2">
          <div className="w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto" />
          <p className="text-xs">Loading project applications...</p>
        </div>
      ) : apps.length === 0 ? (
        <div className="p-12 border border-dashed border-slate-800 rounded-2xl text-center space-y-3">
          <h4 className="text-sm font-semibold text-slate-300">No Applications Built Yet</h4>
          <p className="text-xs text-slate-500 max-w-md mx-auto">
            Transform an approved Phase 11 Use-Case Specification into an operational application or start with a blank
            template.
          </p>
          <button
            type="button"
            onClick={() => setShowCreateModal(true)}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold rounded-lg transition-colors shadow-md"
          >
            Create First Application
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {apps.map((app) => (
            <div
              key={app.id}
              className="bg-slate-900 border border-slate-800 hover:border-slate-700 rounded-2xl p-5 shadow-lg flex flex-col justify-between transition-all space-y-4"
            >
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span
                    className={`text-[10px] font-bold px-2 py-0.5 rounded uppercase tracking-wider ${
                      app.status === 'PUBLISHED'
                        ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                        : app.status === 'VALIDATED'
                        ? 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20'
                        : 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                    }`}
                  >
                    {app.status}
                  </span>
                  <span className="text-[10px] font-mono text-slate-400">
                    Draft v{app.current_version}
                    {app.published_version ? ` · Live v${app.published_version}` : ''}
                  </span>
                </div>

                <h4 className="text-sm font-bold text-white">{app.name}</h4>
                <p className="text-xs text-slate-400 line-clamp-2">{app.description}</p>
              </div>

              <div className="pt-3 border-t border-slate-800 space-y-2">
                <div className="flex items-center justify-between text-[11px] text-slate-500 font-mono">
                  <span>Updated: {app.updated_at.slice(0, 10)}</span>
                  <button
                    type="button"
                    onClick={() => handleViewVersions(app.id)}
                    className="hover:text-indigo-400 transition-colors"
                  >
                    History ({app.current_version})
                  </button>
                </div>

                <div className="flex items-center gap-2 pt-1">
                  {app.status === 'PUBLISHED' && (
                    <button
                      type="button"
                      data-testid={`launch-app-${app.id}`}
                      onClick={() => handleOpenPortal(app.id)}
                      className="flex-1 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs rounded-lg transition-colors shadow-md shadow-emerald-600/20 text-center"
                    >
                      ▶ Launch App
                    </button>
                  )}
                  <button
                    type="button"
                    data-testid={`edit-app-${app.id}`}
                    onClick={() => handleOpenBuilder(app.id)}
                    className="flex-1 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold text-xs rounded-lg transition-colors text-center"
                  >
                    Edit Blueprint
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDeleteApp(app.id, app.name)}
                    className="p-1.5 bg-slate-800 hover:bg-rose-950/80 text-slate-400 hover:text-rose-400 rounded-lg text-xs transition-colors"
                    title="Delete Application"
                  >
                    🗑
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create Application Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 max-w-lg w-full shadow-2xl space-y-4">
            <h3 className="text-base font-bold text-white">Create New Application</h3>
            <p className="text-xs text-slate-400">
              Build a custom operational application for your enterprise operators.
            </p>

            {createError && (
              <div className="p-3 bg-rose-950/60 border border-rose-800 text-rose-200 rounded-lg text-xs">
                {createError}
              </div>
            )}

            <div className="flex gap-2 p-1 bg-slate-950 rounded-lg border border-slate-800">
              <button
                type="button"
                onClick={() => setCreateMode('approved_spec')}
                className={`flex-1 py-1.5 rounded text-xs font-semibold transition-colors ${
                  createMode === 'approved_spec'
                    ? 'bg-indigo-600 text-white'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                From Approved Use-Case
              </button>
              <button
                type="button"
                onClick={() => setCreateMode('blank')}
                className={`flex-1 py-1.5 rounded text-xs font-semibold transition-colors ${
                  createMode === 'blank'
                    ? 'bg-indigo-600 text-white'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                Blank Template
              </button>
            </div>

            <form onSubmit={handleCreateSubmit} className="space-y-4">
              {createMode === 'approved_spec' && (
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">
                    Select Approved Use-Case Specification
                  </label>
                  {useCases.length === 0 ? (
                    <p className="text-xs text-amber-400 italic bg-amber-950/40 p-2.5 rounded border border-amber-800">
                      No approved Use-Case Specifications found in this project. You can build from a blank template or
                      approve a specification in the Use-Case Architect.
                    </p>
                  ) : (
                    <select
                      value={selectedUseCaseId}
                      onChange={(e) => setSelectedUseCaseId(e.target.value)}
                      className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-xs text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    >
                      {useCases.map((uc) => (
                        <option key={uc.id} value={uc.id}>
                          {uc.title} (v{uc.current_version}) — {uc.status}
                        </option>
                      ))}
                    </select>
                  )}
                </div>
              )}

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Application Name {createMode === 'approved_spec' ? '(Optional override)' : ''}
                </label>
                <input
                  type="text"
                  required={createMode === 'blank'}
                  value={appName}
                  onChange={(e) => setAppName(e.target.value)}
                  placeholder={createMode === 'approved_spec' ? 'Auto-derived from specification' : 'Procure-to-Pay Portal'}
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Description {createMode === 'approved_spec' ? '(Optional override)' : ''}
                </label>
                <textarea
                  rows={2}
                  value={appDescription}
                  onChange={(e) => setAppDescription(e.target.value)}
                  placeholder="Operational dashboard and exception management interface."
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 font-semibold text-xs rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createLoading || (createMode === 'approved_spec' && useCases.length === 0)}
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-semibold text-xs rounded-lg transition-colors shadow-lg shadow-indigo-600/20"
                >
                  {createLoading ? 'Generating...' : 'Create & Open Builder'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Version History Modal */}
      {showVersionHistoryModal && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 max-w-md w-full shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-slate-800">
              <h3 className="text-base font-bold text-white">Application Version History</h3>
              <button
                type="button"
                onClick={() => setShowVersionHistoryModal(false)}
                className="text-slate-400 hover:text-white text-xs"
              >
                ✕
              </button>
            </div>

            {historyLoading ? (
              <div className="p-6 text-center text-xs text-slate-400">Loading versions...</div>
            ) : versionHistory.length === 0 ? (
              <p className="text-xs text-slate-500 italic">No published versions yet.</p>
            ) : (
              <div className="space-y-3 max-h-72 overflow-y-auto pr-1">
                {versionHistory.map((ver) => (
                  <div key={ver.version} className="p-3 bg-slate-950/70 border border-slate-800 rounded-xl space-y-1">
                    <div className="flex justify-between text-xs">
                      <span className="font-bold text-emerald-400 font-mono">v{ver.version}</span>
                      <span className="text-[11px] text-slate-400">{ver.created_at.slice(0, 16)}</span>
                    </div>
                    {ver.changelog && <p className="text-xs text-slate-300">{ver.changelog}</p>}
                    <p className="text-[10px] text-slate-500 font-mono">Publisher: {ver.created_by}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
