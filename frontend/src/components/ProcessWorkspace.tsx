import { useState, useEffect, useCallback, type FormEvent } from 'react'
import { useAuth } from '../context/AuthContext'
import type { Project } from '../types/auth'
import type {
  Process,
  ProcessOverview,
  ProcessVariantsResponse,
  DFGResponse,
  ProcessCaseListResponse,
  ProcessCaseDetailResponse,
  DFGEdge,
} from '../types/process'
import {
  listProcesses,
  createProcess,
  reconstructProcess,
  getProcessOverview,
  getProcessVariants,
  getDFG,
  listProcessCases,
  getProcessCaseDetail,
  deleteProcess,
} from '../services/process'
import { AuthApiError } from '../services/auth'

interface ProcessWorkspaceProps {
  project: Project
  onBack: () => void
}

function formatDuration(seconds: number): string {
  if (seconds <= 0) return '0s'
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  const parts: string[] = []
  if (d > 0) parts.push(`${d}d`)
  if (h > 0) parts.push(`${h}h`)
  if (m > 0 && d === 0) parts.push(`${m}m`)
  if (s > 0 && d === 0 && h === 0) parts.push(`${s}s`)
  return parts.join(' ') || `${s}s`
}

export function ProcessWorkspace({ project, onBack }: ProcessWorkspaceProps) {
  const { token, activeOrg } = useAuth()

  // State
  const [processes, setProcesses] = useState<Process[]>([])
  const [activeProcess, setActiveProcess] = useState<Process | null>(null)
  const [activeTab, setActiveTab] = useState<'flow' | 'variants' | 'cases'>('flow')
  const [loading, setLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  // Sub-data state
  const [overview, setOverview] = useState<ProcessOverview | null>(null)
  const [variantsData, setVariantsData] = useState<ProcessVariantsResponse | null>(null)
  const [dfgData, setDfgData] = useState<DFGResponse | null>(null)
  const [casesData, setCasesData] = useState<ProcessCaseListResponse | null>(null)
  const [selectedCaseDetail, setSelectedCaseDetail] = useState<ProcessCaseDetailResponse | null>(null)
  const [selectedEdge, setSelectedEdge] = useState<DFGEdge | null>(null)

  // Create Process Modal
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [newProcName, setNewProcName] = useState('')
  const [newProcDesc, setNewProcDesc] = useState('')
  const [newProcTargetHours, setNewProcTargetHours] = useState('72')

  const loadProcesses = useCallback(async () => {
    if (!token || !activeOrg) return
    setLoading(true)
    setError(null)
    try {
      const list = await listProcesses(token, activeOrg.id, project.id)
      setProcesses(list)
      if (list.length > 0 && (!activeProcess || !list.some((p) => p.id === activeProcess.id))) {
        setActiveProcess(list[0])
      }
    } catch (err: unknown) {
      setError(err instanceof AuthApiError ? err.message : 'Failed to load processes')
    } finally {
      setLoading(false)
    }
  }, [token, activeOrg, project.id, activeProcess])

  useEffect(() => {
    void loadProcesses()
  }, [loadProcesses])

  // Load process analytics when activeProcess changes
  const loadProcessData = useCallback(async (procId: string) => {
    if (!token || !activeOrg) return
    setLoading(true)
    setError(null)
    try {
      const [ov, vars, dfg, cases] = await Promise.all([
        getProcessOverview(token, activeOrg.id, project.id, procId),
        getProcessVariants(token, activeOrg.id, project.id, procId),
        getDFG(token, activeOrg.id, project.id, procId),
        listProcessCases(token, activeOrg.id, project.id, procId, 1, 25),
      ])
      setOverview(ov)
      setVariantsData(vars)
      setDfgData(dfg)
      setCasesData(cases)
      setSelectedCaseDetail(null)
      setSelectedEdge(null)
    } catch (err: unknown) {
      setError(err instanceof AuthApiError ? err.message : 'Failed to load process intelligence data')
    } finally {
      setLoading(false)
    }
  }, [token, activeOrg, project.id])

  useEffect(() => {
    if (activeProcess) {
      void loadProcessData(activeProcess.id)
    } else {
      setOverview(null)
      setVariantsData(null)
      setDfgData(null)
      setCasesData(null)
    }
  }, [activeProcess, loadProcessData])

  const handleCreateProcess = async (e: FormEvent) => {
    e.preventDefault()
    if (!token || !activeOrg || !newProcName.trim()) return
    setActionLoading(true)
    setError(null)
    try {
      const targetSec = parseFloat(newProcTargetHours) * 3600
      const created = await createProcess(token, activeOrg.id, project.id, {
        name: newProcName.trim(),
        description: newProcDesc.trim() || undefined,
        target_duration_seconds: isNaN(targetSec) ? undefined : targetSec,
      })
      setShowCreateModal(false)
      setNewProcName('')
      setNewProcDesc('')
      setProcesses((prev) => [created, ...prev])
      setActiveProcess(created)
      setSuccessMessage(`Process "${created.name}" created successfully.`)
    } catch (err: unknown) {
      setError(err instanceof AuthApiError ? err.message : 'Failed to create process')
    } finally {
      setActionLoading(false)
    }
  }

  const handleReconstructP2P = async () => {
    if (!token || !activeOrg || !activeProcess) return
    setActionLoading(true)
    setError(null)
    setSuccessMessage(null)
    try {
      const res = await reconstructProcess(token, activeOrg.id, project.id, activeProcess.id, {
        mode: 'P2P_ONTOLOGY',
      })
      setSuccessMessage(
        `Reconstruction complete: Reconstructed ${res.cases_reconstructed} cases and ${res.events_reconstructed} events across ${res.variants_discovered} distinct variants (${res.execution_time_ms.toFixed(1)} ms).`
      )
      await loadProcessData(activeProcess.id)
    } catch (err: unknown) {
      setError(err instanceof AuthApiError ? err.message : 'P2P event log reconstruction failed')
    } finally {
      setActionLoading(false)
    }
  }

  const handleDeleteProcess = async () => {
    if (!token || !activeOrg || !activeProcess) return
    if (!window.confirm(`Delete process "${activeProcess.name}" and all mined cases?`)) return
    setActionLoading(true)
    try {
      await deleteProcess(token, activeOrg.id, project.id, activeProcess.id)
      const remaining = processes.filter((p) => p.id !== activeProcess.id)
      setProcesses(remaining)
      setActiveProcess(remaining[0] || null)
      setSuccessMessage('Process deleted.')
    } catch (err: unknown) {
      setError(err instanceof AuthApiError ? err.message : 'Failed to delete process')
    } finally {
      setActionLoading(false)
    }
  }

  const handleInspectCase = async (caseId: string) => {
    if (!token || !activeOrg || !activeProcess) return
    try {
      const detail = await getProcessCaseDetail(token, activeOrg.id, project.id, activeProcess.id, caseId)
      setSelectedCaseDetail(detail)
    } catch (err: unknown) {
      setError(err instanceof AuthApiError ? err.message : 'Failed to load case detail')
    }
  }

  return (
    <div className="space-y-6" data-testid="process-workspace">
      {/* Header bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl">
        <div className="space-y-1">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={onBack}
              className="text-xs text-slate-400 hover:text-white transition-colors flex items-center gap-1"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
              <span>Back to Projects</span>
            </button>
            <span className="text-slate-600">/</span>
            <h2 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
              <span>Process Intelligence & Event Mining</span>
              <span className="text-xs font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                Phase 6
              </span>
            </h2>
          </div>
          <p className="text-xs text-slate-400">
            Reconstruct milestone event logs, analyze Directly-Follows Graphs (DFG), discover process variants, track SLA compliance, and identify operational bottlenecks.
          </p>
        </div>

        {/* Process Selector & Action Buttons */}
        <div className="flex items-center gap-2 flex-wrap">
          {processes.length > 0 && (
            <select
              aria-label="Select Process"
              value={activeProcess?.id || ''}
              onChange={(e) => {
                const selected = processes.find((p) => p.id === e.target.value)
                if (selected) setActiveProcess(selected)
              }}
              className="bg-slate-800 border border-slate-700 text-white text-xs rounded-lg px-3 py-2 font-medium focus:outline-none focus:border-indigo-500"
            >
              {processes.map((proc) => (
                <option key={proc.id} value={proc.id}>
                  {proc.name}
                </option>
              ))}
            </select>
          )}

          <button
            type="button"
            onClick={() => setShowCreateModal(true)}
            className="px-3 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-sm transition-colors flex items-center gap-1.5"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            <span>New Process</span>
          </button>

          {activeProcess && (
            <>
              <button
                type="button"
                onClick={handleReconstructP2P}
                disabled={actionLoading}
                className="px-3 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-xs font-semibold shadow-sm transition-colors flex items-center gap-1.5"
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                <span>{actionLoading ? 'Reconstructing...' : 'Reconstruct P2P'}</span>
              </button>

              <button
                type="button"
                onClick={handleDeleteProcess}
                disabled={actionLoading}
                title="Delete Process"
                className="p-2 rounded-lg bg-slate-800 hover:bg-red-500/20 text-slate-400 hover:text-red-400 border border-slate-700 transition-colors"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            </>
          )}
        </div>
      </div>

      {/* Messages */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 text-xs text-red-400 flex items-center gap-2">
          <svg className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span>{error}</span>
        </div>
      )}
      {successMessage && (
        <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-xl p-4 text-xs text-emerald-400 flex items-center gap-2">
          <svg className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
          <span>{successMessage}</span>
        </div>
      )}

      {/* No processes banner */}
      {processes.length === 0 && !loading && (
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-12 text-center text-slate-300">
          <div className="w-12 h-12 mx-auto rounded-full bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400 mb-3">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
          </div>
          <h3 className="text-lg font-bold text-white mb-1">No Processes Initialized</h3>
          <p className="text-xs text-slate-400 max-w-md mx-auto mb-4">
            Create a process container to mine event logs from P2P datasets (Purchase Orders, Goods Receipts, Invoices) or custom event logs.
          </p>
          <button
            type="button"
            onClick={() => setShowCreateModal(true)}
            className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-sm transition-colors"
          >
            Create First Process
          </button>
        </div>
      )}

      {/* Analytics KPIs Overview */}
      {activeProcess && overview && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-3 shadow-md">
            <div className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Total Cases</div>
            <div className="text-xl font-bold text-white mt-1">{overview.total_cases.toLocaleString()}</div>
            <div className="text-[10px] text-slate-500 mt-0.5">{overview.total_events} milestone events</div>
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-xl p-3 shadow-md">
            <div className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Variants</div>
            <div className="text-xl font-bold text-indigo-400 mt-1">{overview.distinct_variants}</div>
            <div className="text-[10px] text-slate-500 mt-0.5">Execution pathways</div>
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-xl p-3 shadow-md">
            <div className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Avg Cycle Time</div>
            <div className="text-xl font-bold text-emerald-400 mt-1">{formatDuration(overview.avg_duration_seconds)}</div>
            <div className="text-[10px] text-slate-500 mt-0.5">Median: {formatDuration(overview.median_duration_seconds)}</div>
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-xl p-3 shadow-md">
            <div className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Target SLA</div>
            <div className="text-xl font-bold text-white mt-1">
              {activeProcess.target_duration_seconds ? formatDuration(activeProcess.target_duration_seconds) : 'None'}
            </div>
            <div className="text-[10px] text-slate-500 mt-0.5">Threshold</div>
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-xl p-3 shadow-md">
            <div className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">SLA Breaches</div>
            <div className={`text-xl font-bold mt-1 ${overview.sla_breach_count > 0 ? 'text-red-400' : 'text-slate-400'}`}>
              {overview.sla_breach_count}
            </div>
            <div className="text-[10px] text-slate-500 mt-0.5">
              {(overview.sla_breach_rate * 100).toFixed(1)}% breach rate
            </div>
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-xl p-3 shadow-md">
            <div className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Rework Rate</div>
            <div className={`text-xl font-bold mt-1 ${overview.rework_case_count > 0 ? 'text-amber-400' : 'text-slate-400'}`}>
              {(overview.rework_case_rate * 100).toFixed(1)}%
            </div>
            <div className="text-[10px] text-slate-500 mt-0.5">{overview.rework_case_count} cases looped</div>
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-xl p-3 shadow-md col-span-2 lg:col-span-1">
            <div className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Top Bottleneck</div>
            {overview.top_bottleneck ? (
              <div className="mt-1">
                <div className="text-xs font-bold text-red-400 truncate" title={`${overview.top_bottleneck.from_activity} → ${overview.top_bottleneck.to_activity}`}>
                  {overview.top_bottleneck.from_activity} → {overview.top_bottleneck.to_activity}
                </div>
                <div className="text-[10px] text-slate-500 mt-0.5">
                  Avg {formatDuration(overview.top_bottleneck.avg_duration_seconds)}
                </div>
              </div>
            ) : (
              <div className="text-xs text-slate-500 mt-1">None identified</div>
            )}
          </div>
        </div>
      )}

      {/* Main Process Exploration Tabs */}
      {activeProcess && (
        <div className="bg-slate-900 border border-slate-800 rounded-2xl shadow-xl overflow-hidden">
          {/* Tab buttons */}
          <div className="flex items-center gap-2 px-6 pt-4 border-b border-slate-800 bg-slate-900/60">
            <button
              type="button"
              data-testid="subtab-flow"
              onClick={() => setActiveTab('flow')}
              className={`px-4 py-2.5 border-b-2 text-xs font-semibold transition-colors flex items-center gap-2 ${
                activeTab === 'flow'
                  ? 'border-indigo-500 text-white'
                  : 'border-transparent text-slate-400 hover:text-slate-200'
              }`}
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
              <span>Process Flow (DFG)</span>
              {dfgData && (
                <span className="text-[10px] px-1.5 py-0.2 rounded bg-slate-800 text-slate-300 font-mono">
                  {dfgData.nodes.length} nodes
                </span>
              )}
            </button>

            <button
              type="button"
              data-testid="subtab-variants"
              onClick={() => setActiveTab('variants')}
              className={`px-4 py-2.5 border-b-2 text-xs font-semibold transition-colors flex items-center gap-2 ${
                activeTab === 'variants'
                  ? 'border-indigo-500 text-white'
                  : 'border-transparent text-slate-400 hover:text-slate-200'
              }`}
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 10h16M4 14h16M4 18h16" />
              </svg>
              <span>Process Variants</span>
              {variantsData && (
                <span className="text-[10px] px-1.5 py-0.2 rounded bg-slate-800 text-slate-300 font-mono">
                  {variantsData.total_variants}
                </span>
              )}
            </button>

            <button
              type="button"
              data-testid="subtab-cases"
              onClick={() => setActiveTab('cases')}
              className={`px-4 py-2.5 border-b-2 text-xs font-semibold transition-colors flex items-center gap-2 ${
                activeTab === 'cases'
                  ? 'border-indigo-500 text-white'
                  : 'border-transparent text-slate-400 hover:text-slate-200'
              }`}
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
              </svg>
              <span>Cases Explorer</span>
              {casesData && (
                <span className="text-[10px] px-1.5 py-0.2 rounded bg-slate-800 text-slate-300 font-mono">
                  {casesData.total}
                </span>
              )}
            </button>
          </div>

          {/* Tab Content */}
          <div className="p-6">
            {/* 1. PROCESS FLOW (DFG) */}
            {activeTab === 'flow' && (
              <div className="space-y-6">
                {dfgData && dfgData.nodes.length > 0 ? (
                  <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    {/* Visual Graph Panel */}
                    <div className="lg:col-span-2 bg-slate-950/80 border border-slate-800 rounded-xl p-5 min-h-[350px]">
                      <div className="flex items-center justify-between mb-4">
                        <div className="text-xs font-bold text-white uppercase tracking-wider flex items-center gap-2">
                          <span>Directly-Follows Graph</span>
                          <span className="text-[10px] font-mono font-normal text-slate-400">
                            ({dfgData.total_transitions} transitions)
                          </span>
                        </div>
                        {dfgData.bottleneck_count > 0 && (
                          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-red-500/10 text-red-400 border border-red-500/20">
                            {dfgData.bottleneck_count} Bottleneck{dfgData.bottleneck_count > 1 ? 's' : ''} Detected
                          </span>
                        )}
                      </div>

                      {/* Interactive Visual Graph of Nodes & Transitions */}
                      <div className="space-y-4">
                        {dfgData.nodes.map((node) => {
                          const outgoing = dfgData.edges.filter((e) => e.source === node.name)
                          return (
                            <div key={node.id} className="bg-slate-900 border border-slate-800 rounded-xl p-3 space-y-2">
                              <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                  <span
                                    className={`w-2 h-2 rounded-full ${
                                      node.is_start_activity
                                        ? 'bg-emerald-400'
                                        : node.is_end_activity
                                        ? 'bg-purple-400'
                                        : 'bg-indigo-400'
                                    }`}
                                  />
                                  <span className="text-xs font-bold text-white">{node.name}</span>
                                  {node.is_start_activity && (
                                    <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                                      Start
                                    </span>
                                  )}
                                  {node.is_end_activity && (
                                    <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-purple-500/10 text-purple-400 border border-purple-500/20">
                                      End
                                    </span>
                                  )}
                                </div>
                                <span className="text-[10px] font-mono text-slate-400">
                                  {node.total_occurrences} execution{node.total_occurrences > 1 ? 's' : ''}
                                </span>
                              </div>

                              {/* Outgoing Transitions */}
                              {outgoing.length > 0 && (
                                <div className="pl-4 border-l border-slate-800 space-y-1.5 pt-1">
                                  {outgoing.map((edge, idx) => (
                                    <div
                                      key={`${edge.source}-${edge.target}-${idx}`}
                                      onClick={() => setSelectedEdge(edge)}
                                      className={`text-[11px] p-2 rounded-lg cursor-pointer transition-colors flex items-center justify-between ${
                                        selectedEdge?.source === edge.source && selectedEdge?.target === edge.target
                                          ? 'bg-indigo-600/20 border border-indigo-500/40 text-white'
                                          : edge.is_bottleneck
                                          ? 'bg-red-500/10 border border-red-500/20 text-red-300 hover:bg-red-500/20'
                                          : edge.is_rework_loop
                                          ? 'bg-amber-500/10 border border-amber-500/20 text-amber-300 hover:bg-amber-500/20'
                                          : 'bg-slate-800/40 hover:bg-slate-800 border border-transparent text-slate-300'
                                      }`}
                                    >
                                      <div className="flex items-center gap-2">
                                        <svg className="w-3.5 h-3.5 text-slate-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                                        </svg>
                                        <span className="font-semibold text-slate-200">{edge.target}</span>
                                        {edge.is_bottleneck && (
                                          <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-red-500/20 text-red-300">
                                            Bottleneck
                                          </span>
                                        )}
                                        {edge.is_rework_loop && (
                                          <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-amber-500/20 text-amber-300">
                                            Rework Loop
                                          </span>
                                        )}
                                      </div>
                                      <div className="flex items-center gap-3 font-mono text-[10px]">
                                        <span className="text-slate-400">{edge.transition_count}x</span>
                                        <span className={edge.is_bottleneck ? 'text-red-400 font-bold' : 'text-slate-300'}>
                                          avg {formatDuration(edge.avg_duration_seconds)}
                                        </span>
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          )
                        })}
                      </div>
                    </div>

                    {/* Transition Inspector Detail Panel */}
                    <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-5 space-y-4">
                      <div className="text-xs font-bold text-white uppercase tracking-wider">
                        Transition Analytics
                      </div>
                      {selectedEdge ? (
                        <div className="space-y-4 text-xs">
                          <div className="bg-slate-900 border border-slate-800 rounded-xl p-3.5 space-y-2">
                            <div className="text-[10px] text-slate-400 uppercase font-semibold">Transition</div>
                            <div className="text-sm font-bold text-white flex items-center gap-2">
                              <span>{selectedEdge.source}</span>
                              <span className="text-slate-500">→</span>
                              <span>{selectedEdge.target}</span>
                            </div>
                            <div className="flex items-center gap-2 pt-1">
                              {selectedEdge.is_bottleneck && (
                                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-red-500/10 text-red-400 border border-red-500/20">
                                  Active Bottleneck
                                </span>
                              )}
                              {selectedEdge.is_rework_loop && (
                                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">
                                  Rework Loop
                                </span>
                              )}
                            </div>
                          </div>

                          <div className="grid grid-cols-2 gap-2 font-mono">
                            <div className="bg-slate-900 border border-slate-800 rounded-lg p-2.5">
                              <div className="text-[9px] text-slate-500 uppercase">Transitions</div>
                              <div className="text-sm font-bold text-white mt-0.5">{selectedEdge.transition_count}</div>
                            </div>
                            <div className="bg-slate-900 border border-slate-800 rounded-lg p-2.5">
                              <div className="text-[9px] text-slate-500 uppercase">Avg Duration</div>
                              <div className="text-sm font-bold text-emerald-400 mt-0.5">{formatDuration(selectedEdge.avg_duration_seconds)}</div>
                            </div>
                            <div className="bg-slate-900 border border-slate-800 rounded-lg p-2.5">
                              <div className="text-[9px] text-slate-500 uppercase">Median Duration</div>
                              <div className="text-sm font-bold text-white mt-0.5">{formatDuration(selectedEdge.median_duration_seconds)}</div>
                            </div>
                            <div className="bg-slate-900 border border-slate-800 rounded-lg p-2.5">
                              <div className="text-[9px] text-slate-500 uppercase">Min / Max</div>
                              <div className="text-xs font-bold text-slate-300 mt-0.5">
                                {formatDuration(selectedEdge.min_duration_seconds)} / {formatDuration(selectedEdge.max_duration_seconds)}
                              </div>
                            </div>
                          </div>
                        </div>
                      ) : (
                        <div className="text-xs text-slate-500 italic p-6 text-center border border-dashed border-slate-800 rounded-xl">
                          Click any transition edge in the flow graph to inspect duration statistics and latency metrics.
                        </div>
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="text-center py-12 text-slate-400 text-xs">
                    No graph data available. Click <strong className="text-white">Reconstruct P2P</strong> above to generate events from your datasets.
                  </div>
                )}
              </div>
            )}

            {/* 2. PROCESS VARIANTS */}
            {activeTab === 'variants' && (
              <div className="space-y-4">
                {variantsData && variantsData.variants.length > 0 ? (
                  <div className="space-y-3">
                    {variantsData.variants.map((v, idx) => (
                      <div
                        key={v.variant_key}
                        className={`bg-slate-950/60 border rounded-xl p-4 transition-colors space-y-3 ${
                          v.is_happy_path ? 'border-emerald-500/30 bg-emerald-950/10' : 'border-slate-800'
                        }`}
                      >
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-mono font-bold text-slate-500">#{idx + 1}</span>
                            <span className="text-xs font-bold text-white">
                              {v.is_happy_path ? 'Standard Happy Path' : `Variant ${idx + 1}`}
                            </span>
                            {v.is_happy_path && (
                              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                                Happy Path
                              </span>
                            )}
                          </div>
                          <div className="flex items-center gap-4 text-xs font-mono">
                            <span className="text-slate-300">
                              <strong className="text-white">{v.case_count}</strong> cases ({v.percentage_of_total.toFixed(1)}%)
                            </span>
                            <span className="text-slate-400">
                              Avg: <strong className="text-emerald-400">{formatDuration(v.avg_duration_seconds)}</strong>
                            </span>
                          </div>
                        </div>

                        {/* Frequency progress bar */}
                        <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full ${v.is_happy_path ? 'bg-emerald-500' : 'bg-indigo-500'}`}
                            style={{ width: `${Math.min(100, Math.max(2, v.percentage_of_total))}%` }}
                          />
                        </div>

                        {/* Sequence of activities */}
                        <div className="flex items-center gap-1.5 flex-wrap pt-1">
                          {v.activities.map((act, actIdx) => (
                            <div key={`${act}-${actIdx}`} className="flex items-center gap-1.5">
                              <span className="text-[11px] font-medium px-2.5 py-1 rounded-md bg-slate-800 text-slate-200 border border-slate-700">
                                {act}
                              </span>
                              {actIdx < v.activities.length - 1 && (
                                <svg className="w-3 h-3 text-slate-600 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                                </svg>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-12 text-slate-400 text-xs">
                    No process variants discovered yet. Reconstruct events to analyze execution pathways.
                  </div>
                )}
              </div>
            )}

            {/* 3. CASES EXPLORER */}
            {activeTab === 'cases' && (
              <div className="space-y-4">
                {casesData && casesData.items.length > 0 ? (
                  <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    {/* Case list table */}
                    <div className="lg:col-span-2 overflow-x-auto border border-slate-800 rounded-xl">
                      <table className="w-full text-left text-xs">
                        <thead className="bg-slate-950 text-slate-400 uppercase font-mono text-[10px]">
                          <tr>
                            <th className="px-3.5 py-2.5">Case ID</th>
                            <th className="px-3.5 py-2.5">Status</th>
                            <th className="px-3.5 py-2.5">Events</th>
                            <th className="px-3.5 py-2.5">Duration</th>
                            <th className="px-3.5 py-2.5">Started At</th>
                            <th className="px-3.5 py-2.5 text-right">Action</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800">
                          {casesData.items.map((c) => (
                            <tr
                              key={c.id}
                              className={`hover:bg-slate-800/40 transition-colors ${
                                selectedCaseDetail?.case.id === c.id ? 'bg-indigo-600/10' : ''
                              }`}
                            >
                              <td className="px-3.5 py-2.5 font-bold font-mono text-white">{c.case_identifier}</td>
                              <td className="px-3.5 py-2.5">
                                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                                  {c.status}
                                </span>
                              </td>
                              <td className="px-3.5 py-2.5 font-mono text-slate-300">{c.event_count}</td>
                              <td className="px-3.5 py-2.5 font-mono text-emerald-400 font-semibold">
                                {formatDuration(c.total_duration_seconds)}
                              </td>
                              <td className="px-3.5 py-2.5 text-slate-400 text-[11px]">
                                {new Date(c.started_at).toLocaleDateString()}
                              </td>
                              <td className="px-3.5 py-2.5 text-right">
                                <button
                                  type="button"
                                  onClick={() => handleInspectCase(c.id)}
                                  className="text-indigo-400 hover:text-indigo-300 font-semibold"
                                >
                                  Inspect
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>

                    {/* Case timeline inspector */}
                    <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-5 space-y-4">
                      <div className="text-xs font-bold text-white uppercase tracking-wider">
                        Case Timeline & Provenance
                      </div>
                      {selectedCaseDetail ? (
                        <div className="space-y-4 text-xs">
                          <div className="bg-slate-900 border border-slate-800 rounded-xl p-3.5 space-y-1 font-mono">
                            <div className="text-white font-bold text-sm">
                              {selectedCaseDetail.case.case_identifier}
                            </div>
                            <div className="text-slate-400 text-[11px]">
                              Variant: <span className="text-indigo-300">{selectedCaseDetail.case.variant_key}</span>
                            </div>
                            <div className="text-emerald-400 text-[11px]">
                              Duration: {formatDuration(selectedCaseDetail.case.total_duration_seconds)}
                            </div>
                          </div>

                          {/* Ordered events */}
                          <div className="space-y-3 relative before:absolute before:left-3 before:top-2 before:bottom-2 before:w-0.5 before:bg-slate-800">
                            {selectedCaseDetail.events.map((evt, idx) => (
                              <div key={evt.id} className="relative pl-7 space-y-1">
                                <span className="absolute left-2 top-1.5 w-2.5 h-2.5 rounded-full bg-indigo-500 ring-4 ring-slate-950 -translate-x-1/2" />
                                <div className="flex items-center justify-between">
                                  <span className="font-bold text-white text-xs">{evt.activity_name}</span>
                                  <span className="text-[10px] font-mono text-slate-500">#{idx + 1}</span>
                                </div>
                                <div className="text-[10px] font-mono text-slate-400">
                                  {new Date(evt.timestamp).toLocaleString()}
                                </div>
                                {(evt.resource || evt.source_system) && (
                                  <div className="text-[10px] text-slate-500">
                                    {evt.resource && <span>Resource: {evt.resource} </span>}
                                    {evt.source_system && <span className="font-mono">({evt.source_system})</span>}
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      ) : (
                        <div className="text-xs text-slate-500 italic p-6 text-center border border-dashed border-slate-800 rounded-xl">
                          Select a case from the table to trace its chronological milestone events and data provenance.
                        </div>
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="text-center py-12 text-slate-400 text-xs">
                    No cases mined yet.
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Create Process Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 w-full max-w-md shadow-2xl space-y-4">
            <h3 className="text-base font-bold text-white">Create Process Container</h3>
            <p className="text-xs text-slate-400">
              Configure a business process container for event log mining, SLA tracking, and bottleneck detection.
            </p>

            <form onSubmit={handleCreateProcess} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Process Name *</label>
                <input
                  type="text"
                  required
                  value={newProcName}
                  onChange={(e) => setNewProcName(e.target.value)}
                  placeholder="e.g. Procure-to-Pay Lifecycle"
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Description</label>
                <textarea
                  rows={2}
                  value={newProcDesc}
                  onChange={(e) => setNewProcDesc(e.target.value)}
                  placeholder="Optional operational process scope"
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  Target SLA Duration (Hours)
                </label>
                <input
                  type="number"
                  min="1"
                  step="1"
                  value={newProcTargetHours}
                  onChange={(e) => setNewProcTargetHours(e.target.value)}
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                />
                <span className="text-[10px] text-slate-500">Cases exceeding this duration will be marked as SLA breaches.</span>
              </div>

              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-3.5 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionLoading || !newProcName.trim()}
                  className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs font-semibold"
                >
                  {actionLoading ? 'Creating...' : 'Create Process'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
