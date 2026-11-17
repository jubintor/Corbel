import { useState, useEffect, useCallback, type FormEvent } from 'react'
import { useAuth } from '../context/AuthContext'
import type { Project } from '../types/auth'
import type {
  UseCaseResponse,
  UseCaseDetailResponse,
  UseCaseSpecification,
  SpecificationVersionSummary,
  SpecificationDiffResponse,
} from '../types/api_generated'
import {
  createUseCase,
  listUseCases,
  getUseCase,
  addDiscoveryMessage,
  generateSpecification,
  listSpecifications,
  compareSpecifications,
  approveSpecification,
} from '../services/architect'
import { AuthApiError } from '../services/auth'

interface ArchitectWorkspaceProps {
  project: Project
  onBack: () => void
}

export function ArchitectWorkspace({ project, onBack }: ArchitectWorkspaceProps) {
  const { token, activeOrg } = useAuth()

  // State
  const [useCases, setUseCases] = useState<UseCaseResponse[]>([])
  const [selectedUseCaseId, setSelectedUseCaseId] = useState<string | null>(null)
  const [activeDetail, setActiveDetail] = useState<UseCaseDetailResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Creation modal
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const [newDescription, setNewDescription] = useState('')

  // Discovery turn message
  const [discoveryReply, setDiscoveryReply] = useState('')

  // Sub-tabs in detail view
  const [activeTab, setActiveTab] = useState<
    'discovery' | 'architecture' | 'implementation' | 'history'
  >('discovery')

  // Version history & diff
  const [versions, setVersions] = useState<SpecificationVersionSummary[]>([])
  const [diffResult, setDiffResult] = useState<SpecificationDiffResponse | null>(null)
  const [compareV1, setCompareV1] = useState<number>(1)
  const [compareV2, setCompareV2] = useState<number>(1)

  // 1. Load Use Cases List
  const loadUseCases = useCallback(async () => {
    if (!token || !activeOrg) return
    setLoading(true)
    setError(null)
    try {
      const items = await listUseCases(token, activeOrg.id, project.id)
      setUseCases(items)
      if (items.length > 0 && !selectedUseCaseId) {
        setSelectedUseCaseId(items[0].id)
      }
    } catch (err: unknown) {
      if (err instanceof AuthApiError) setError(err.message)
      else setError('Failed to load use cases for this project.')
    } finally {
      setLoading(false)
    }
  }, [token, activeOrg, project.id, selectedUseCaseId])

  useEffect(() => {
    loadUseCases()
  }, [loadUseCases])

  // 2. Load Selected Use Case Details
  const loadDetail = useCallback(async (id: string) => {
    if (!token || !activeOrg) return
    setError(null)
    try {
      const detail = await getUseCase(token, activeOrg.id, project.id, id)
      setActiveDetail(detail)
      if (detail.current_version > 0) {
        const specs = await listSpecifications(token, activeOrg.id, project.id, id)
        setVersions(specs)
        if (specs.length >= 2) {
          setCompareV1(specs[1].version)
          setCompareV2(specs[0].version)
        } else if (specs.length === 1) {
          setCompareV1(specs[0].version)
          setCompareV2(specs[0].version)
        }
      } else {
        setVersions([])
      }
    } catch (err: unknown) {
      if (err instanceof AuthApiError) setError(err.message)
      else setError('Failed to load use case details.')
    }
  }, [token, activeOrg, project.id])

  useEffect(() => {
    if (selectedUseCaseId) {
      loadDetail(selectedUseCaseId)
    } else {
      setActiveDetail(null)
    }
  }, [selectedUseCaseId, loadDetail])

  // 3. Create Use Case
  const handleCreateUseCase = async (e: FormEvent) => {
    e.preventDefault()
    if (!token || !activeOrg) return
    setActionLoading(true)
    setError(null)
    try {
      const created = await createUseCase(token, activeOrg.id, project.id, {
        title: newTitle,
        description: newDescription,
      })
      setShowCreateModal(false)
      setNewTitle('')
      setNewDescription('')
      await loadUseCases()
      setSelectedUseCaseId(created.id)
    } catch (err: unknown) {
      if (err instanceof AuthApiError) setError(err.message)
      else setError('Failed to create use case.')
    } finally {
      setActionLoading(false)
    }
  }

  // 4. Submit Discovery Answer
  const handleSendDiscoveryMessage = async (e: FormEvent) => {
    e.preventDefault()
    if (!token || !activeOrg || !selectedUseCaseId || !discoveryReply.trim()) return
    setActionLoading(true)
    setError(null)
    try {
      await addDiscoveryMessage(
        token,
        activeOrg.id,
        project.id,
        selectedUseCaseId,
        discoveryReply.trim()
      )
      setDiscoveryReply('')
      await loadDetail(selectedUseCaseId)
    } catch (err: unknown) {
      if (err instanceof AuthApiError) setError(err.message)
      else setError('Failed to post discovery response.')
    } finally {
      setActionLoading(false)
    }
  }

  // 5. Generate Specification
  const handleGenerateSpecification = async () => {
    if (!token || !activeOrg || !selectedUseCaseId) return
    setActionLoading(true)
    setError(null)
    try {
      await generateSpecification(token, activeOrg.id, project.id, selectedUseCaseId)
      await loadDetail(selectedUseCaseId)
      await loadUseCases()
      setActiveTab('architecture')
    } catch (err: unknown) {
      if (err instanceof AuthApiError) setError(err.message)
      else setError('Failed to generate solution specification.')
    } finally {
      setActionLoading(false)
    }
  }

  // 6. Approve Specification
  const handleApproveSpecification = async () => {
    if (!token || !activeOrg || !selectedUseCaseId) return
    setActionLoading(true)
    setError(null)
    try {
      await approveSpecification(token, activeOrg.id, project.id, selectedUseCaseId)
      await loadDetail(selectedUseCaseId)
      await loadUseCases()
    } catch (err: unknown) {
      if (err instanceof AuthApiError) setError(err.message)
      else setError('Failed to approve specification. Check user role permissions.')
    } finally {
      setActionLoading(false)
    }
  }

  // 7. Compare Specification Versions
  const handleCompareVersions = async () => {
    if (!token || !activeOrg || !selectedUseCaseId) return
    setActionLoading(true)
    setError(null)
    try {
      const diff = await compareSpecifications(
        token,
        activeOrg.id,
        project.id,
        selectedUseCaseId,
        compareV1,
        compareV2
      )
      setDiffResult(diff)
    } catch (err: unknown) {
      if (err instanceof AuthApiError) setError(err.message)
      else setError('Failed to compare specification revisions.')
    } finally {
      setActionLoading(false)
    }
  }

  const spec: UseCaseSpecification | null = activeDetail?.latest_specification || null

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <div className="flex items-center gap-3">
            <button
              onClick={onBack}
              className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors"
              title="Back to Workspaces"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
              </svg>
            </button>
            <h2 className="text-xl font-bold text-white flex items-center gap-2">
              <span>Use-Case Architect</span>
              <span className="text-xs px-2.5 py-0.5 rounded-full font-medium bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                Phase 11
              </span>
            </h2>
          </div>
          <p className="text-xs text-slate-400 mt-1 pl-8">
            Transform operational business requirements into structured, versioned, technically justified solution designs.
          </p>
        </div>

        <button
          onClick={() => setShowCreateModal(true)}
          className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold rounded-lg shadow-md hover:shadow-indigo-500/20 transition-all flex items-center gap-2 self-start sm:self-auto"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          <span>New Use Case</span>
        </button>
      </div>

      {error && (
        <div className="p-3 bg-rose-950/60 border border-rose-800/80 rounded-lg text-rose-200 text-xs flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-rose-400 hover:text-white text-sm">
            ✕
          </button>
        </div>
      )}

      {/* Main Grid: Sidebar List + Workspace Detail */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Use Case Roster */}
        <div className="lg:col-span-4 bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-col h-[750px]">
          <div className="flex items-center justify-between pb-3 border-b border-slate-800 mb-3">
            <span className="text-xs font-bold text-slate-300 uppercase tracking-wider">
              Project Use Cases ({useCases.length})
            </span>
            {loading && <span className="text-[10px] text-slate-500 animate-pulse">Loading...</span>}
          </div>

          <div className="flex-1 overflow-y-auto space-y-2 pr-1">
            {useCases.length === 0 && !loading && (
              <div className="p-6 text-center text-slate-500 text-xs">
                No use cases created yet. Click <span className="text-indigo-400">"New Use Case"</span> to initiate discovery.
              </div>
            )}
            {useCases.map((uc) => {
              const isSelected = uc.id === selectedUseCaseId
              const statusColor =
                uc.status === 'APPROVED'
                  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                  : uc.status === 'REVIEW'
                  ? 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                  : uc.status === 'DISCOVERY'
                  ? 'bg-sky-500/10 text-sky-400 border-sky-500/20'
                  : 'bg-slate-500/10 text-slate-400 border-slate-500/20'

              return (
                <div
                  key={uc.id}
                  onClick={() => setSelectedUseCaseId(uc.id)}
                  className={`p-3 rounded-lg border cursor-pointer transition-all ${
                    isSelected
                      ? 'bg-indigo-950/40 border-indigo-600/60 shadow-sm'
                      : 'bg-slate-950/60 border-slate-800/80 hover:border-slate-700'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <h4 className="text-xs font-semibold text-slate-100 truncate">{uc.title}</h4>
                    <span className={`text-[10px] font-mono px-2 py-0.5 rounded border uppercase ${statusColor}`}>
                      {uc.status}
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400 line-clamp-2 mb-2">{uc.description}</p>
                  <div className="flex items-center justify-between text-[10px] text-slate-500 font-mono">
                    <span>Rev: v{uc.current_version}</span>
                    <span>{new Date(uc.created_at).toLocaleDateString()}</span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Right Column: Active Use Case Canvas */}
        <div className="lg:col-span-8 bg-slate-900 border border-slate-800 rounded-xl p-5 flex flex-col h-[750px] overflow-hidden">
          {!activeDetail ? (
            <div className="flex-1 flex items-center justify-center text-slate-500 text-xs">
              Select or create a use case to view discovery dialogue and solution design.
            </div>
          ) : (
            <div className="flex flex-col h-full overflow-hidden">
              {/* Header Card */}
              <div className="pb-4 border-b border-slate-800">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-3">
                      <h3 className="text-base font-bold text-white">{activeDetail.title}</h3>
                      <span
                        className={`text-[10px] font-mono px-2 py-0.5 rounded border uppercase ${
                          activeDetail.status === 'APPROVED'
                            ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                            : activeDetail.status === 'REVIEW'
                            ? 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                            : activeDetail.status === 'DISCOVERY'
                            ? 'bg-sky-500/10 text-sky-400 border-sky-500/20'
                            : 'bg-slate-500/10 text-slate-400 border-slate-500/20'
                        }`}
                      >
                        {activeDetail.status}
                      </span>
                      {activeDetail.current_version > 0 && (
                        <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                          v{activeDetail.current_version}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-slate-400 mt-1">{activeDetail.description}</p>
                  </div>

                  <div className="flex items-center gap-2 self-start sm:self-auto">
                    <button
                      onClick={handleGenerateSpecification}
                      disabled={actionLoading}
                      className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs font-semibold rounded-lg shadow transition-colors flex items-center gap-1.5"
                    >
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                      </svg>
                      <span>{spec ? 'Synthesize New Revision' : 'Generate Specification'}</span>
                    </button>

                    {activeDetail.status !== 'APPROVED' && spec && (
                      <button
                        onClick={handleApproveSpecification}
                        disabled={actionLoading}
                        className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-xs font-semibold rounded-lg shadow transition-colors flex items-center gap-1.5"
                      >
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                        </svg>
                        <span>Approve Specification</span>
                      </button>
                    )}
                  </div>
                </div>

                {activeDetail.status === 'APPROVED' && (
                  <div className="mt-3 p-2 bg-emerald-950/40 border border-emerald-800/60 rounded-lg text-emerald-300 text-xs flex items-center gap-2">
                    <svg className="w-4 h-4 shrink-0 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <span>
                      Specification formally approved on{' '}
                      {activeDetail.approved_at ? new Date(activeDetail.approved_at).toLocaleString() : 'N/A'}. Ready for governed execution.
                    </span>
                  </div>
                )}

                {/* Sub-Tabs */}
                <div className="flex gap-2 mt-4">
                  <button
                    onClick={() => setActiveTab('discovery')}
                    className={`px-3 py-1 text-xs font-semibold rounded-md transition-colors ${
                      activeTab === 'discovery'
                        ? 'bg-slate-800 text-indigo-400 border border-slate-700'
                        : 'text-slate-400 hover:text-white'
                    }`}
                  >
                    Discovery Dialogue ({(activeDetail.messages || []).length})
                  </button>
                  <button
                    onClick={() => setActiveTab('architecture')}
                    className={`px-3 py-1 text-xs font-semibold rounded-md transition-colors ${
                      activeTab === 'architecture'
                        ? 'bg-slate-800 text-indigo-400 border border-slate-700'
                        : 'text-slate-400 hover:text-white'
                    }`}
                  >
                    Technical Architecture
                  </button>
                  <button
                    onClick={() => setActiveTab('implementation')}
                    className={`px-3 py-1 text-xs font-semibold rounded-md transition-colors ${
                      activeTab === 'implementation'
                        ? 'bg-slate-800 text-indigo-400 border border-slate-700'
                        : 'text-slate-400 hover:text-white'
                    }`}
                  >
                    Implementation Plan
                  </button>
                  <button
                    onClick={() => setActiveTab('history')}
                    className={`px-3 py-1 text-xs font-semibold rounded-md transition-colors ${
                      activeTab === 'history'
                        ? 'bg-slate-800 text-indigo-400 border border-slate-700'
                        : 'text-slate-400 hover:text-white'
                    }`}
                  >
                    Revisions & Diff ({versions.length})
                  </button>
                </div>
              </div>

              {/* Tab 1: Discovery Dialogue */}
              {activeTab === 'discovery' && (
                <div className="flex-1 flex flex-col min-h-0 pt-4">
                  {/* Messages Thread */}
                  <div className="flex-1 overflow-y-auto space-y-3 pr-2 mb-4">
                    {(activeDetail.messages || []).map((m) => {
                      const isUser = m.sender_role === 'USER'
                      return (
                        <div
                          key={m.id}
                          className={`flex flex-col ${isUser ? 'items-end' : 'items-start'}`}
                        >
                          <div
                            className={`max-w-[85%] rounded-xl p-3.5 text-xs shadow-sm ${
                              isUser
                                ? 'bg-indigo-600 text-white rounded-br-none'
                                : 'bg-slate-800/90 text-slate-200 border border-slate-700/80 rounded-bl-none'
                            }`}
                          >
                            <div className="flex items-center justify-between gap-4 mb-1 text-[10px] opacity-75 font-mono">
                              <span>{m.sender_role}</span>
                              <span>{new Date(m.created_at).toLocaleTimeString()}</span>
                            </div>
                            <p className="whitespace-pre-line leading-relaxed">{m.message_text}</p>

                            {/* Assistant Extracted Requirements Snapshot */}
                            {!isUser && m.extracted_requirements && (
                              <div className="mt-3 pt-3 border-t border-slate-700/80 space-y-2">
                                <div className="text-[11px] font-bold text-indigo-300">
                                  Captured Discovery State:
                                </div>
                                <div className="grid grid-cols-2 gap-2 text-[10px]">
                                  <div>
                                    <span className="text-slate-400 block font-semibold">Stakeholders:</span>
                                    <span className="text-slate-200">
                                      {m.extracted_requirements.stakeholders?.join(', ') || 'TBD'}
                                    </span>
                                  </div>
                                  <div>
                                    <span className="text-slate-400 block font-semibold">Source Systems:</span>
                                    <span className="text-slate-200">
                                      {m.extracted_requirements.source_systems?.join(', ') || 'TBD'}
                                    </span>
                                  </div>
                                </div>

                                {/* Confirmed vs Assumptions distinction */}
                                <div className="space-y-1 pt-1">
                                  <div className="text-[10px] font-semibold text-emerald-400">
                                    ✓ Confirmed Requirements:
                                  </div>
                                  <ul className="list-disc list-inside text-[10px] text-slate-300 pl-1">
                                    {m.extracted_requirements.confirmed_requirements?.map((req, i) => (
                                      <li key={i}>{req}</li>
                                    ))}
                                  </ul>

                                  <div className="text-[10px] font-semibold text-amber-400 pt-1">
                                    ? Unverified Assumptions:
                                  </div>
                                  <ul className="list-disc list-inside text-[10px] text-slate-400 pl-1">
                                    {m.extracted_requirements.unverified_assumptions?.map((ass, i) => (
                                      <li key={i}>{ass}</li>
                                    ))}
                                  </ul>
                                </div>
                              </div>
                            )}

                            {/* Open Clarification Questions */}
                            {!isUser && m.clarification_questions && m.clarification_questions.length > 0 && (
                              <div className="mt-2.5 p-2 bg-indigo-950/60 border border-indigo-800/80 rounded-lg">
                                <div className="text-[10px] font-bold text-indigo-300 mb-1 flex items-center gap-1">
                                  <svg className="w-3 h-3 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                                  </svg>
                                  <span>Clarification Questions:</span>
                                </div>
                                <ul className="list-decimal list-inside text-[10px] text-indigo-200 space-y-0.5">
                                  {m.clarification_questions.map((q, idx) => (
                                    <li key={idx}>{q}</li>
                                  ))}
                                </ul>
                              </div>
                            )}
                          </div>
                        </div>
                      )
                    })}
                  </div>

                  {/* Reply Input Form */}
                  <form onSubmit={handleSendDiscoveryMessage} className="pt-2 border-t border-slate-800 flex gap-2">
                    <input
                      type="text"
                      value={discoveryReply}
                      onChange={(e) => setDiscoveryReply(e.target.value)}
                      placeholder="Answer clarification questions, define tolerances, or specify source systems..."
                      disabled={actionLoading}
                      className="flex-1 px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    />
                    <button
                      type="submit"
                      disabled={actionLoading || !discoveryReply.trim()}
                      className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs font-semibold rounded-lg shadow transition-colors flex items-center gap-1"
                    >
                      <span>Send</span>
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                      </svg>
                    </button>
                  </form>
                </div>
              )}

              {/* Tab 2: Technical Architecture */}
              {activeTab === 'architecture' && (
                <div className="flex-1 overflow-y-auto space-y-4 pt-4 pr-2">
                  {!spec ? (
                    <div className="p-8 text-center text-slate-500 text-xs">
                      No specification synthesized yet. Click{' '}
                      <span className="text-indigo-400 font-semibold">"Generate Specification"</span> to generate the technical architecture.
                    </div>
                  ) : (
                    <>
                      {/* Proposed Pattern Card */}
                      <div className="p-4 bg-slate-950/80 border border-indigo-900/60 rounded-xl space-y-2">
                        <div className="text-[10px] font-mono uppercase text-indigo-400 font-bold tracking-wider">
                          Recommended Solution Pattern
                        </div>
                        <h4 className="text-sm font-bold text-white">{spec.proposed_architecture}</h4>
                        <p className="text-xs text-slate-300 leading-relaxed">
                          {spec.architecture_rationale_and_alternatives.justification}
                        </p>
                      </div>

                      {/* Architecture Components Breakdown */}
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                        <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg space-y-1.5">
                          <div className="text-xs font-bold text-emerald-400 flex items-center gap-1.5">
                            <span className="w-2 h-2 rounded-full bg-emerald-500" />
                            Deterministic Components
                          </div>
                          <ul className="text-[11px] text-slate-300 space-y-1 list-disc list-inside pl-1">
                            {spec.architecture_rationale_and_alternatives.deterministic_components?.map((c, i) => (
                              <li key={i}>{c}</li>
                            ))}
                          </ul>
                        </div>

                        <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg space-y-1.5">
                          <div className="text-xs font-bold text-sky-400 flex items-center gap-1.5">
                            <span className="w-2 h-2 rounded-full bg-sky-500" />
                            Retrieval Architecture
                          </div>
                          <ul className="text-[11px] text-slate-300 space-y-1 list-disc list-inside pl-1">
                            {spec.architecture_rationale_and_alternatives.retrieval_components?.map((c, i) => (
                              <li key={i}>{c}</li>
                            ))}
                          </ul>
                        </div>

                        <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg space-y-1.5">
                          <div className="text-xs font-bold text-indigo-400 flex items-center gap-1.5">
                            <span className="w-2 h-2 rounded-full bg-indigo-500" />
                            Governed AI & State Machines
                          </div>
                          <ul className="text-[11px] text-slate-300 space-y-1 list-disc list-inside pl-1">
                            {spec.architecture_rationale_and_alternatives.agentic_components?.map((c, i) => (
                              <li key={i}>{c}</li>
                            ))}
                          </ul>
                        </div>
                      </div>

                      {/* Alternatives Considered Table */}
                      <div className="p-4 bg-slate-950 border border-slate-800 rounded-xl space-y-3">
                        <h4 className="text-xs font-bold text-slate-200 uppercase tracking-wider">
                          Alternatives Considered & Rejection Rationale
                        </h4>
                        <div className="space-y-3">
                          {spec.architecture_rationale_and_alternatives.alternatives_considered?.map((alt, idx) => (
                            <div key={idx} className="p-3 bg-slate-900 border border-slate-800 rounded-lg space-y-1.5">
                              <div className="flex items-center justify-between">
                                <span className="text-xs font-semibold text-rose-300">{alt.approach}</span>
                                <span className="text-[10px] font-mono text-slate-500">Rejected Alternative</span>
                              </div>
                              <p className="text-xs text-rose-200/90 font-medium">
                                <span className="text-slate-400">Why Rejected: </span>
                                {alt.rejection_reason}
                              </p>
                              <div className="grid grid-cols-2 gap-2 text-[10px] pt-1">
                                <div>
                                  <span className="text-emerald-400 font-semibold block">Pros:</span>
                                  <ul className="list-disc list-inside text-slate-300">
                                    {(alt.pros || []).map((p, i) => (
                                      <li key={i}>{p}</li>
                                    ))}
                                  </ul>
                                </div>
                                <div>
                                  <span className="text-rose-400 font-semibold block">Cons:</span>
                                  <ul className="list-disc list-inside text-slate-300">
                                    {(alt.cons || []).map((c, i) => (
                                      <li key={i}>{c}</li>
                                    ))}
                                  </ul>
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Governance & Human-in-the-Loop Gates */}
                      <div className="p-4 bg-slate-950 border border-slate-800 rounded-xl space-y-2">
                        <div className="flex items-center justify-between">
                          <h4 className="text-xs font-bold text-slate-200 uppercase tracking-wider">
                            Governance & Human Approval Gates
                          </h4>
                          <span
                            className={`text-[10px] font-mono px-2 py-0.5 rounded border uppercase ${
                              spec.risk_level === 'HIGH' || spec.risk_level === 'CRITICAL'
                                ? 'bg-rose-500/10 text-rose-400 border-rose-500/20'
                                : 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                            }`}
                          >
                            Risk: {spec.risk_level}
                          </span>
                        </div>
                        <ul className="list-disc list-inside text-xs text-slate-300 space-y-1 pl-1">
                          {(spec.human_approval_requirements || []).map((req, i) => (
                            <li key={i}>{req}</li>
                          ))}
                        </ul>
                      </div>
                    </>
                  )}
                </div>
              )}

              {/* Tab 3: Implementation Plan */}
              {activeTab === 'implementation' && (
                <div className="flex-1 overflow-y-auto space-y-4 pt-4 pr-2">
                  {!spec ? (
                    <div className="p-8 text-center text-slate-500 text-xs">
                      No specification synthesized yet.
                    </div>
                  ) : (
                    <>
                      {/* Milestones */}
                      <div className="space-y-3">
                        <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wider">
                          Delivery Milestones & Effort Estimates
                        </h4>
                        {(spec.implementation_plan || []).map((m) => (
                          <div key={m.milestone_id} className="p-3.5 bg-slate-950 border border-slate-800 rounded-lg space-y-2">
                            <div className="flex items-center justify-between">
                              <span className="text-xs font-bold text-indigo-400">
                                [{m.milestone_id}] {m.title}
                              </span>
                              <span className="text-[10px] font-mono text-amber-300 bg-amber-500/10 px-2 py-0.5 rounded border border-amber-500/20">
                                {m.estimated_effort}
                              </span>
                            </div>
                            <p className="text-xs text-slate-300">{m.description}</p>
                            <div className="text-[10px] text-slate-400">
                              <span className="font-semibold text-slate-300">Target Components: </span>
                              {(m.target_components || []).join(', ')}
                            </div>
                            <div className="text-[10px] text-slate-400">
                              <span className="font-semibold text-slate-300">Acceptance Criteria: </span>
                              {(m.acceptance_criteria || []).join(' | ')}
                            </div>
                          </div>
                        ))}
                      </div>

                      {/* Technical Risks & Mitigations */}
                      <div className="p-4 bg-slate-950 border border-slate-800 rounded-xl space-y-3">
                        <h4 className="text-xs font-bold text-slate-200 uppercase tracking-wider">
                          Technical Risks & Mitigations
                        </h4>
                        <div className="space-y-2">
                          {(spec.risks_and_dependencies || []).map((r, i) => (
                            <div key={i} className="p-2.5 bg-slate-900 border border-slate-800 rounded-lg space-y-1">
                              <div className="flex items-center justify-between text-xs font-semibold text-slate-200">
                                <span>{r.risk}</span>
                                <span
                                  className={`text-[9px] font-mono px-1.5 py-0.5 rounded ${
                                    r.severity === 'HIGH'
                                      ? 'text-rose-400 bg-rose-500/10'
                                      : 'text-amber-400 bg-amber-500/10'
                                  }`}
                                >
                                  {r.severity}
                                </span>
                              </div>
                              <p className="text-[11px] text-slate-400">
                                <span className="font-semibold text-slate-300">Mitigation: </span>
                                {r.mitigation}
                              </p>
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Success Metrics & Evaluation */}
                      <div className="p-4 bg-slate-950 border border-slate-800 rounded-xl space-y-2">
                        <h4 className="text-xs font-bold text-slate-200 uppercase tracking-wider">
                          Success Metrics & Evaluation Plan
                        </h4>
                        <ul className="list-disc list-inside text-xs text-slate-300 space-y-1 pl-1">
                          {(spec.success_metrics || []).map((sm, i) => (
                            <li key={i}>{sm}</li>
                          ))}
                        </ul>
                        <div className="text-xs text-slate-400 pt-2 border-t border-slate-800">
                          <span className="font-semibold text-slate-300">Evaluation Strategy: </span>
                          {spec.evaluation_plan}
                        </div>
                      </div>
                    </>
                  )}
                </div>
              )}

              {/* Tab 4: Revisions & Diff */}
              {activeTab === 'history' && (
                <div className="flex-1 overflow-y-auto space-y-4 pt-4 pr-2">
                  {versions.length === 0 ? (
                    <div className="p-8 text-center text-slate-500 text-xs">
                      No specification revisions exist yet.
                    </div>
                  ) : (
                    <>
                      {/* Version Compare Controls */}
                      <div className="p-4 bg-slate-950 border border-slate-800 rounded-xl space-y-3">
                        <div className="text-xs font-bold text-slate-200 uppercase tracking-wider">
                          Compare Specification Revisions
                        </div>
                        <div className="flex items-center gap-3">
                          <div className="flex items-center gap-2 text-xs text-slate-300">
                            <span>Base:</span>
                            <select
                              value={compareV1}
                              onChange={(e) => setCompareV1(Number(e.target.value))}
                              className="px-2 py-1 bg-slate-900 border border-slate-700 rounded text-xs text-slate-100"
                            >
                              {versions.map((v) => (
                                <option key={v.version} value={v.version}>
                                  v{v.version}
                                </option>
                              ))}
                            </select>
                          </div>
                          <div className="flex items-center gap-2 text-xs text-slate-300">
                            <span>Target:</span>
                            <select
                              value={compareV2}
                              onChange={(e) => setCompareV2(Number(e.target.value))}
                              className="px-2 py-1 bg-slate-900 border border-slate-700 rounded text-xs text-slate-100"
                            >
                              {versions.map((v) => (
                                <option key={v.version} value={v.version}>
                                  v{v.version}
                                </option>
                              ))}
                            </select>
                          </div>
                          <button
                            onClick={handleCompareVersions}
                            disabled={actionLoading}
                            className="px-3 py-1 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold rounded shadow transition-colors"
                          >
                            Compare
                          </button>
                        </div>

                        {diffResult && (
                          <div className="mt-3 p-3 bg-slate-900 border border-slate-800 rounded-lg space-y-2">
                            <div className="text-xs font-semibold text-indigo-300">{diffResult.summary}</div>
                            {Object.entries(diffResult.differences).map(([field, delta]) => (
                              <div key={field} className="text-xs p-2 bg-slate-950 rounded border border-slate-800">
                                <span className="font-mono text-indigo-400 font-bold">{field}</span>
                                <div className="grid grid-cols-2 gap-2 mt-1 text-[11px]">
                                  <div className="text-rose-300">
                                    <span className="text-slate-500 block">v{diffResult.v1}:</span>
                                    {typeof delta.v1 === 'object'
                                      ? JSON.stringify(delta.v1)
                                      : String(delta.v1)}
                                  </div>
                                  <div className="text-emerald-300">
                                    <span className="text-slate-500 block">v{diffResult.v2}:</span>
                                    {typeof delta.v2 === 'object'
                                      ? JSON.stringify(delta.v2)
                                      : String(delta.v2)}
                                  </div>
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>

                      {/* Versions List */}
                      <div className="space-y-2">
                        <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wider">
                          Revision History ({versions.length})
                        </h4>
                        {versions.map((v) => (
                          <div
                            key={v.version}
                            className="p-3 bg-slate-950 border border-slate-800 rounded-lg flex items-center justify-between text-xs"
                          >
                            <div>
                              <div className="font-bold text-white flex items-center gap-2">
                                <span>Revision v{v.version}</span>
                                <span className="text-[10px] font-mono text-slate-400">
                                  {new Date(v.created_at).toLocaleString()}
                                </span>
                              </div>
                              <div className="text-slate-400 text-[11px] mt-0.5">{v.proposed_architecture}</div>
                            </div>
                            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                              Risk: {v.risk_level}
                            </span>
                          </div>
                        ))}
                      </div>
                    </>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Create Use Case Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
          <div className="relative w-full max-w-lg bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl p-6 text-slate-100">
            <button
              onClick={() => setShowCreateModal(false)}
              className="absolute top-4 right-4 text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors"
              aria-label="Close"
            >
              ✕
            </button>

            <h3 className="text-lg font-bold text-white mb-1">Initiate Use-Case Discovery</h3>
            <p className="text-xs text-slate-400 mb-4">
              Describe your operational business problem. The Use-Case Architect will extract requirements, ask focused clarification questions, and propose a justified architecture.
            </p>

            <form onSubmit={handleCreateUseCase} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1" htmlFor="usecase-title">
                  Use Case Title
                </label>
                <input
                  id="usecase-title"
                  type="text"
                  required
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  placeholder="e.g. Procurement Exception and Invoice Discrepancy Intelligence"
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1" htmlFor="usecase-description">
                  Business Problem Statement
                </label>
                <textarea
                  id="usecase-description"
                  required
                  rows={4}
                  value={newDescription}
                  onChange={(e) => setNewDescription(e.target.value)}
                  placeholder="Describe the operational pain point, affected processes (e.g. PO, Goods Receipts, Invoices), latency expectations, and users involved..."
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
                  disabled={actionLoading || !newTitle.trim() || !newDescription.trim()}
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-semibold text-xs rounded-lg shadow-md transition-colors"
                >
                  Start Discovery
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
