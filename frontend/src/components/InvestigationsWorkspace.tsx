import { useState, useEffect, useCallback, type FormEvent } from 'react'
import { useAuth } from '../context/AuthContext'
import type { Project } from '../types/auth'
import type {
  Investigation,
  Document as RAGDocument,
  Approval,
  Action,
  AuditEvent,
  P2PVerticalSliceDemoResponse,
  DocumentQueryResultItem,
} from '../types/governance'
import {
  listInvestigations,
  getInvestigation,
  listDocuments,
  ingestDocument,
  queryDocuments,
  listApprovals,
  decideApproval,
  listActions,
  executeAction,
  listAuditEvents,
  runP2PDemoSlice,
} from '../services/governance'
import { AuthApiError } from '../services/auth'

interface InvestigationsWorkspaceProps {
  project: Project
  onBack: () => void
}

type TabType = 'investigations' | 'approvals' | 'actions' | 'rag' | 'audit' | 'demo'

export function InvestigationsWorkspace({ project, onBack }: InvestigationsWorkspaceProps) {
  const { token, activeOrg } = useAuth()
  const [activeTab, setActiveTab] = useState<TabType>('investigations')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [actionMessage, setActionMessage] = useState<string | null>(null)

  // Investigations state
  const [investigations, setInvestigations] = useState<Investigation[]>([])
  const [selectedInvestigation, setSelectedInvestigation] = useState<Investigation | null>(null)

  // Approvals state
  const [approvals, setApprovals] = useState<Approval[]>([])
  const [selectedApproval, setSelectedApproval] = useState<Approval | null>(null)
  const [approvalRationale, setApprovalRationale] = useState('')
  const [approvalLoading, setApprovalLoading] = useState(false)

  // Actions state
  const [actions, setActions] = useState<Action[]>([])
  const [executingActionId, setExecutingActionId] = useState<string | null>(null)

  // RAG Documents state
  const [documents, setDocuments] = useState<RAGDocument[]>([])
  const [showIngestModal, setShowIngestModal] = useState(false)
  const [docTitle, setDocTitle] = useState('')
  const [docType, setDocType] = useState<'CONTRACT' | 'POLICY' | 'INVOICE'>('CONTRACT')
  const [docFileName, setDocFileName] = useState('')
  const [docRawText, setDocRawText] = useState('')
  const [docIngestLoading, setDocIngestLoading] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<DocumentQueryResultItem[]>([])
  const [searching, setSearching] = useState(false)

  // Audit state
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([])

  // P2P Demo Slice state
  const [demoLoading, setDemoLoading] = useState(false)
  const [demoResult, setDemoResult] = useState<P2PVerticalSliceDemoResponse | null>(null)
  const [demoSupplier, setDemoSupplier] = useState('Apex Industrial Supplies')
  const [demoPoNumber, setDemoPoNumber] = useState('PO-10023')
  const [demoPoAmount, setDemoPoAmount] = useState('15000.00')
  const [demoInvoiceNumber, setDemoInvoiceNumber] = useState('INV-7844')
  const [demoInvoiceAmount, setDemoInvoiceAmount] = useState('16250.00')
  const [demoVariance, setDemoVariance] = useState('1250.00')
  const [demoAutoApprove, setDemoAutoApprove] = useState(true)

  const loadData = useCallback(async () => {
    if (!token || !activeOrg) return
    setLoading(true)
    setError(null)
    try {
      if (activeTab === 'investigations') {
        const invRes = await listInvestigations(token, activeOrg.id, project.id)
        setInvestigations(invRes.items)
      } else if (activeTab === 'approvals') {
        const apprRes = await listApprovals(token, activeOrg.id, project.id)
        setApprovals(apprRes)
      } else if (activeTab === 'actions') {
        const actRes = await listActions(token, activeOrg.id, project.id)
        setActions(actRes)
      } else if (activeTab === 'rag') {
        const docRes = await listDocuments(token, activeOrg.id, project.id)
        setDocuments(docRes)
      } else if (activeTab === 'audit') {
        const auditRes = await listAuditEvents(token, activeOrg.id, project.id)
        setAuditEvents(auditRes.items)
      }
    } catch (err: unknown) {
      if (err instanceof AuthApiError) {
        setError(err.message)
      } else {
        setError('Failed to load governance workspace data')
      }
    } finally {
      setLoading(false)
    }
  }, [token, activeOrg?.id, project.id, activeTab])

  useEffect(() => {
    loadData()
  }, [loadData])

  const handleSelectInvestigation = async (inv: Investigation) => {
    if (!token || !activeOrg) return
    try {
      const full = await getInvestigation(token, activeOrg.id, project.id, inv.id)
      setSelectedInvestigation(full)
    } catch {
      setSelectedInvestigation(inv)
    }
  }

  const handleApprovalDecision = async (decision: 'APPROVED' | 'REJECTED') => {
    if (!token || !activeOrg || !selectedApproval) return
    setApprovalLoading(true)
    setError(null)
    try {
      await decideApproval(token, activeOrg.id, project.id, selectedApproval.id, {
        decision,
        rationale: approvalRationale.trim() || `Decision recorded by authorized reviewer`,
      })
      setActionMessage(`Approval ${decision.toLowerCase()} successfully.`)
      setSelectedApproval(null)
      setApprovalRationale('')
      await loadData()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to record approval decision')
    } finally {
      setApprovalLoading(false)
    }
  }

  const handleExecuteAction = async (action: Action) => {
    if (!token || !activeOrg) return
    setExecutingActionId(action.id)
    setError(null)
    try {
      const idempotencyKey = `EXEC-${Date.now()}-${Math.random().toString(36).substring(2, 8)}`
      const exec = await executeAction(token, activeOrg.id, project.id, action.id, {
        idempotency_key: idempotencyKey,
      })
      setActionMessage(
        `Action dispatched to ${exec.target_adapter_type} (${exec.status}). Reference: ${JSON.stringify(exec.adapter_response_json)}`
      )
      await loadData()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to execute governed action')
    } finally {
      setExecutingActionId(null)
    }
  }

  const handleIngestDocument = async (e: FormEvent) => {
    e.preventDefault()
    if (!token || !activeOrg) return
    setDocIngestLoading(true)
    setError(null)
    try {
      await ingestDocument(token, activeOrg.id, project.id, {
        title: docTitle.trim(),
        document_type: docType,
        file_name: docFileName.trim(),
        raw_text: docRawText.trim(),
      })
      setShowIngestModal(false)
      setDocTitle('')
      setDocFileName('')
      setDocRawText('')
      setActionMessage('Document ingested and chunked for RAG successfully.')
      await loadData()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to ingest document')
    } finally {
      setDocIngestLoading(false)
    }
  }

  const handleSearchRAG = async (e: FormEvent) => {
    e.preventDefault()
    if (!token || !activeOrg || !searchQuery.trim()) return
    setSearching(true)
    setError(null)
    try {
      const res = await queryDocuments(token, activeOrg.id, project.id, {
        query_text: searchQuery.trim(),
        top_k: 4,
      })
      setSearchResults(res.results)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to query RAG chunks')
    } finally {
      setSearching(false)
    }
  }

  const handleRunP2PDemo = async () => {
    if (!token || !activeOrg) return
    setDemoLoading(true)
    setError(null)
    try {
      const res = await runP2PDemoSlice(token, activeOrg.id, project.id, {
        supplier_name: demoSupplier,
        po_number: demoPoNumber,
        po_amount: parseFloat(demoPoAmount) || 15000.0,
        invoice_number: demoInvoiceNumber,
        invoice_amount: parseFloat(demoInvoiceAmount) || 16250.0,
        expected_variance: parseFloat(demoVariance) || 1250.0,
        auto_approve: demoAutoApprove,
      })
      setDemoResult(res)
      setActionMessage(
        `P2P Vertical Slice executed successfully! Discrepancy: $${res.financial_impact_usd.toFixed(2)}.`
      )
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to execute P2P demo slice')
    } finally {
      setDemoLoading(false)
    }
  }

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <div className="flex items-center gap-3">
            <button
              onClick={onBack}
              className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors"
              aria-label="Back to projects"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
              </svg>
            </button>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-lg font-bold text-white">Governed Investigation & Approvals</h3>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                  Phase 9 Vertical Slice
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                Workspace: <span className="font-semibold text-slate-300">{project.name}</span> — Evidence-backed investigations, RAG citations, and human approval gates.
              </p>
            </div>
          </div>
        </div>

        <button
          onClick={() => setActiveTab('demo')}
          className="inline-flex items-center gap-2 px-3.5 py-2 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white text-xs font-semibold rounded-lg transition-all shadow-lg shadow-emerald-900/30 shrink-0"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span>Run P2P Demo Slice</span>
        </button>
      </div>

      {/* Tabs */}
      <div className="flex flex-wrap gap-2 border-b border-slate-800 pb-2">
        <button
          onClick={() => setActiveTab('investigations')}
          className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-colors flex items-center gap-2 ${
            activeTab === 'investigations'
              ? 'bg-indigo-600 text-white shadow-sm'
              : 'text-slate-400 hover:text-white hover:bg-slate-800/60'
          }`}
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          <span>Investigations</span>
        </button>

        <button
          onClick={() => setActiveTab('approvals')}
          className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-colors flex items-center gap-2 ${
            activeTab === 'approvals'
              ? 'bg-indigo-600 text-white shadow-sm'
              : 'text-slate-400 hover:text-white hover:bg-slate-800/60'
          }`}
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span>Human Approvals</span>
        </button>

        <button
          onClick={() => setActiveTab('actions')}
          className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-colors flex items-center gap-2 ${
            activeTab === 'actions'
              ? 'bg-indigo-600 text-white shadow-sm'
              : 'text-slate-400 hover:text-white hover:bg-slate-800/60'
          }`}
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
          <span>Governed Actions</span>
        </button>

        <button
          onClick={() => setActiveTab('rag')}
          className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-colors flex items-center gap-2 ${
            activeTab === 'rag'
              ? 'bg-indigo-600 text-white shadow-sm'
              : 'text-slate-400 hover:text-white hover:bg-slate-800/60'
          }`}
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
          </svg>
          <span>RAG Documents</span>
        </button>

        <button
          onClick={() => setActiveTab('audit')}
          className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-colors flex items-center gap-2 ${
            activeTab === 'audit'
              ? 'bg-indigo-600 text-white shadow-sm'
              : 'text-slate-400 hover:text-white hover:bg-slate-800/60'
          }`}
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span>Audit Log</span>
        </button>

        <button
          onClick={() => setActiveTab('demo')}
          className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-colors flex items-center gap-2 ${
            activeTab === 'demo'
              ? 'bg-emerald-600 text-white shadow-sm'
              : 'text-emerald-400 hover:text-emerald-300 hover:bg-emerald-950/40'
          }`}
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
          </svg>
          <span>P2P Slice Demo</span>
        </button>
      </div>

      {/* Notifications */}
      {error && (
        <div className="p-3 bg-rose-950/60 border border-rose-800/80 rounded-xl text-rose-200 text-xs flex justify-between items-center">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-rose-400 hover:text-white font-bold text-sm">×</button>
        </div>
      )}
      {actionMessage && (
        <div className="p-3 bg-emerald-950/60 border border-emerald-800/80 rounded-xl text-emerald-200 text-xs flex justify-between items-center">
          <span>{actionMessage}</span>
          <button onClick={() => setActionMessage(null)} className="text-emerald-400 hover:text-white font-bold text-sm">×</button>
        </div>
      )}

      {/* Tab 1: Investigations */}
      {activeTab === 'investigations' && (
        <div className="space-y-4">
          <div className="flex justify-between items-center">
            <h4 className="text-sm font-semibold text-white">Project Investigations ({investigations.length})</h4>
            <button
              onClick={loadData}
              className="px-2.5 py-1 text-xs text-slate-400 hover:text-white bg-slate-800 rounded transition-colors"
            >
              Refresh
            </button>
          </div>

          {loading ? (
            <div className="p-8 text-center text-slate-400 text-sm">Loading investigations...</div>
          ) : investigations.length === 0 ? (
            <div className="p-8 text-center bg-slate-950/40 border border-slate-800/60 rounded-xl text-slate-400 text-sm">
              No investigations created yet for this project. Launch one from an Exception Finding or run the P2P Demo Slice.
            </div>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-slate-800/80">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-950/80 text-slate-400 uppercase text-[10px] tracking-wider border-b border-slate-800">
                  <tr>
                    <th className="p-3">Title</th>
                    <th className="p-3">Status</th>
                    <th className="p-3">Financial Impact</th>
                    <th className="p-3">Evidence Items</th>
                    <th className="p-3">Created</th>
                    <th className="p-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 text-slate-300">
                  {investigations.map((inv) => (
                    <tr key={inv.id} className="hover:bg-slate-800/30 transition-colors">
                      <td className="p-3 font-medium text-white">{inv.title}</td>
                      <td className="p-3">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                          inv.status === 'COMPLETED' ? 'bg-emerald-950/60 text-emerald-400 border border-emerald-800/60' : 'bg-indigo-950/60 text-indigo-400 border border-indigo-800/60'
                        }`}>
                          {inv.status}
                        </span>
                      </td>
                      <td className="p-3 font-mono font-semibold text-amber-400">
                        ${inv.financial_impact_usd.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                      </td>
                      <td className="p-3">{inv.evidence_count}</td>
                      <td className="p-3 text-slate-400">{new Date(inv.created_at).toLocaleDateString()}</td>
                      <td className="p-3 text-right">
                        <button
                          onClick={() => handleSelectInvestigation(inv)}
                          className="px-2.5 py-1 bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-300 rounded font-semibold text-[11px] transition-colors"
                        >
                          Inspect
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Investigation Inspection Modal */}
          {selectedInvestigation && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 overflow-y-auto">
              <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-4xl w-full p-6 space-y-6 text-slate-100 max-h-[90vh] overflow-y-auto shadow-2xl">
                <div className="flex justify-between items-start border-b border-slate-800 pb-4">
                  <div>
                    <h3 className="text-lg font-bold text-white">{selectedInvestigation.title}</h3>
                    <p className="text-xs text-slate-400 mt-0.5">ID: {selectedInvestigation.id}</p>
                  </div>
                  <button
                    onClick={() => setSelectedInvestigation(null)}
                    className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors"
                  >
                    ✕
                  </button>
                </div>

                {/* Financial Impact Banner */}
                <div className="p-4 bg-gradient-to-r from-amber-950/40 to-slate-900 border border-amber-800/40 rounded-xl flex items-center justify-between">
                  <div>
                    <div className="text-[11px] uppercase tracking-wider text-amber-400 font-bold">
                      Deterministic Financial Impact
                    </div>
                    <div className="text-2xl font-mono font-extrabold text-amber-300">
                      ${selectedInvestigation.financial_impact_usd.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </div>
                  </div>
                  <span className="text-xs text-slate-400 max-w-xs text-right">
                    Calculated from observed transaction variance and verified contractual thresholds.
                  </span>
                </div>

                {/* Facts vs Extracts vs Hypotheses Separation */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {/* Verified Facts */}
                  <div className="p-4 bg-slate-950/80 border border-emerald-900/40 rounded-xl space-y-3">
                    <div className="flex items-center gap-2 text-emerald-400 font-bold text-xs uppercase tracking-wider">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                      <span>Verified Transactional Facts</span>
                    </div>
                    <p className="text-[11px] text-slate-400">
                      Authoritative transactional data from database records.
                    </p>
                    <div className="space-y-2">
                      {selectedInvestigation.verified_facts_json?.map((fact, idx) => (
                        <div key={idx} className="p-2.5 bg-slate-900 border border-slate-800 rounded text-xs font-mono text-slate-300">
                          <pre className="whitespace-pre-wrap">{JSON.stringify(fact, null, 2)}</pre>
                        </div>
                      )) || <div className="text-xs text-slate-500 italic">No transactional facts recorded</div>}
                    </div>
                  </div>

                  {/* Document Extracts */}
                  <div className="p-4 bg-slate-950/80 border border-sky-900/40 rounded-xl space-y-3">
                    <div className="flex items-center gap-2 text-sky-400 font-bold text-xs uppercase tracking-wider">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                      </svg>
                      <span>Document Extracts (RAG)</span>
                    </div>
                    <p className="text-[11px] text-slate-400">
                      Clauses retrieved from contracts & SOWs. Not transactional facts.
                    </p>
                    <div className="space-y-2">
                      {selectedInvestigation.document_extracts_json?.map((extract, idx) => (
                        <div key={idx} className="p-2.5 bg-slate-900 border border-slate-800 rounded text-xs font-mono text-sky-300">
                          <pre className="whitespace-pre-wrap">{JSON.stringify(extract, null, 2)}</pre>
                        </div>
                      )) || <div className="text-xs text-slate-500 italic">No document extracts recorded</div>}
                    </div>
                  </div>

                  {/* Causal Hypotheses */}
                  <div className="p-4 bg-slate-950/80 border border-purple-900/40 rounded-xl space-y-3">
                    <div className="flex items-center gap-2 text-purple-400 font-bold text-xs uppercase tracking-wider">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                      </svg>
                      <span>Causal Hypotheses (AI Generated)</span>
                    </div>
                    <p className="text-[11px] text-slate-400">
                      Model-generated explanations for root cause. Subject to review.
                    </p>
                    <div className="p-3 bg-slate-900 border border-slate-800 rounded text-xs text-purple-200 leading-relaxed">
                      {selectedInvestigation.causal_hypothesis || 'No hypothesis formulated.'}
                    </div>
                  </div>
                </div>

                {/* Evidence Items */}
                <div className="space-y-2">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400">Retrieved Evidence & Citations</h4>
                  <div className="space-y-2 max-h-48 overflow-y-auto">
                    {selectedInvestigation.evidence_items?.map((ev) => (
                      <div key={ev.id} className="p-3 bg-slate-950/60 border border-slate-800 rounded-lg text-xs space-y-1">
                        <div className="flex justify-between items-center text-slate-400">
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-slate-200">{ev.title}</span>
                            {ev.evidence_classification === 'DOCUMENT_EXTRACT' ? (
                              <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-sky-950 text-sky-300 border border-sky-800">
                                Document Extract (Unverified Fact)
                              </span>
                            ) : ev.evidence_classification === 'TRANSACTION_FACT' ? (
                              <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800">
                                Transaction Fact (Verified)
                              </span>
                            ) : (
                              <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-purple-950 text-purple-300 border border-purple-800">
                                AI Hypothesis
                              </span>
                            )}
                          </div>
                          <span className="text-[10px] font-mono">{ev.evidence_type} (Score: {ev.confidence_score.toFixed(2)})</span>
                        </div>
                        <p className="text-slate-300 italic">"{ev.content_snippet}"</p>
                      </div>
                    )) || <div className="text-xs text-slate-500">No evidence items attached.</div>}
                  </div>
                </div>

                {/* Recommendations */}
                <div className="space-y-2">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400">Formulated Recommendations</h4>
                  <div className="space-y-3">
                    {selectedInvestigation.recommendations?.map((rec) => (
                      <div key={rec.id} className="p-4 bg-slate-950 border border-indigo-900/40 rounded-xl space-y-2">
                        <div className="flex justify-between items-start">
                          <div>
                            <div className="font-semibold text-white text-sm">{rec.title}</div>
                            <p className="text-xs text-slate-300 mt-1">{rec.description}</p>
                          </div>
                          <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-indigo-950 text-indigo-300 border border-indigo-800">
                            {rec.recommended_action_type}
                          </span>
                        </div>
                        <div className="text-[11px] font-mono text-slate-400 bg-slate-900 p-2 rounded border border-slate-800">
                          <span className="text-slate-500">Payload: </span>
                          {JSON.stringify(rec.suggested_payload_json)}
                        </div>
                      </div>
                    )) || <div className="text-xs text-slate-500">No recommendations available.</div>}
                  </div>
                </div>

                <div className="flex justify-end pt-2">
                  <button
                    onClick={() => setSelectedInvestigation(null)}
                    className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold rounded-lg transition-colors"
                  >
                    Close
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Tab 2: Human Approvals */}
      {activeTab === 'approvals' && (
        <div className="space-y-4">
          <div className="flex justify-between items-center">
            <div>
              <h4 className="text-sm font-semibold text-white">Pending Human Approval Gates ({approvals.length})</h4>
              <p className="text-xs text-slate-400">
                Consequential operations require explicit human authorization with cryptographic canonical payload hash verification.
              </p>
            </div>
            <button
              onClick={loadData}
              className="px-2.5 py-1 text-xs text-slate-400 hover:text-white bg-slate-800 rounded transition-colors"
            >
              Refresh
            </button>
          </div>

          {loading ? (
            <div className="p-8 text-center text-slate-400 text-sm">Loading approval gates...</div>
          ) : approvals.length === 0 ? (
            <div className="p-8 text-center bg-slate-950/40 border border-slate-800/60 rounded-xl text-slate-400 text-sm">
              No approval requests found for this project.
            </div>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-slate-800/80">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-950/80 text-slate-400 uppercase text-[10px] tracking-wider border-b border-slate-800">
                  <tr>
                    <th className="p-3">Approval ID</th>
                    <th className="p-3">Assigned Role</th>
                    <th className="p-3">Status</th>
                    <th className="p-3">Payload SHA-256 Hash</th>
                    <th className="p-3">Created</th>
                    <th className="p-3 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 text-slate-300">
                  {approvals.map((appr) => (
                    <tr key={appr.id} className="hover:bg-slate-800/30 transition-colors">
                      <td className="p-3 font-mono text-slate-300">{appr.id.substring(0, 8)}...</td>
                      <td className="p-3 font-semibold text-white">{appr.assigned_role}</td>
                      <td className="p-3">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                          appr.status === 'APPROVED' ? 'bg-emerald-950/60 text-emerald-400 border border-emerald-800/60' : appr.status === 'REJECTED' ? 'bg-rose-950/60 text-rose-400 border border-rose-800/60' : 'bg-amber-950/60 text-amber-400 border border-amber-800/60'
                        }`}>
                          {appr.status}
                        </span>
                      </td>
                      <td className="p-3 font-mono text-[10px] text-slate-400 truncate max-w-xs">
                        {appr.approved_payload_hash || '(Calculated on approval)'}
                      </td>
                      <td className="p-3 text-slate-400">{new Date(appr.created_at).toLocaleDateString()}</td>
                      <td className="p-3 text-right">
                        {appr.status === 'PENDING' ? (
                          <button
                            onClick={() => setSelectedApproval(appr)}
                            className="px-2.5 py-1 bg-indigo-600 hover:bg-indigo-500 text-white rounded font-semibold text-[11px] transition-colors"
                          >
                            Review & Decide
                          </button>
                        ) : (
                          <span className="text-[11px] text-slate-500 font-mono">Decided</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Decide Approval Modal */}
          {selectedApproval && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
              <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-lg w-full p-6 space-y-4 text-slate-100 shadow-2xl">
                <div className="flex justify-between items-start border-b border-slate-800 pb-3">
                  <h3 className="text-base font-bold text-white">Review Consequential Action Approval</h3>
                  <button onClick={() => setSelectedApproval(null)} className="text-slate-400 hover:text-white">✕</button>
                </div>

                <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg text-xs space-y-1">
                  <div className="text-slate-400 font-semibold">Approval Gate Target:</div>
                  <div className="font-mono text-indigo-300">Approval ID: {selectedApproval.id}</div>
                  <div className="text-slate-400">Required Role: <strong className="text-white">{selectedApproval.assigned_role}</strong></div>
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1" htmlFor="approval-rationale">
                    Decision Audit Rationale (Mandatory)
                  </label>
                  <textarea
                    id="approval-rationale"
                    rows={3}
                    value={approvalRationale}
                    onChange={(e) => setApprovalRationale(e.target.value)}
                    placeholder="Document verified contractual clauses or rationale for authorizing payment hold."
                    className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>

                <div className="flex justify-end gap-3 pt-2">
                  <button
                    disabled={approvalLoading}
                    onClick={() => handleApprovalDecision('REJECTED')}
                    className="px-3.5 py-1.5 bg-rose-900/60 hover:bg-rose-900 text-rose-200 text-xs font-semibold rounded-lg transition-colors border border-rose-800"
                  >
                    Reject Operation
                  </button>
                  <button
                    disabled={approvalLoading}
                    onClick={() => handleApprovalDecision('APPROVED')}
                    className="px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold rounded-lg transition-colors flex items-center gap-1.5"
                  >
                    <span>Sign & Authorize</span>
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Tab 3: Governed Actions */}
      {activeTab === 'actions' && (
        <div className="space-y-4">
          <div className="flex justify-between items-center">
            <div>
              <h4 className="text-sm font-semibold text-white">Governed Action Dispatcher ({actions.length})</h4>
              <p className="text-xs text-slate-400">
                Dispatches authorized actions to target enterprise systems via TargetSystemAdapter with idempotency guarantees.
              </p>
            </div>
            <button
              onClick={loadData}
              className="px-2.5 py-1 text-xs text-slate-400 hover:text-white bg-slate-800 rounded transition-colors"
            >
              Refresh
            </button>
          </div>

          {loading ? (
            <div className="p-8 text-center text-slate-400 text-sm">Loading actions...</div>
          ) : actions.length === 0 ? (
            <div className="p-8 text-center bg-slate-950/40 border border-slate-800/60 rounded-xl text-slate-400 text-sm">
              No actions generated yet.
            </div>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-slate-800/80">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-950/80 text-slate-400 uppercase text-[10px] tracking-wider border-b border-slate-800">
                  <tr>
                    <th className="p-3">Action Type</th>
                    <th className="p-3">Target Adapter</th>
                    <th className="p-3">Status</th>
                    <th className="p-3">Payload Details</th>
                    <th className="p-3 text-right">Execution</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 text-slate-300">
                  {actions.map((act) => (
                    <tr key={act.id} className="hover:bg-slate-800/30 transition-colors">
                      <td className="p-3 font-semibold text-white">{act.action_type}</td>
                      <td className="p-3 font-mono text-[11px] text-slate-400">{act.target_system}</td>
                      <td className="p-3">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                          act.status === 'EXECUTED' ? 'bg-emerald-950/60 text-emerald-400 border border-emerald-800/60' : act.status === 'APPROVED' ? 'bg-indigo-950/60 text-indigo-400 border border-indigo-800/60' : 'bg-amber-950/60 text-amber-400 border border-amber-800/60'
                        }`}>
                          {act.status}
                        </span>
                      </td>
                      <td className="p-3 font-mono text-[10px] text-slate-400 truncate max-w-xs">
                        {JSON.stringify(act.proposed_payload_json)}
                      </td>
                      <td className="p-3 text-right">
                        {act.status === 'APPROVED' ? (
                          <button
                            disabled={executingActionId === act.id}
                            onClick={() => handleExecuteAction(act)}
                            className="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white rounded font-semibold text-[11px] transition-colors"
                          >
                            {executingActionId === act.id ? 'Dispatching...' : 'Dispatch Action'}
                          </button>
                        ) : (
                          <span className="text-slate-500 font-mono text-[11px]">{act.status}</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Tab 4: RAG Documents */}
      {activeTab === 'rag' && (
        <div className="space-y-6">
          <div className="flex justify-between items-center">
            <div>
              <h4 className="text-sm font-semibold text-white">RAG Knowledge Base & Contract Ingestion ({documents.length})</h4>
              <p className="text-xs text-slate-400">
                Index unstructured contracts, terms, and purchase agreements with section-aware chunking and hybrid retrieval.
              </p>
            </div>
            <button
              onClick={() => setShowIngestModal(true)}
              className="px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold rounded-lg transition-colors flex items-center gap-1.5"
            >
              <span>+ Ingest Document</span>
            </button>
          </div>

          {/* RAG Query Tester */}
          <div className="p-4 bg-slate-950/80 border border-slate-800 rounded-xl space-y-3">
            <h5 className="text-xs font-bold text-slate-300 uppercase tracking-wider">Semantic & Lexical RAG Retrieval Query</h5>
            <form onSubmit={handleSearchRAG} className="flex gap-2">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="e.g. freight surcharge shipping payment hold"
                className="flex-1 px-3 py-1.5 bg-slate-900 border border-slate-700 rounded-lg text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
              <button
                type="submit"
                disabled={searching}
                className="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold rounded-lg transition-colors"
              >
                {searching ? 'Querying...' : 'Search'}
              </button>
            </form>

            {searchResults.length > 0 && (
              <div className="space-y-2 pt-2 border-t border-slate-800">
                <div className="text-[11px] text-slate-400">Retrieved {searchResults.length} ranked chunks:</div>
                <div className="space-y-2">
                  {searchResults.map((r, i) => (
                    <div key={i} className="p-3 bg-slate-900 border border-slate-800 rounded-lg text-xs space-y-1">
                      <div className="flex justify-between text-indigo-400 font-semibold text-[11px]">
                        <span>{r.document_title} — {r.section_header || 'General'}</span>
                        <span className="font-mono text-slate-400">Score: {r.relevance_score.toFixed(3)}</span>
                      </div>
                      <p className="text-slate-300 font-mono text-[11px] whitespace-pre-wrap">{r.chunk_text}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Document List */}
          <div className="overflow-x-auto rounded-xl border border-slate-800/80">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-950/80 text-slate-400 uppercase text-[10px] tracking-wider border-b border-slate-800">
                <tr>
                  <th className="p-3">Title</th>
                  <th className="p-3">Type</th>
                  <th className="p-3">File Name</th>
                  <th className="p-3">Chunks</th>
                  <th className="p-3">Indexed At</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 text-slate-300">
                {documents.map((d) => (
                  <tr key={d.id} className="hover:bg-slate-800/30 transition-colors">
                    <td className="p-3 font-semibold text-white">{d.title}</td>
                    <td className="p-3">
                      <span className="px-2 py-0.5 rounded text-[10px] bg-slate-800 text-slate-300 border border-slate-700">
                        {d.document_type}
                      </span>
                    </td>
                    <td className="p-3 font-mono text-[11px] text-slate-400">{d.file_name}</td>
                    <td className="p-3 font-mono text-indigo-300">{d.chunk_count}</td>
                    <td className="p-3 text-slate-400">{new Date(d.created_at).toLocaleDateString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Ingest Modal */}
          {showIngestModal && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
              <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-lg w-full p-6 space-y-4 text-slate-100 shadow-2xl">
                <div className="flex justify-between items-start border-b border-slate-800 pb-3">
                  <h3 className="text-base font-bold text-white">Ingest Business Document for RAG</h3>
                  <button onClick={() => setShowIngestModal(false)} className="text-slate-400 hover:text-white">✕</button>
                </div>

                <form onSubmit={handleIngestDocument} className="space-y-3">
                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1" htmlFor="doc-title">Document Title</label>
                    <input
                      id="doc-title"
                      type="text"
                      required
                      value={docTitle}
                      onChange={(e) => setDocTitle(e.target.value)}
                      placeholder="e.g. Master Services Agreement (MSA 2026)"
                      className="w-full px-3 py-1.5 bg-slate-950 border border-slate-700 rounded-lg text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-medium text-slate-300 mb-1" htmlFor="doc-type">Type</label>
                      <select
                        id="doc-type"
                        value={docType}
                        onChange={(e) => setDocType(e.target.value as 'CONTRACT' | 'POLICY' | 'INVOICE')}
                        className="w-full px-3 py-1.5 bg-slate-950 border border-slate-700 rounded-lg text-xs text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                      >
                        <option value="CONTRACT">CONTRACT</option>
                        <option value="POLICY">POLICY</option>
                        <option value="INVOICE">INVOICE</option>
                      </select>
                    </div>

                    <div>
                      <label className="block text-xs font-medium text-slate-300 mb-1" htmlFor="doc-file-name">File Name</label>
                      <input
                        id="doc-file-name"
                        type="text"
                        required
                        value={docFileName}
                        onChange={(e) => setDocFileName(e.target.value)}
                        placeholder="agreement.txt"
                        className="w-full px-3 py-1.5 bg-slate-950 border border-slate-700 rounded-lg text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1" htmlFor="doc-raw-text">Raw Text Content</label>
                    <textarea
                      id="doc-raw-text"
                      rows={6}
                      required
                      value={docRawText}
                      onChange={(e) => setDocRawText(e.target.value)}
                      placeholder="Paste clauses, terms, or specifications..."
                      className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-xs font-mono text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    />
                  </div>

                  <div className="flex justify-end gap-3 pt-2">
                    <button
                      type="button"
                      onClick={() => setShowIngestModal(false)}
                      className="px-4 py-1.5 bg-slate-800 text-slate-300 text-xs font-semibold rounded-lg"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={docIngestLoading}
                      className="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold rounded-lg flex items-center gap-2"
                    >
                      {docIngestLoading ? 'Chunking & Indexing...' : 'Index Document'}
                    </button>
                  </div>
                </form>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Tab 5: Authoritative Audit Log */}
      {activeTab === 'audit' && (
        <div className="space-y-4">
          <div className="flex justify-between items-center">
            <div>
              <h4 className="text-sm font-semibold text-white">Authoritative Append-Only Audit Trail ({auditEvents.length})</h4>
              <p className="text-xs text-slate-400">
                PostgreSQL immutable event store recording all investigations, recommendations, human approvals, and action dispatches.
              </p>
            </div>
            <button
              onClick={loadData}
              className="px-2.5 py-1 text-xs text-slate-400 hover:text-white bg-slate-800 rounded transition-colors"
            >
              Refresh
            </button>
          </div>

          <div className="overflow-x-auto rounded-xl border border-slate-800/80">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-950/80 text-slate-400 uppercase text-[10px] tracking-wider border-b border-slate-800">
                <tr>
                  <th className="p-3">Timestamp</th>
                  <th className="p-3">Actor</th>
                  <th className="p-3">Action Type</th>
                  <th className="p-3">Affected Entity</th>
                  <th className="p-3">Outcome</th>
                  <th className="p-3">Context</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 text-slate-300">
                {auditEvents.map((ev) => (
                  <tr key={ev.id} className="hover:bg-slate-800/30 transition-colors">
                    <td className="p-3 font-mono text-[11px] text-slate-400">
                      {new Date(ev.timestamp).toLocaleString()}
                    </td>
                    <td className="p-3 font-semibold text-white">
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 mr-1.5">
                        {ev.actor_type}
                      </span>
                      {ev.actor_id.substring(0, 8)}...
                    </td>
                    <td className="p-3 font-mono font-semibold text-indigo-300">{ev.action_type}</td>
                    <td className="p-3 font-mono text-[11px] text-slate-400">
                      {ev.affected_entity_type}/{ev.affected_entity_id.substring(0, 8)}
                    </td>
                    <td className="p-3">
                      <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-950/60 text-emerald-400 border border-emerald-800/60">
                        {ev.outcome_status}
                      </span>
                    </td>
                    <td className="p-3 font-mono text-[10px] text-slate-400 truncate max-w-xs">
                      {ev.execution_context_json ? JSON.stringify(ev.execution_context_json) : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tab 6: P2P Slice Demo */}
      {activeTab === 'demo' && (
        <div className="space-y-6">
          <div className="p-4 bg-gradient-to-r from-emerald-950/40 via-slate-900 to-indigo-950/40 border border-emerald-800/40 rounded-xl space-y-2">
            <h4 className="text-base font-bold text-white flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse" />
              Procure-to-Pay (P2P) Vertical Slice Demonstration
            </h4>
            <p className="text-xs text-slate-300 leading-relaxed">
              Demonstrates the complete end-to-end operational governance lifecycle:
              <br />
              <strong>1. Operational Finding</strong> (Price/Freight variance) → <strong>2. Master Agreement RAG Indexing</strong> → <strong>3. Governed Investigation</strong> (Facts vs Hypotheses) → <strong>4. Impact USD Calculation</strong> → <strong>5. Human Approval Gate</strong> → <strong>6. ERP Adapter Hold Dispatch</strong> → <strong>7. Authoritative Audit Trail</strong>.
            </p>
          </div>

          {/* Trigger Parameters Form */}
          <div className="p-5 bg-slate-950 border border-slate-800 rounded-xl space-y-4">
            <h5 className="text-xs font-bold text-slate-300 uppercase tracking-wider">Demo Execution Parameters</h5>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
              <div>
                <label className="block text-[11px] font-medium text-slate-400 mb-1" htmlFor="demo-supplier">Supplier Name</label>
                <input
                  id="demo-supplier"
                  type="text"
                  value={demoSupplier}
                  onChange={(e) => setDemoSupplier(e.target.value)}
                  className="w-full px-3 py-1.5 bg-slate-900 border border-slate-700 rounded text-xs text-white"
                />
              </div>

              <div>
                <label className="block text-[11px] font-medium text-slate-400 mb-1" htmlFor="demo-po-number">PO Number & Budget</label>
                <div className="flex gap-2">
                  <input
                    id="demo-po-number"
                    type="text"
                    value={demoPoNumber}
                    onChange={(e) => setDemoPoNumber(e.target.value)}
                    className="w-1/2 px-3 py-1.5 bg-slate-900 border border-slate-700 rounded text-xs text-white"
                  />
                  <input
                    type="text"
                    value={demoPoAmount}
                    onChange={(e) => setDemoPoAmount(e.target.value)}
                    className="w-1/2 px-3 py-1.5 bg-slate-900 border border-slate-700 rounded text-xs text-white font-mono"
                  />
                </div>
              </div>

              <div>
                <label className="block text-[11px] font-medium text-slate-400 mb-1" htmlFor="demo-invoice-number">Invoice & Billed</label>
                <div className="flex gap-2">
                  <input
                    id="demo-invoice-number"
                    type="text"
                    value={demoInvoiceNumber}
                    onChange={(e) => setDemoInvoiceNumber(e.target.value)}
                    className="w-1/2 px-3 py-1.5 bg-slate-900 border border-slate-700 rounded text-xs text-white"
                  />
                  <input
                    type="text"
                    value={demoInvoiceAmount}
                    onChange={(e) => setDemoInvoiceAmount(e.target.value)}
                    className="w-1/2 px-3 py-1.5 bg-slate-900 border border-slate-700 rounded text-xs text-white font-mono"
                  />
                </div>
              </div>

              <div>
                <label className="block text-[11px] font-medium text-slate-400 mb-1" htmlFor="demo-variance">Expected Variance ($)</label>
                <input
                  id="demo-variance"
                  type="text"
                  value={demoVariance}
                  onChange={(e) => setDemoVariance(e.target.value)}
                  className="w-full px-3 py-1.5 bg-slate-900 border border-slate-700 rounded text-xs text-white font-mono"
                />
              </div>
            </div>

            <div className="flex items-center justify-between pt-2">
              <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={demoAutoApprove}
                  onChange={(e) => setDemoAutoApprove(e.target.checked)}
                  className="w-4 h-4 rounded border-slate-700 bg-slate-900 text-indigo-600 focus:ring-0"
                />
                <span>Auto-sign approval & dispatch action immediately (Full Automation Demo)</span>
              </label>

              <button
                onClick={handleRunP2PDemo}
                disabled={demoLoading}
                className="px-5 py-2 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 disabled:opacity-50 text-white font-bold text-xs rounded-lg transition-all shadow-lg shadow-emerald-900/30 flex items-center gap-2"
              >
                {demoLoading ? (
                  <>
                    <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                    </svg>
                    <span>Executing P2P Slice...</span>
                  </>
                ) : (
                  <span>Execute Full Demonstration</span>
                )}
              </button>
            </div>
          </div>

          {/* Demo Results Display */}
          {demoResult && (
            <div className="p-6 bg-slate-950 border border-emerald-900/40 rounded-2xl space-y-6 shadow-2xl">
              <div className="flex justify-between items-center border-b border-slate-800 pb-3">
                <div className="flex items-center gap-2">
                  <span className="w-3 h-3 rounded-full bg-emerald-400" />
                  <h4 className="text-base font-bold text-white">Demonstration Execution Result</h4>
                </div>
                <div className="text-xs font-mono text-emerald-400">
                  Audit Events Recorded: {demoResult.audit_events_count}
                </div>
              </div>

              {/* 3 Step Visual Progression */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {/* 1. Detection & Facts */}
                <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl space-y-2">
                  <div className="text-[11px] font-bold uppercase text-slate-400">1. Anomaly & Facts</div>
                  <div className="text-sm font-bold text-white">{demoResult.action.action_type}</div>
                  <div className="text-xs text-amber-300 font-mono font-bold">
                    Impact: ${demoResult.financial_impact_usd.toFixed(2)}
                  </div>
                  <div className="text-[11px] text-slate-400 line-clamp-3">
                    {demoResult.causal_hypothesis}
                  </div>
                </div>

                {/* 2. RAG Contract Retrieval */}
                <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl space-y-2">
                  <div className="text-[11px] font-bold uppercase text-slate-400">2. RAG Citations</div>
                  <div className="text-xs text-indigo-300 font-semibold">MSA Section 4.2 Terms</div>
                  <div className="text-[11px] text-slate-300 italic line-clamp-3">
                    "{demoResult.retrieved_document_snippets[0] || 'Clause terms verified'}"
                  </div>
                </div>

                {/* 3. Governed Execution */}
                <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl space-y-2">
                  <div className="text-[11px] font-bold uppercase text-slate-400">3. Execution & ERP</div>
                  <div className="text-xs font-semibold text-emerald-400">
                    Status: {demoResult.execution?.status || demoResult.action.status}
                  </div>
                  <div className="text-[11px] font-mono text-slate-400 truncate">
                    Hash: {demoResult.approval?.approved_payload_hash?.substring(0, 16)}...
                  </div>
                  <div className="text-[11px] text-slate-300 font-mono">
                    Adapter: {demoResult.action.target_system}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
