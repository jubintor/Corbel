import { useState, useEffect, useCallback, type FormEvent } from 'react'
import { useAuth } from '../context/AuthContext'
import type { Project } from '../types/auth'
import type {
  Monitor,
  MonitorCreate,
  BusinessRuleCreate,
  Finding,
  FindingStatus,
  RuleSeverity,
  MonitorTargetType,
  RuleOperator,
  MonitorEvaluation,
} from '../types/monitors'
import {
  listMonitors,
  createMonitor,
  updateMonitor,
  deleteMonitor,
  addRule,
  deleteRule,
  evaluateMonitor,
  listFindings,
  updateFindingStatus,
  listEvaluations,
} from '../services/monitors'

interface MonitorsWorkspaceProps {
  project: Project
  onBack: () => void
  onNavigateToInvestigations?: () => void
}

export function MonitorsWorkspace({ project, onBack, onNavigateToInvestigations }: MonitorsWorkspaceProps) {
  const { token, activeOrg } = useAuth()

  // Navigation tab
  const [activeTab, setActiveTab] = useState<'monitors' | 'findings' | 'evaluations'>('monitors')

  // Data states
  const [monitors, setMonitors] = useState<Monitor[]>([])
  const [findings, setFindings] = useState<Finding[]>([])
  const [evaluations, setEvaluations] = useState<MonitorEvaluation[]>([])
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)
  const [actionMessage, setActionMessage] = useState<string | null>(null)

  // Filtering states for findings
  const [statusFilter, setStatusFilter] = useState<string>('ALL')
  const [severityFilter, setSeverityFilter] = useState<string>('ALL')
  const [selectedMonitorFilter, setSelectedMonitorFilter] = useState<string>('ALL')

  // Modal states
  const [showCreateMonitorModal, setShowCreateMonitorModal] = useState<boolean>(false)
  const [showAddRuleModal, setShowAddRuleModal] = useState<string | null>(null) // monitor_id
  const [selectedFinding, setSelectedFinding] = useState<Finding | null>(null)
  const [resolvingFinding, setResolvingFinding] = useState<Finding | null>(null)
  const [resolutionNotes, setResolutionNotes] = useState<string>('')
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false)

  // New Monitor Form
  const [newMonitorName, setNewMonitorName] = useState('')
  const [newMonitorDesc, setNewMonitorDesc] = useState('')
  const [newTargetType, setNewTargetType] = useState<MonitorTargetType>('ENTITY')
  const [newTargetId, setNewTargetId] = useState('PurchaseOrder')
  const [newRuleCode, setNewRuleCode] = useState('PO_VALUE_LIMIT')
  const [newRuleSeverity, setNewRuleSeverity] = useState<RuleSeverity>('HIGH')
  const [newRuleField, setNewRuleField] = useState('total_amount')
  const [newRuleOperator, setNewRuleOperator] = useState<RuleOperator>('gt')
  const [newRuleThreshold, setNewRuleThreshold] = useState('10000')

  // New Rule on existing monitor form
  const [addRuleCode, setAddRuleCode] = useState('')
  const [addRuleDesc, setAddRuleDesc] = useState('')
  const [addRuleSeverity, setAddRuleSeverity] = useState<RuleSeverity>('HIGH')
  const [addRuleType, setAddRuleType] = useState('THRESHOLD')
  const [addRuleField, setAddRuleField] = useState('')
  const [addRuleOperator, setAddRuleOperator] = useState<RuleOperator>('gt')
  const [addRuleThreshold, setAddRuleThreshold] = useState('')

  // ---------------------------------------------------------------------------
  // Data Loaders
  // ---------------------------------------------------------------------------

  const loadMonitors = useCallback(async () => {
    if (!token || !activeOrg) return
    try {
      const data = await listMonitors(token, activeOrg.id, project.id)
      setMonitors(data)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load operational monitors')
    }
  }, [token, activeOrg, project.id])

  const loadFindings = useCallback(async () => {
    if (!token || !activeOrg) return
    try {
      const data = await listFindings(token, activeOrg.id, project.id, {
        status: statusFilter !== 'ALL' ? (statusFilter as FindingStatus) : undefined,
        severity: severityFilter !== 'ALL' ? (severityFilter as RuleSeverity) : undefined,
        monitorId: selectedMonitorFilter !== 'ALL' ? selectedMonitorFilter : undefined,
        limit: 100,
      })
      setFindings(data)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load exception findings')
    }
  }, [token, activeOrg, project.id, statusFilter, severityFilter, selectedMonitorFilter])

  const loadEvaluations = useCallback(async () => {
    if (!token || !activeOrg) return
    try {
      const data = await listEvaluations(token, activeOrg.id, project.id, undefined, 50)
      setEvaluations(data)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load evaluation history')
    }
  }, [token, activeOrg, project.id])

  const refreshAll = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      await Promise.all([loadMonitors(), loadFindings(), loadEvaluations()])
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to refresh monitors workspace')
    } finally {
      setLoading(false)
    }
  }, [loadMonitors, loadFindings, loadEvaluations])

  useEffect(() => {
    void refreshAll()
  }, [refreshAll])

  // ---------------------------------------------------------------------------
  // Monitor Actions
  // ---------------------------------------------------------------------------

  const handleCreateMonitor = async (e: FormEvent) => {
    e.preventDefault()
    if (!token || !activeOrg) return
    setIsSubmitting(true)
    setError(null)

    try {
      const req: MonitorCreate = {
        name: newMonitorName.trim(),
        description: newMonitorDesc.trim() || undefined,
        target_type: newTargetType,
        target_id: newTargetId.trim(),
        status: 'ACTIVE',
        rules: [
          {
            rule_code: newRuleCode.trim().toUpperCase(),
            description: 'Configured threshold condition',
            severity: newRuleSeverity,
            rule_type: 'THRESHOLD',
            field_name: newRuleField.trim(),
            operator: newRuleOperator,
            threshold_value: newRuleThreshold ? parseFloat(newRuleThreshold) : undefined,
          },
        ],
      }

      await createMonitor(token, activeOrg.id, project.id, req)
      setShowCreateMonitorModal(false)
      setActionMessage(`Created monitor "${newMonitorName}" successfully.`)
      // Reset form
      setNewMonitorName('')
      setNewMonitorDesc('')
      await loadMonitors()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to create monitor')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleToggleMonitorStatus = async (monitor: Monitor) => {
    if (!token || !activeOrg) return
    const nextStatus = monitor.status === 'ACTIVE' ? 'PAUSED' : 'ACTIVE'
    try {
      await updateMonitor(token, activeOrg.id, project.id, monitor.id, { status: nextStatus })
      setActionMessage(`Monitor status changed to ${nextStatus}.`)
      await loadMonitors()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to update monitor status')
    }
  }

  const handleDeleteMonitor = async (monitor: Monitor) => {
    if (!token || !activeOrg) return
    if (!window.confirm(`Delete monitor "${monitor.name}" and its evaluation records?`)) return
    try {
      await deleteMonitor(token, activeOrg.id, project.id, monitor.id)
      setActionMessage(`Deleted monitor "${monitor.name}".`)
      await refreshAll()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to delete monitor')
    }
  }

  const handleEvaluate = async (monitorId: string) => {
    if (!token || !activeOrg) return
    setIsSubmitting(true)
    setError(null)
    try {
      const res = await evaluateMonitor(token, activeOrg.id, project.id, monitorId)
      setActionMessage(
        `Evaluation run completed: ${res.records_evaluated} records scanned, ${res.findings_detected} findings detected.`
      )
      await refreshAll()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Evaluation run failed')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleAddRule = async (e: FormEvent) => {
    e.preventDefault()
    if (!token || !activeOrg || !showAddRuleModal) return
    setIsSubmitting(true)
    try {
      const req: BusinessRuleCreate = {
        rule_code: addRuleCode.trim().toUpperCase(),
        description: addRuleDesc.trim() || undefined,
        severity: addRuleSeverity,
        rule_type: addRuleType,
        field_name: addRuleField.trim(),
        operator: addRuleOperator,
        threshold_value: addRuleThreshold ? parseFloat(addRuleThreshold) : undefined,
      }
      await addRule(token, activeOrg.id, project.id, showAddRuleModal, req)
      setShowAddRuleModal(null)
      setAddRuleCode('')
      setAddRuleDesc('')
      setAddRuleField('')
      setAddRuleThreshold('')
      setActionMessage('Added business rule to monitor.')
      await loadMonitors()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to add rule')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleDeleteRule = async (monitorId: string, ruleId: string) => {
    if (!token || !activeOrg) return
    if (!window.confirm('Are you sure you want to delete this business rule?')) return
    try {
      await deleteRule(token, activeOrg.id, project.id, monitorId, ruleId)
      setActionMessage('Rule removed successfully.')
      await loadMonitors()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to delete rule')
    }
  }

  // ---------------------------------------------------------------------------
  // Finding Actions
  // ---------------------------------------------------------------------------

  const handleAcknowledgeFinding = async (finding: Finding) => {
    if (!token || !activeOrg) return
    try {
      await updateFindingStatus(token, activeOrg.id, project.id, finding.id, {
        status: 'ACKNOWLEDGED',
      })
      setActionMessage(`Exception finding "${finding.entity_id}" acknowledged.`)
      await refreshAll()
      if (selectedFinding?.id === finding.id) {
        setSelectedFinding({ ...finding, status: 'ACKNOWLEDGED' })
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to acknowledge finding')
    }
  }

  const handleResolveFinding = async (e: FormEvent) => {
    e.preventDefault()
    if (!token || !activeOrg || !resolvingFinding) return
    setIsSubmitting(true)
    try {
      await updateFindingStatus(token, activeOrg.id, project.id, resolvingFinding.id, {
        status: 'RESOLVED',
        resolution_notes: resolutionNotes.trim() || undefined,
      })
      setActionMessage(`Exception finding resolved with audit note.`)
      setResolvingFinding(null)
      setResolutionNotes('')
      await refreshAll()
      if (selectedFinding?.id === resolvingFinding.id) {
        setSelectedFinding(null)
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to resolve finding')
    } finally {
      setIsSubmitting(false)
    }
  }

  // ---------------------------------------------------------------------------
  // Render Helpers
  // ---------------------------------------------------------------------------

  const severityBadge = (severity: RuleSeverity) => {
    switch (severity) {
      case 'CRITICAL':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/30">
            CRITICAL
          </span>
        )
      case 'HIGH':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">
            HIGH
          </span>
        )
      case 'MEDIUM':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-blue-500/20 text-blue-300 border border-blue-500/30">
            MEDIUM
          </span>
        )
      default:
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-500/20 text-slate-300 border border-slate-500/30">
            LOW
          </span>
        )
    }
  }

  const statusBadge = (status: FindingStatus) => {
    switch (status) {
      case 'OPEN':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/30">
            OPEN
          </span>
        )
      case 'ACKNOWLEDGED':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">
            ACKNOWLEDGED
          </span>
        )
      case 'RESOLVED':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
            RESOLVED
          </span>
        )
      case 'DISMISSED':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-500/20 text-slate-400 border border-slate-500/30">
            DISMISSED
          </span>
        )
      default:
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
            {status}
          </span>
        )
    }
  }

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <button
              onClick={onBack}
              className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors"
              aria-label="Back to Projects"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
              </svg>
            </button>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-xl font-bold text-white">Adaptive Monitors & Exception Detection</h2>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  Phase 7 Deterministic
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-1">
                Configurable threshold monitors, factual evidence capture, and human exception governance for{' '}
                <span className="text-slate-300 font-semibold">{project.name}</span>.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowCreateMonitorModal(true)}
              className="px-3.5 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold rounded-lg transition-colors shadow-lg shadow-indigo-600/20 flex items-center gap-1.5"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              <span>New Monitor</span>
            </button>
            <button
              onClick={refreshAll}
              disabled={loading}
              className="px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold rounded-lg transition-colors flex items-center gap-1.5"
            >
              <svg className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              <span>Refresh</span>
            </button>
          </div>
        </div>

        {/* Tab Selector */}
        <div className="flex border-b border-slate-800 gap-6 text-xs font-semibold">
          <button
            onClick={() => setActiveTab('monitors')}
            className={`pb-3 transition-colors flex items-center gap-2 ${
              activeTab === 'monitors'
                ? 'text-indigo-400 border-b-2 border-indigo-500'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <span>Configured Monitors</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 font-mono">
              {monitors.length}
            </span>
          </button>
          <button
            onClick={() => setActiveTab('findings')}
            className={`pb-3 transition-colors flex items-center gap-2 ${
              activeTab === 'findings'
                ? 'text-indigo-400 border-b-2 border-indigo-500'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <span>Operational Exceptions & Findings</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-rose-500/20 text-rose-300 font-mono">
              {findings.filter((f) => f.status === 'OPEN').length} Open
            </span>
          </button>
          <button
            onClick={() => setActiveTab('evaluations')}
            className={`pb-3 transition-colors flex items-center gap-2 ${
              activeTab === 'evaluations'
                ? 'text-indigo-400 border-b-2 border-indigo-500'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <span>Evaluation Run Audit</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 font-mono">
              {evaluations.length}
            </span>
          </button>
        </div>

        {/* Action / Error Banner */}
        {actionMessage && (
          <div className="p-3 bg-emerald-950/60 border border-emerald-800/80 rounded-lg text-emerald-300 text-xs flex justify-between items-center">
            <span>{actionMessage}</span>
            <button onClick={() => setActionMessage(null)} className="text-emerald-400 hover:text-white text-xs">
              &times;
            </button>
          </div>
        )}
        {error && (
          <div className="p-3 bg-rose-950/60 border border-rose-800/80 rounded-lg text-rose-200 text-xs flex justify-between items-center">
            <span>{error}</span>
            <button onClick={() => setError(null)} className="text-rose-400 hover:text-white text-xs">
              &times;
            </button>
          </div>
        )}
      </div>

      {/* TAB 1: Configured Monitors */}
      {activeTab === 'monitors' && (
        <div className="space-y-4">
          {monitors.length === 0 ? (
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-12 text-center text-slate-400">
              <svg className="w-12 h-12 mx-auto text-slate-600 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
              <h3 className="text-base font-semibold text-slate-200 mb-1">No Operational Monitors Configured</h3>
              <p className="text-xs text-slate-500 max-w-md mx-auto mb-4">
                Define deterministic threshold rules targeting purchase orders, invoices, or process clearance SLAs.
              </p>
              <button
                onClick={() => setShowCreateMonitorModal(true)}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold rounded-lg transition-colors"
              >
                Create First Monitor
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4">
              {monitors.map((m) => (
                <div key={m.id} className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg space-y-4">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b border-slate-800">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-base font-bold text-white">{m.name}</span>
                        <span
                          className={`text-[10px] font-mono px-2 py-0.5 rounded font-semibold ${
                            m.status === 'ACTIVE'
                              ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                              : 'bg-slate-700/40 text-slate-400 border border-slate-600/30'
                          }`}
                        >
                          {m.status}
                        </span>
                        <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-300 border border-indigo-500/20">
                          Target: {m.target_type} ({m.target_id})
                        </span>
                      </div>
                      <p className="text-xs text-slate-400 mt-1">{m.description || 'No description provided.'}</p>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      <button
                        onClick={() => handleEvaluate(m.id)}
                        disabled={isSubmitting || m.status !== 'ACTIVE'}
                        className="px-3 py-1.5 bg-indigo-600/20 hover:bg-indigo-600/40 text-indigo-300 text-xs font-semibold rounded-lg transition-colors disabled:opacity-40 flex items-center gap-1.5 border border-indigo-500/30"
                      >
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        <span>Evaluate Now</span>
                      </button>

                      <button
                        onClick={() => handleToggleMonitorStatus(m)}
                        className="px-2.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold rounded-lg transition-colors"
                      >
                        {m.status === 'ACTIVE' ? 'Pause' : 'Activate'}
                      </button>

                      <button
                        onClick={() => setShowAddRuleModal(m.id)}
                        className="px-2.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold rounded-lg transition-colors"
                      >
                        + Rule
                      </button>

                      <button
                        onClick={() => handleDeleteMonitor(m)}
                        className="p-1.5 text-rose-400 hover:text-rose-300 hover:bg-rose-950/40 rounded-lg transition-colors"
                        aria-label="Delete Monitor"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                      </button>
                    </div>
                  </div>

                  {/* Rules list */}
                  <div className="space-y-2">
                    <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">
                      Business Rules ({m.rules.length})
                    </div>
                    {m.rules.length === 0 ? (
                      <div className="text-xs text-slate-500 italic">No business rules defined on this monitor.</div>
                    ) : (
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                        {m.rules.map((r) => (
                          <div
                            key={r.id}
                            className="p-3 bg-slate-950 border border-slate-800/80 rounded-lg text-xs space-y-1.5 relative group"
                          >
                            <div className="flex items-center justify-between">
                              <span className="font-mono font-bold text-slate-200">{r.rule_code}</span>
                              <div className="flex items-center gap-2">
                                {severityBadge(r.severity)}
                                <button
                                  onClick={() => handleDeleteRule(m.id, r.id)}
                                  className="text-slate-500 hover:text-rose-400 text-xs"
                                  title="Delete Rule"
                                >
                                  &times;
                                </button>
                              </div>
                            </div>
                            <div className="text-slate-400 text-[11px]">{r.description || 'Threshold rule'}</div>
                            <div className="font-mono text-[11px] text-indigo-300 bg-slate-900 px-2 py-0.5 rounded border border-slate-800 inline-block">
                              {r.field_name} {r.operator} {r.threshold_value ?? r.threshold_string ?? r.secondary_field}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Findings counts badge */}
                  <div className="pt-2 flex items-center justify-between text-xs text-slate-400 border-t border-slate-800/60">
                    <div className="flex items-center gap-4">
                      <span>
                        Open Findings:{' '}
                        <strong className="text-rose-400">{m.open_findings_count}</strong>
                      </span>
                      <span>
                        Total Detected: <strong>{m.total_findings_count}</strong>
                      </span>
                      {m.last_run_at && (
                        <span>
                          Last Evaluated:{' '}
                          <span className="text-slate-300">{new Date(m.last_run_at).toLocaleString()}</span>
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* TAB 2: Operational Exceptions & Findings */}
      {activeTab === 'findings' && (
        <div className="space-y-4">
          {/* Filters Bar */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-wrap items-center justify-between gap-4">
            <div className="flex flex-wrap items-center gap-3 text-xs">
              <div>
                <label className="text-slate-400 block mb-1 font-medium">Status</label>
                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  className="bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-slate-200 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500"
                >
                  <option value="ALL">All Statuses</option>
                  <option value="OPEN">Open</option>
                  <option value="ACKNOWLEDGED">Acknowledged</option>
                  <option value="RESOLVED">Resolved</option>
                  <option value="DISMISSED">Dismissed</option>
                </select>
              </div>

              <div>
                <label className="text-slate-400 block mb-1 font-medium">Severity</label>
                <select
                  value={severityFilter}
                  onChange={(e) => setSeverityFilter(e.target.value)}
                  className="bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-slate-200 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500"
                >
                  <option value="ALL">All Severities</option>
                  <option value="CRITICAL">Critical</option>
                  <option value="HIGH">High</option>
                  <option value="MEDIUM">Medium</option>
                  <option value="LOW">Low</option>
                </select>
              </div>

              <div>
                <label className="text-slate-400 block mb-1 font-medium">Monitor Filter</label>
                <select
                  value={selectedMonitorFilter}
                  onChange={(e) => setSelectedMonitorFilter(e.target.value)}
                  className="bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-slate-200 text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500"
                >
                  <option value="ALL">All Monitors</option>
                  {monitors.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="text-xs text-slate-400">
              Showing <strong className="text-white">{findings.length}</strong> findings
            </div>
          </div>

          {/* Findings Table */}
          {findings.length === 0 ? (
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-12 text-center text-slate-400">
              <svg className="w-12 h-12 mx-auto text-emerald-500/40 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <h3 className="text-base font-semibold text-slate-200 mb-1">No Exception Findings</h3>
              <p className="text-xs text-slate-500 max-w-md mx-auto">
                No active operational threshold violations match your selected filters. Run monitor evaluation to check new records.
              </p>
            </div>
          ) : (
            <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-lg">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs text-slate-300">
                  <thead className="bg-slate-950/80 border-b border-slate-800 text-[11px] uppercase font-bold text-slate-400">
                    <tr>
                      <th className="p-3.5">Severity</th>
                      <th className="p-3.5">Entity / Case</th>
                      <th className="p-3.5">Summary</th>
                      <th className="p-3.5">Observed vs Threshold</th>
                      <th className="p-3.5">Status</th>
                      <th className="p-3.5">Detected</th>
                      <th className="p-3.5 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 font-medium">
                    {findings.map((f) => (
                      <tr key={f.id} className="hover:bg-slate-800/30 transition-colors">
                        <td className="p-3.5">{severityBadge(f.severity)}</td>
                        <td className="p-3.5">
                          <div className="font-mono font-bold text-white">{f.entity_id}</div>
                          <div className="text-[10px] text-slate-500">{f.entity_type}</div>
                        </td>
                        <td className="p-3.5 max-w-xs truncate" title={f.summary}>
                          {f.summary}
                        </td>
                        <td className="p-3.5 font-mono text-[11px]">
                          <span className="text-rose-400">{f.observed_value ?? 'N/A'}</span>
                          <span className="text-slate-500 mx-1">/</span>
                          <span className="text-slate-400">{f.threshold_value ?? 'N/A'}</span>
                        </td>
                        <td className="p-3.5">{statusBadge(f.status)}</td>
                        <td className="p-3.5 text-slate-400 text-[11px]">
                          {new Date(f.detected_at).toLocaleDateString()}
                        </td>
                        <td className="p-3.5 text-right space-x-2">
                          <button
                            onClick={() => setSelectedFinding(f)}
                            className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 text-[11px] rounded transition-colors"
                          >
                            Details
                          </button>
                          {onNavigateToInvestigations && (
                            <button
                              onClick={() => onNavigateToInvestigations()}
                              className="px-2.5 py-1 bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-300 text-[11px] font-semibold rounded transition-colors"
                              title="Investigate with RAG & Governed Actions"
                            >
                              Investigate
                            </button>
                          )}
                          {f.status === 'OPEN' && (
                            <button
                              onClick={() => handleAcknowledgeFinding(f)}
                              className="px-2.5 py-1 bg-amber-600/20 hover:bg-amber-600/30 text-amber-300 text-[11px] rounded transition-colors"
                            >
                              Ack
                            </button>
                          )}
                          {(f.status === 'OPEN' || f.status === 'ACKNOWLEDGED') && (
                            <button
                              onClick={() => {
                                setResolvingFinding(f)
                                setResolutionNotes('')
                              }}
                              className="px-2.5 py-1 bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 text-[11px] rounded transition-colors"
                            >
                              Resolve
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* TAB 3: Evaluation Run History Audit */}
      {activeTab === 'evaluations' && (
        <div className="space-y-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-lg">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-slate-300">
                <thead className="bg-slate-950/80 border-b border-slate-800 text-[11px] uppercase font-bold text-slate-400">
                  <tr>
                    <th className="p-3.5">Evaluated At</th>
                    <th className="p-3.5">Status</th>
                    <th className="p-3.5">Records Scanned</th>
                    <th className="p-3.5">Findings Emitted</th>
                    <th className="p-3.5">Duration</th>
                    <th className="p-3.5">Summary Facts</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-medium">
                  {evaluations.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="p-8 text-center text-slate-500 italic">
                        No evaluation runs recorded. Trigger monitor evaluation to generate audit logs.
                      </td>
                    </tr>
                  ) : (
                    evaluations.map((ev) => (
                      <tr key={ev.id} className="hover:bg-slate-800/30 transition-colors">
                        <td className="p-3.5 font-mono text-[11px]">
                          {new Date(ev.evaluated_at).toLocaleString()}
                        </td>
                        <td className="p-3.5">
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-bold font-mono ${
                              ev.status === 'SUCCESS'
                                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                                : 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                            }`}
                          >
                            {ev.status}
                          </span>
                        </td>
                        <td className="p-3.5 font-mono">{ev.records_evaluated}</td>
                        <td className="p-3.5 font-mono">
                          <span className={ev.findings_detected > 0 ? 'text-amber-400 font-bold' : 'text-slate-400'}>
                            {ev.findings_detected}
                          </span>
                        </td>
                        <td className="p-3.5 font-mono text-slate-400">{ev.execution_duration_ms.toFixed(1)} ms</td>
                        <td className="p-3.5 font-mono text-[10px] text-slate-400 truncate max-w-xs">
                          {ev.summary_json ? JSON.stringify(ev.summary_json) : '-'}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* MODAL 1: Create Monitor Modal */}
      {showCreateMonitorModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
          <div className="relative w-full max-w-lg bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl p-6 text-slate-100 max-h-[90vh] overflow-y-auto">
            <button
              onClick={() => setShowCreateMonitorModal(false)}
              className="absolute top-4 right-4 text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors"
            >
              &times;
            </button>
            <h3 className="text-lg font-bold text-white mb-1">Create Operational Monitor</h3>
            <p className="text-xs text-slate-400 mb-4">
              Configure deterministic threshold rules for business objects or operational processes.
            </p>

            <form onSubmit={handleCreateMonitor} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">Monitor Name</label>
                <input
                  type="text"
                  required
                  value={newMonitorName}
                  onChange={(e) => setNewMonitorName(e.target.value)}
                  placeholder="e.g. High Value Purchase Order Monitor"
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">Description (Optional)</label>
                <input
                  type="text"
                  value={newMonitorDesc}
                  onChange={(e) => setNewMonitorDesc(e.target.value)}
                  placeholder="e.g. Evaluates PO totals against spending threshold"
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">Target Type</label>
                  <select
                    value={newTargetType}
                    onChange={(e) => setNewTargetType(e.target.value as MonitorTargetType)}
                    className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  >
                    <option value="ENTITY">Entity (Dataset / Business Object)</option>
                    <option value="PROCESS">Process (SLA / Cycle Time)</option>
                    <option value="SYSTEM">System Operational</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">Target Identifier</label>
                  <input
                    type="text"
                    required
                    value={newTargetId}
                    onChange={(e) => setNewTargetId(e.target.value)}
                    placeholder="e.g. PurchaseOrder or Process ID"
                    className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
              </div>

              <div className="p-3 bg-slate-950 border border-slate-800 rounded-xl space-y-3">
                <div className="text-xs font-bold text-indigo-400 uppercase tracking-wider">
                  Initial Business Rule
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-[11px] text-slate-400 mb-1">Rule Code</label>
                    <input
                      type="text"
                      required
                      value={newRuleCode}
                      onChange={(e) => setNewRuleCode(e.target.value)}
                      placeholder="PO_10K_LIMIT"
                      className="w-full px-2.5 py-1.5 bg-slate-900 border border-slate-700 rounded text-xs font-mono text-slate-100"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] text-slate-400 mb-1">Severity</label>
                    <select
                      value={newRuleSeverity}
                      onChange={(e) => setNewRuleSeverity(e.target.value as RuleSeverity)}
                      className="w-full px-2.5 py-1.5 bg-slate-900 border border-slate-700 rounded text-xs text-slate-100"
                    >
                      <option value="LOW">Low</option>
                      <option value="MEDIUM">Medium</option>
                      <option value="HIGH">High</option>
                      <option value="CRITICAL">Critical</option>
                    </select>
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <label className="block text-[11px] text-slate-400 mb-1">Field Name</label>
                    <input
                      type="text"
                      required
                      value={newRuleField}
                      onChange={(e) => setNewRuleField(e.target.value)}
                      placeholder="total_amount"
                      className="w-full px-2.5 py-1.5 bg-slate-900 border border-slate-700 rounded text-xs font-mono text-slate-100"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] text-slate-400 mb-1">Operator</label>
                    <select
                      value={newRuleOperator}
                      onChange={(e) => setNewRuleOperator(e.target.value as RuleOperator)}
                      className="w-full px-2.5 py-1.5 bg-slate-900 border border-slate-700 rounded text-xs text-slate-100"
                    >
                      <option value="gt">&gt; (Greater than)</option>
                      <option value="gte">&gt;= (Greater or eq)</option>
                      <option value="lt">&lt; (Less than)</option>
                      <option value="lte">&lt;= (Less or eq)</option>
                      <option value="eq">= (Equal)</option>
                      <option value="neq">!= (Not equal)</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-[11px] text-slate-400 mb-1">Threshold</label>
                    <input
                      type="number"
                      step="any"
                      required
                      value={newRuleThreshold}
                      onChange={(e) => setNewRuleThreshold(e.target.value)}
                      placeholder="10000"
                      className="w-full px-2.5 py-1.5 bg-slate-900 border border-slate-700 rounded text-xs font-mono text-slate-100"
                    />
                  </div>
                </div>
              </div>

              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreateMonitorModal(false)}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs font-semibold rounded-lg transition-colors"
                >
                  {isSubmitting ? 'Creating...' : 'Create Monitor'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 2: Add Rule Modal */}
      {showAddRuleModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
          <div className="relative w-full max-w-md bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl p-6 text-slate-100">
            <button
              onClick={() => setShowAddRuleModal(null)}
              className="absolute top-4 right-4 text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors"
            >
              &times;
            </button>
            <h3 className="text-lg font-bold text-white mb-1">Add Business Rule</h3>
            <p className="text-xs text-slate-400 mb-4">Add a new deterministic threshold condition to this monitor.</p>

            <form onSubmit={handleAddRule} className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">Rule Code</label>
                <input
                  type="text"
                  required
                  value={addRuleCode}
                  onChange={(e) => setAddRuleCode(e.target.value)}
                  placeholder="PRICE_VARIANCE_20"
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-xs font-mono text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">Description</label>
                <input
                  type="text"
                  value={addRuleDesc}
                  onChange={(e) => setAddRuleDesc(e.target.value)}
                  placeholder="Unit price exceeds 20% baseline"
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-xs text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">Severity</label>
                  <select
                    value={addRuleSeverity}
                    onChange={(e) => setAddRuleSeverity(e.target.value as RuleSeverity)}
                    className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-xs text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  >
                    <option value="LOW">Low</option>
                    <option value="MEDIUM">Medium</option>
                    <option value="HIGH">High</option>
                    <option value="CRITICAL">Critical</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">Rule Type</label>
                  <input
                    type="text"
                    value={addRuleType}
                    onChange={(e) => setAddRuleType(e.target.value)}
                    placeholder="THRESHOLD"
                    className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-xs text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="block text-[11px] text-slate-400 mb-1">Field Name</label>
                  <input
                    type="text"
                    required
                    value={addRuleField}
                    onChange={(e) => setAddRuleField(e.target.value)}
                    placeholder="unit_price"
                    className="w-full px-2.5 py-1.5 bg-slate-950 border border-slate-700 rounded text-xs font-mono text-slate-100"
                  />
                </div>
                <div>
                  <label className="block text-[11px] text-slate-400 mb-1">Operator</label>
                  <select
                    value={addRuleOperator}
                    onChange={(e) => setAddRuleOperator(e.target.value as RuleOperator)}
                    className="w-full px-2.5 py-1.5 bg-slate-950 border border-slate-700 rounded text-xs text-slate-100"
                  >
                    <option value="gt">&gt;</option>
                    <option value="gte">&gt;=</option>
                    <option value="lt">&lt;</option>
                    <option value="lte">&lt;=</option>
                    <option value="eq">=</option>
                    <option value="neq">!=</option>
                  </select>
                </div>
                <div>
                  <label className="block text-[11px] text-slate-400 mb-1">Threshold</label>
                  <input
                    type="number"
                    step="any"
                    required
                    value={addRuleThreshold}
                    onChange={(e) => setAddRuleThreshold(e.target.value)}
                    placeholder="100.0"
                    className="w-full px-2.5 py-1.5 bg-slate-950 border border-slate-700 rounded text-xs font-mono text-slate-100"
                  />
                </div>
              </div>

              <div className="flex justify-end gap-3 pt-3">
                <button
                  type="button"
                  onClick={() => setShowAddRuleModal(null)}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs font-semibold rounded-lg transition-colors"
                >
                  {isSubmitting ? 'Adding...' : 'Add Rule'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 3: Finding Detail Modal */}
      {selectedFinding && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
          <div className="relative w-full max-w-xl bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl p-6 text-slate-100 max-h-[90vh] overflow-y-auto space-y-4">
            <button
              onClick={() => setSelectedFinding(null)}
              className="absolute top-4 right-4 text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors"
            >
              &times;
            </button>

            <div className="flex items-center gap-2">
              <span className="text-lg font-bold text-white">Exception Finding Details</span>
              {severityBadge(selectedFinding.severity)}
              {statusBadge(selectedFinding.status)}
            </div>

            <p className="text-xs text-slate-300 bg-slate-950 p-3 rounded-lg border border-slate-800">
              {selectedFinding.summary}
            </p>

            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="p-3 bg-slate-950 rounded-lg border border-slate-800">
                <span className="text-slate-500 block text-[10px] uppercase font-bold">Target Entity</span>
                <span className="font-mono text-slate-200">
                  {selectedFinding.entity_type}: {selectedFinding.entity_id}
                </span>
              </div>
              <div className="p-3 bg-slate-950 rounded-lg border border-slate-800">
                <span className="text-slate-500 block text-[10px] uppercase font-bold">Threshold Comparison</span>
                <span className="font-mono text-rose-400 font-bold">{selectedFinding.observed_value}</span>
                <span className="text-slate-500 mx-1">vs</span>
                <span className="font-mono text-slate-300">{selectedFinding.threshold_value}</span>
              </div>
            </div>

            {/* Deduplication Hash Audit */}
            <div className="p-3 bg-slate-950 rounded-lg border border-slate-800 text-xs">
              <span className="text-slate-500 block text-[10px] uppercase font-bold mb-1">
                Deterministic Deduplication Key Hash
              </span>
              <code className="text-[10px] font-mono text-indigo-300 break-all">
                {selectedFinding.deduplication_hash}
              </code>
            </div>

            {/* Verified Context JSON */}
            {selectedFinding.verified_context_json && (
              <div className="space-y-1">
                <span className="text-[10px] uppercase font-bold text-slate-400">Verified Factual Context</span>
                <pre className="p-3 bg-slate-950 rounded-lg border border-slate-800 text-[11px] font-mono text-slate-300 overflow-x-auto max-h-48">
                  {JSON.stringify(selectedFinding.verified_context_json, null, 2)}
                </pre>
              </div>
            )}

            {/* Resolution Details */}
            {selectedFinding.resolution_notes && (
              <div className="p-3 bg-emerald-950/40 border border-emerald-800/40 rounded-lg text-xs space-y-1">
                <span className="text-[10px] uppercase font-bold text-emerald-400">Resolution Notes</span>
                <p className="text-emerald-200">{selectedFinding.resolution_notes}</p>
                {selectedFinding.resolved_at && (
                  <div className="text-[10px] text-emerald-400/80">
                    Resolved at: {new Date(selectedFinding.resolved_at).toLocaleString()}
                  </div>
                )}
              </div>
            )}

            {/* Actions */}
            <div className="flex justify-end gap-3 pt-2 border-t border-slate-800">
              <button
                type="button"
                onClick={() => setSelectedFinding(null)}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold rounded-lg transition-colors"
              >
                Close
              </button>
              {selectedFinding.status === 'OPEN' && (
                <button
                  type="button"
                  onClick={() => handleAcknowledgeFinding(selectedFinding)}
                  className="px-4 py-2 bg-amber-600 hover:bg-amber-500 text-white text-xs font-semibold rounded-lg transition-colors"
                >
                  Acknowledge Exception
                </button>
              )}
              {(selectedFinding.status === 'OPEN' || selectedFinding.status === 'ACKNOWLEDGED') && (
                <button
                  type="button"
                  onClick={() => {
                    setResolvingFinding(selectedFinding)
                    setResolutionNotes('')
                  }}
                  className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold rounded-lg transition-colors"
                >
                  Resolve Exception
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* MODAL 4: Resolve Finding Modal with Audit Notes */}
      {resolvingFinding && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
          <div className="relative w-full max-w-md bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl p-6 text-slate-100">
            <button
              onClick={() => setResolvingFinding(null)}
              className="absolute top-4 right-4 text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors"
            >
              &times;
            </button>
            <h3 className="text-lg font-bold text-white mb-1">Resolve Operational Exception</h3>
            <p className="text-xs text-slate-400 mb-3">
              Record governance sign-off and explanation for closing exception on{' '}
              <strong className="text-slate-200">{resolvingFinding.entity_id}</strong>.
            </p>

            <form onSubmit={handleResolveFinding} className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">Resolution Notes / Reason</label>
                <textarea
                  rows={3}
                  required
                  value={resolutionNotes}
                  onChange={(e) => setResolutionNotes(e.target.value)}
                  placeholder="e.g. Price variance verified against approved volume amendment contract."
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setResolvingFinding(null)}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-xs font-semibold rounded-lg transition-colors"
                >
                  {isSubmitting ? 'Resolving...' : 'Confirm Resolution'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
