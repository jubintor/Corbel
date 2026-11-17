import { useState, useEffect, useCallback, type FormEvent } from 'react'
import { useAuth } from '../context/AuthContext'
import { listProjects, createProject, deleteProject } from '../services/projects'
import type { Project } from '../types/auth'
import { AuthApiError } from '../services/auth'
import { DatasetWorkspace } from './DatasetWorkspace'
import { OntologyWorkspace } from './OntologyWorkspace'
import { QueryWorkspace } from './QueryWorkspace'
import { ProcessWorkspace } from './ProcessWorkspace'
import { MonitorsWorkspace } from './MonitorsWorkspace'
import { InvestigationsWorkspace } from './InvestigationsWorkspace'

export function ProjectWorkspace() {
  const { user, token, activeOrg } = useAuth()
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [activeProject, setActiveProject] = useState<Project | null>(null)
  const [projectSubView, setProjectSubView] = useState<'datasets' | 'ontology' | 'query' | 'process' | 'monitors' | 'investigations'>('datasets')

  // Create Project state
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [projName, setProjName] = useState('')
  const [projSlug, setProjSlug] = useState('')
  const [projDesc, setProjDesc] = useState('')
  const [createLoading, setCreateLoading] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)

  const loadTenantProjects = useCallback(async () => {
    if (!token || !activeOrg) {
      setProjects([])
      return
    }
    setLoading(true)
    setError(null)
    try {
      const data = await listProjects(token, activeOrg.id)
      setProjects(data)
    } catch (err: unknown) {
      if (err instanceof AuthApiError) {
        setError(err.message)
      } else {
        setError('Failed to load projects for active tenant')
      }
    } finally {
      setLoading(false)
    }
  }, [token, activeOrg?.id])

  useEffect(() => {
    loadTenantProjects()
  }, [loadTenantProjects])

  const handleCreateProject = async (e: FormEvent) => {
    e.preventDefault()
    if (!token || !activeOrg) return
    setCreateError(null)
    setCreateLoading(true)

    try {
      await createProject(token, activeOrg.id, {
        name: projName.trim(),
        slug: projSlug.trim().toLowerCase(),
        description: projDesc.trim() || undefined,
      })
      setProjName('')
      setProjSlug('')
      setProjDesc('')
      setShowCreateModal(false)
      await loadTenantProjects()
    } catch (err: unknown) {
      if (err instanceof AuthApiError) {
        setCreateError(err.message)
      } else {
        setCreateError('Failed to create project')
      }
    } finally {
      setCreateLoading(false)
    }
  }

  const handleDeleteProject = async (projectId: string, projectName: string) => {
    if (!token || !activeOrg) return
    if (!window.confirm(`Are you sure you want to delete project "${projectName}"? This action cannot be undone.`)) {
      return
    }

    try {
      await deleteProject(token, activeOrg.id, projectId)
      await loadTenantProjects()
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Failed to delete project')
    }
  }

  if (!user) {
    return null
  }

  if (!activeOrg) {
    return (
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-8 text-center text-slate-300">
        <div className="w-12 h-12 mx-auto rounded-full bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400 mb-3">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
          </svg>
        </div>
        <h3 className="text-lg font-bold text-white mb-1">No Active Organization</h3>
        <p className="text-xs text-slate-400 max-w-md mx-auto mb-4">
          To manage projects and inspect operational processes, create or select an organization from the selector above.
        </p>
      </div>
    )
  }

  if (activeProject) {
    return (
      <div className="space-y-4">
        {/* Project View Tabs */}
        <div className="flex items-center gap-2 bg-slate-900 border border-slate-800 rounded-xl p-1.5 shadow-md">
          <button
            type="button"
            data-testid="tab-datasets"
            onClick={() => setProjectSubView('datasets')}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-colors flex items-center gap-2 ${
              projectSubView === 'datasets'
                ? 'bg-indigo-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-white hover:bg-slate-800/60'
            }`}
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2 1 3 3 3h10c2 0 3-1 3-3V7c0-2-1-3-3-3H7C5 4 4 5 4 7z" />
            </svg>
            <span>Datasets & Profiling</span>
          </button>
          <button
            type="button"
            data-testid="tab-ontology"
            onClick={() => setProjectSubView('ontology')}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-colors flex items-center gap-2 ${
              projectSubView === 'ontology'
                ? 'bg-indigo-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-white hover:bg-slate-800/60'
            }`}
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
            </svg>
            <span>Ontology & Semantic Discovery</span>
          </button>
          <button
            type="button"
            data-testid="tab-query"
            onClick={() => setProjectSubView('query')}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-colors flex items-center gap-2 ${
              projectSubView === 'query'
                ? 'bg-indigo-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-white hover:bg-slate-800/60'
            }`}
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <span>Structured Querying & AI</span>
          </button>
          <button
            type="button"
            data-testid="tab-process"
            onClick={() => setProjectSubView('process')}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-colors flex items-center gap-2 ${
              projectSubView === 'process'
                ? 'bg-indigo-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-white hover:bg-slate-800/60'
            }`}
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
            <span>Process Intelligence</span>
          </button>
          <button
            type="button"
            data-testid="tab-monitors"
            onClick={() => setProjectSubView('monitors')}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-colors flex items-center gap-2 ${
              projectSubView === 'monitors'
                ? 'bg-indigo-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-white hover:bg-slate-800/60'
            }`}
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <span>Monitors & Exceptions</span>
          </button>
          <button
            type="button"
            data-testid="tab-investigations"
            onClick={() => setProjectSubView('investigations')}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-colors flex items-center gap-2 ${
              projectSubView === 'investigations'
                ? 'bg-indigo-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-white hover:bg-slate-800/60'
            }`}
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
            <span>Investigations & Approvals</span>
          </button>
        </div>

        {projectSubView === 'datasets' ? (
          <DatasetWorkspace project={activeProject} onBack={() => setActiveProject(null)} />
        ) : projectSubView === 'ontology' ? (
          <OntologyWorkspace project={activeProject} onBack={() => setActiveProject(null)} />
        ) : projectSubView === 'query' ? (
          <QueryWorkspace project={activeProject} onBack={() => setActiveProject(null)} />
        ) : projectSubView === 'process' ? (
          <ProcessWorkspace project={activeProject} onBack={() => setActiveProject(null)} />
        ) : projectSubView === 'monitors' ? (
          <MonitorsWorkspace
            project={activeProject}
            onBack={() => setActiveProject(null)}
            onNavigateToInvestigations={() => setProjectSubView('investigations')}
          />
        ) : (
          <InvestigationsWorkspace project={activeProject} onBack={() => setActiveProject(null)} />
        )}
      </div>
    )
  }

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-6">
      {/* Workspace Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-lg font-bold text-white">Tenant Workspaces & Projects</h3>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
              Tenant: {activeOrg.slug}
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Projects strictly scoped to organization <span className="font-semibold text-slate-300">{activeOrg.name}</span>. Cross-tenant reads and mutations are deterministically prohibited.
          </p>
        </div>

        <button
          onClick={() => setShowCreateModal(true)}
          className="inline-flex items-center gap-2 px-3.5 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold rounded-lg transition-colors shadow-lg shadow-indigo-600/20 shrink-0"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          <span>New Project</span>
        </button>
      </div>

      {/* Tenant Context Banner */}
      <div className="p-3 bg-slate-950/80 border border-slate-800/80 rounded-xl text-xs flex flex-wrap items-center justify-between gap-2 text-slate-400">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-indigo-500 animate-pulse" />
          <span>Active Tenant Header:</span>
          <code className="text-indigo-300 font-mono text-[11px] bg-indigo-950/60 px-2 py-0.5 rounded border border-indigo-800/40">
            X-Organization-ID: {activeOrg.id}
          </code>
        </div>
        <div className="text-[11px]">
          Your Role: <span className="font-semibold text-slate-200">{activeOrg.role}</span>
        </div>
      </div>

      {/* Error Notice */}
      {error && (
        <div className="p-3 bg-rose-950/60 border border-rose-800/80 rounded-lg text-rose-200 text-xs">
          {error}
        </div>
      )}

      {/* Projects List */}
      {loading ? (
        <div className="py-12 text-center text-xs text-slate-500 flex items-center justify-center gap-2">
          <svg className="w-4 h-4 animate-spin text-indigo-400" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
          </svg>
          <span>Loading tenant projects...</span>
        </div>
      ) : projects.length === 0 ? (
        <div className="py-12 text-center text-slate-400 space-y-2">
          <p className="text-sm font-semibold text-white">No projects found in this organization</p>
          <p className="text-xs text-slate-500 max-w-sm mx-auto">
            Get started by creating your first project workspace (such as the reference Procure-to-Pay vertical slice).
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {projects.map((proj) => (
            <div
              key={proj.id}
              data-testid={`project-card-${proj.id}`}
              onClick={() => setActiveProject(proj)}
              className="p-4 rounded-xl bg-slate-950/60 border border-slate-800/80 hover:border-indigo-500/50 hover:bg-slate-950/90 transition-all flex flex-col justify-between space-y-3 cursor-pointer group shadow-sm hover:shadow-indigo-500/10"
            >
              <div>
                <div className="flex items-start justify-between gap-2">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation()
                      setActiveProject(proj)
                    }}
                    className="font-bold text-white text-sm truncate group-hover:text-indigo-400 transition-colors text-left"
                  >
                    {proj.name}
                  </button>
                  <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 shrink-0">
                    {proj.status}
                  </span>
                </div>
                <div className="text-[10px] font-mono text-slate-500 mt-0.5 truncate">
                  {proj.slug}
                </div>
                <p className="text-xs text-slate-400 mt-2 line-clamp-2">
                  {proj.description || 'No description provided.'}
                </p>
              </div>

              <div className="pt-3 border-t border-slate-800/60 flex items-center justify-between text-[11px] text-slate-500">
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    data-testid="open-workspace-btn"
                    aria-label={`Open workspace for ${proj.name}`}
                    onClick={(e) => {
                      e.stopPropagation()
                      setActiveProject(proj)
                    }}
                    className="px-2.5 py-1 bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-300 font-semibold rounded text-[11px] transition-colors flex items-center gap-1.5"
                  >
                    <span>Open Workspace</span>
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                    </svg>
                  </button>
                  <span>Created {new Date(proj.created_at).toLocaleDateString()}</span>
                </div>
                {activeOrg.role === 'ORG_ADMIN' && (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation()
                      handleDeleteProject(proj.id, proj.name)
                    }}
                    className="text-rose-400 hover:text-rose-300 hover:underline transition-colors"
                  >
                    Delete
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create Project Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
          <div className="relative w-full max-w-md bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl p-6 text-slate-100">
            <button
              onClick={() => setShowCreateModal(false)}
              className="absolute top-4 right-4 text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors"
              aria-label="Close"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>

            <h3 className="text-xl font-bold text-white mb-1">Create Project Workspace</h3>
            <p className="text-xs text-slate-400 mb-4">
              Scoped strictly to organization <span className="font-semibold text-slate-200">{activeOrg.name}</span>.
            </p>

            {createError && (
              <div className="mb-4 p-3 bg-rose-950/60 border border-rose-800/80 rounded-lg text-rose-200 text-xs">
                {createError}
              </div>
            )}

            <form onSubmit={handleCreateProject} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1" htmlFor="project-name">
                  Project Name
                </label>
                <input
                  id="project-name"
                  type="text"
                  required
                  value={projName}
                  onChange={(e) => {
                    setProjName(e.target.value)
                    if (!projSlug) {
                      setProjSlug(e.target.value.toLowerCase().replace(/[^a-z0-9]/g, '-').replace(/-+/g, '-'))
                    }
                  }}
                  placeholder="Procure-to-Pay Intelligence"
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1" htmlFor="project-slug">
                  Project Slug (Unique within Organization)
                </label>
                <input
                  id="project-slug"
                  type="text"
                  required
                  value={projSlug}
                  onChange={(e) => setProjSlug(e.target.value.toLowerCase())}
                  placeholder="p2p-intelligence"
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm font-mono text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1" htmlFor="project-description">
                  Description (Optional)
                </label>
                <textarea
                  id="project-description"
                  rows={2}
                  value={projDesc}
                  onChange={(e) => setProjDesc(e.target.value)}
                  placeholder="Operational intelligence and exception monitoring for P2P."
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <div className="flex gap-3 justify-end pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 font-semibold text-xs rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createLoading}
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-semibold text-xs rounded-lg transition-colors flex items-center gap-2"
                >
                  {createLoading && (
                    <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                    </svg>
                  )}
                  Create Project
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
