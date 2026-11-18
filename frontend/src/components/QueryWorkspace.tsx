import { useState, useEffect, useCallback, type FormEvent } from 'react'
import { useAuth } from '../context/AuthContext'
import {
  getQuerySchema,
  executeStructuredQuery,
  compileNaturalLanguageQuery,
  getQueryHistory,
} from '../services/query'
import type {
  QueryableEntitySchema,
  QueryFilter,
  QueryOperator,
  QuerySchemaResponse,
  QuerySort,
  SortDirection,
  StructuredQueryRequest,
  StructuredQueryResponse,
  NaturalLanguageQueryResponse,
  QueryExecutionAuditResponse,
} from '../types/query'
import type { Project } from '../types/auth'
import { AuthApiError } from '../services/auth'

interface QueryWorkspaceProps {
  project: Project
  onBack: () => void
}

const OPERATOR_LABELS: Record<QueryOperator, string> = {
  eq: '= (Equals)',
  neq: '!= (Not Equals)',
  gt: '> (Greater Than)',
  gte: '>= (Greater or Equal)',
  lt: '< (Less Than)',
  lte: '<= (Less or Equal)',
  contains: 'Contains',
  starts_with: 'Starts With',
  ends_with: 'Ends With',
  in: 'IN (List)',
  not_in: 'NOT IN',
  is_null: 'Is NULL',
  is_not_null: 'Is NOT NULL',
}

export function QueryWorkspace({ project, onBack }: QueryWorkspaceProps) {
  const { token, activeOrg } = useAuth()

  // Navigation tab
  const [activeTab, setActiveTab] = useState<'builder' | 'history'>('builder')

  // Schema state
  const [schema, setSchema] = useState<QuerySchemaResponse | null>(null)
  const [selectedEntity, setSelectedEntity] = useState<QueryableEntitySchema | null>(null)
  const [loadingSchema, setLoadingSchema] = useState(false)

  // Query Builder state
  const [selectedFields, setSelectedFields] = useState<string[]>([])
  const [filters, setFilters] = useState<QueryFilter[]>([])
  const [sorts, setSorts] = useState<QuerySort[]>([])
  const [limit, setLimit] = useState(50)
  const [offset, setOffset] = useState(0)

  // Execution state
  const [executing, setExecuting] = useState(false)
  const [queryResult, setQueryResult] = useState<StructuredQueryResponse | null>(null)
  const [queryPlanOpen, setQueryPlanOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // NLQ Assistant state
  const [nlqPrompt, setNlqPrompt] = useState('')
  const [nlqLoading, setNlqLoading] = useState(false)
  const [nlqResult, setNlqResult] = useState<NaturalLanguageQueryResponse | null>(null)
  const [currentNlqRef, setCurrentNlqRef] = useState<string | null>(null)

  // History state
  const [history, setHistory] = useState<QueryExecutionAuditResponse[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)

  // 1. Load Schema
  const loadSchema = useCallback(async () => {
    if (!token || !activeOrg) return
    setLoadingSchema(true)
    setError(null)
    try {
      const data = await getQuerySchema(token, activeOrg.id, project.id)
      setSchema(data)
      if (data.entities.length > 0 && !selectedEntity) {
        setSelectedEntity(data.entities[0])
      }
    } catch (err: unknown) {
      if (err instanceof AuthApiError) {
        setError(err.message)
      } else {
        setError('Failed to load project query schema')
      }
    } finally {
      setLoadingSchema(false)
    }
  }, [token, activeOrg?.id, project.id, selectedEntity])

  // 2. Load History
  const loadHistory = useCallback(async () => {
    if (!token || !activeOrg) return
    setHistoryLoading(true)
    try {
      const data = await getQueryHistory(token, activeOrg.id, project.id)
      setHistory(data)
    } catch {
      // Non-fatal
    } finally {
      setHistoryLoading(false)
    }
  }, [token, activeOrg?.id, project.id])

  useEffect(() => {
    void loadSchema()
  }, [loadSchema])

  useEffect(() => {
    if (activeTab === 'history') {
      void loadHistory()
    }
  }, [activeTab, loadHistory])

  // Reset fields & filters when entity changes
  const handleSelectEntity = (entityName: string) => {
    if (!schema) return
    const ent = schema.entities.find((e) => e.name === entityName) || null
    setSelectedEntity(ent)
    setSelectedFields([])
    setFilters([])
    setSorts([])
    setQueryResult(null)
    setNlqResult(null)
    setCurrentNlqRef(null)
  }

  // Toggle field selection
  const handleToggleField = (fieldName: string) => {
    setCurrentNlqRef(null)
    setSelectedFields((prev) =>
      prev.includes(fieldName) ? prev.filter((f) => f !== fieldName) : [...prev, fieldName]
    )
  }

  // Add filter
  const handleAddFilter = () => {
    setCurrentNlqRef(null)
    if (!selectedEntity) return
    const firstProp = selectedEntity.properties.find((p) => p.is_mapped) || selectedEntity.properties[0]
    if (!firstProp) return
    setFilters((prev) => [
      ...prev,
      {
        field: firstProp.name,
        operator: 'eq',
        value: '',
      },
    ])
  }

  // Update filter
  const handleUpdateFilter = (index: number, patch: Partial<QueryFilter>) => {
    setCurrentNlqRef(null)
    setFilters((prev) => {
      const updated = [...prev]
      updated[index] = { ...updated[index], ...patch }
      return updated
    })
  }

  // Remove filter
  const handleRemoveFilter = (index: number) => {
    setCurrentNlqRef(null)
    setFilters((prev) => prev.filter((_, i) => i !== index))
  }

  // Add sort
  const handleAddSort = () => {
    setCurrentNlqRef(null)
    if (!selectedEntity) return
    const firstProp = selectedEntity.properties.find((p) => p.is_mapped) || selectedEntity.properties[0]
    if (!firstProp) return
    setSorts((prev) => [
      ...prev,
      {
        field: firstProp.name,
        direction: 'asc',
      },
    ])
  }

  // Update sort
  const handleUpdateSort = (index: number, patch: Partial<QuerySort>) => {
    setCurrentNlqRef(null)
    setSorts((prev) => {
      const updated = [...prev]
      updated[index] = { ...updated[index], ...patch }
      return updated
    })
  }

  // Remove sort
  const handleRemoveSort = (index: number) => {
    setCurrentNlqRef(null)
    setSorts((prev) => prev.filter((_, i) => i !== index))
  }

  // Execute Structured Query
  const handleExecute = async (overrideReq?: StructuredQueryRequest) => {
    if (!token || !activeOrg || (!selectedEntity && !overrideReq)) return
    setExecuting(true)
    setError(null)

    const targetReq: StructuredQueryRequest = overrideReq || {
      entity_name: selectedEntity!.name,
      fields: selectedFields,
      filters: filters.map((f) => {
        let cleanVal: unknown = f.value
        // Numeric coercion if filter value looks like a number
        if (typeof f.value === 'string' && f.value.trim() !== '' && !isNaN(Number(f.value))) {
          cleanVal = Number(f.value)
        }
        return {
          field: f.field,
          operator: f.operator,
          value: cleanVal,
        }
      }),
      sorts,
      limit,
      offset,
      nlq_reference: currentNlqRef || undefined,
    }

    try {
      const res = await executeStructuredQuery(token, activeOrg.id, project.id, targetReq)
      setQueryResult(res)
      setCurrentNlqRef(null)
    } catch (err: unknown) {
      if (err instanceof AuthApiError) {
        setError(err.message)
      } else {
        setError('Query execution failed. Verify your filters and mappings.')
      }
    } finally {
      setExecuting(false)
    }
  }

  // Compile Natural Language Query
  const handleCompileNLQ = async (e: FormEvent) => {
    e.preventDefault()
    if (!token || !activeOrg || !nlqPrompt.trim()) return
    setNlqLoading(true)
    setError(null)
    setNlqResult(null)
    setCurrentNlqRef(null)

    try {
      const res = await compileNaturalLanguageQuery(token, activeOrg.id, project.id, {
        prompt: nlqPrompt.trim(),
        target_entity: selectedEntity?.name,
      })
      setNlqResult(res)
      setCurrentNlqRef(res.nlq_reference)

      // Also sync builder UI with parsed query AST
      if (schema) {
        const ent = schema.entities.find((e) => e.name === res.parsed_query.entity_name)
        if (ent) {
          setSelectedEntity(ent)
        }
      }
      setSelectedFields(res.parsed_query.fields)
      setFilters(res.parsed_query.filters)
      setSorts(res.parsed_query.sorts)
      setLimit(res.parsed_query.limit)
      setOffset(res.parsed_query.offset)
    } catch (err: unknown) {
      if (err instanceof AuthApiError) {
        setError(err.message)
      } else {
        setError('Natural language query compilation failed.')
      }
    } finally {
      setNlqLoading(false)
    }
  }

  // Export Results to CSV
  const handleExportCSV = () => {
    if (!queryResult || queryResult.rows.length === 0) return

    const cols = queryResult.columns
    const csvLines: string[] = []
    csvLines.push(cols.map((c) => `"${c}"`).join(','))

    for (const r of queryResult.rows) {
      const line = cols.map((col) => {
        const val = r[col]
        if (val === null || val === undefined) return '""'
        return `"${String(val).replace(/"/g, '""')}"`
      })
      csvLines.push(line.join(','))
    }

    const blob = new Blob([csvLines.join('\n')], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', `${queryResult.entity_name}_query_export_${Date.now()}.csv`)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  }

  const mappedProps = selectedEntity?.properties.filter((p) => p.is_mapped) || []

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-6">
      {/* Workspace Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <div className="flex items-center gap-3">
            <button
              onClick={onBack}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
              title="Back to Projects"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
              </svg>
            </button>
            <h3 className="text-xl font-bold text-white">Structured Querying & Early AI</h3>
            <span className="text-xs font-mono px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
              {project.name}
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Deterministic parameterized SQL execution over confirmed ontology entities and datasets with AI natural language translation.
          </p>
        </div>

        {/* Tab Switcher */}
        <div className="flex bg-slate-950 p-1 rounded-xl border border-slate-800 self-start sm:self-auto">
          <button
            type="button"
            onClick={() => setActiveTab('builder')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors flex items-center gap-2 ${
              activeTab === 'builder'
                ? 'bg-indigo-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-white hover:bg-slate-800/60'
            }`}
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16m-7 6h7" />
            </svg>
            <span>Query Console</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('history')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors flex items-center gap-2 ${
              activeTab === 'history'
                ? 'bg-indigo-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-white hover:bg-slate-800/60'
            }`}
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span>Audit History</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="p-3 bg-rose-950/60 border border-rose-800/80 rounded-xl text-xs text-rose-200 flex items-center gap-2">
          <svg className="w-4 h-4 shrink-0 text-rose-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span>{error}</span>
        </div>
      )}

      {activeTab === 'builder' ? (
        <div className="space-y-6">
          {/* Natural Language Assistant Bar */}
          <div className="bg-gradient-to-r from-indigo-950/40 via-purple-950/20 to-slate-950/60 border border-indigo-900/40 rounded-xl p-4 shadow-sm">
            <div className="flex items-center gap-2 mb-2">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-xs font-semibold text-indigo-300 uppercase tracking-wider">
                Early AI Query Assistant
              </span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-300 font-mono">
                Hosted Model Gateway
              </span>
            </div>

            <form onSubmit={handleCompileNLQ} className="flex flex-col sm:flex-row gap-2">
              <input
                type="text"
                data-testid="nlq-input"
                value={nlqPrompt}
                onChange={(e) => setNlqPrompt(e.target.value)}
                placeholder="Ask in plain language, e.g., 'Find all invoices where status is PAID' or 'Show purchase orders exceeding 10000'"
                className="flex-1 px-3 py-2 bg-slate-950/80 border border-slate-700 rounded-lg text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 font-sans"
              />
              <button
                type="submit"
                data-testid="nlq-submit-btn"
                disabled={nlqLoading || !nlqPrompt.trim()}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs font-semibold rounded-lg transition-colors flex items-center justify-center gap-2 shrink-0 shadow-md shadow-indigo-600/20"
              >
                {nlqLoading ? (
                  <>
                    <svg className="animate-spin w-3.5 h-3.5" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                    </svg>
                    <span>Compiling...</span>
                  </>
                ) : (
                  <>
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                    <span>Ask AI</span>
                  </>
                )}
              </button>
            </form>

            {/* NLQ Parsed Feedback */}
            {nlqResult && (
              <div className="mt-3 p-3 bg-slate-950/90 border border-indigo-800/50 rounded-lg text-xs space-y-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2 text-emerald-400 font-semibold">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                    <span>AI Compiled Query Successfully</span>
                  </div>
                  <div className="flex items-center gap-3 text-[11px] text-slate-400 font-mono">
                    <span>Latency: {nlqResult.latency_ms.toFixed(1)}ms</span>
                    <span>Tokens: {nlqResult.token_usage.total_tokens}</span>
                  </div>
                </div>

                <p className="text-slate-300 italic">{nlqResult.explanation}</p>

                <div className="flex gap-2 pt-1">
                  <button
                    type="button"
                    onClick={() => handleExecute(nlqResult.parsed_query)}
                    className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs rounded-md transition-colors flex items-center gap-1.5"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <span>Run AI Query Directly</span>
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Query Builder Section */}
          <div className="bg-slate-950/60 border border-slate-800 rounded-xl p-5 space-y-5">
            {/* Entity Selector */}
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <label className="text-xs font-semibold text-slate-300" htmlFor="entity-select">
                  Target Entity:
                </label>
                <select
                  id="entity-select"
                  data-testid="entity-select"
                  value={selectedEntity?.name || ''}
                  onChange={(e) => handleSelectEntity(e.target.value)}
                  className="px-3 py-1.5 bg-slate-900 border border-slate-700 rounded-lg text-xs font-medium text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  {schema?.entities.map((ent) => (
                    <option key={ent.name} value={ent.name}>
                      {ent.display_name} ({ent.name})
                    </option>
                  ))}
                </select>
              </div>

              <div className="text-xs text-slate-400 flex items-center gap-2">
                <span>Mapped Properties:</span>
                <span className="font-semibold text-indigo-400">
                  {loadingSchema ? 'Loading...' : `${mappedProps.length} of ${selectedEntity?.properties.length || 0}`}
                </span>
              </div>
            </div>

            {/* Field Selection */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-semibold text-slate-300">Projected Fields:</span>
                <span className="text-[11px] text-slate-500">
                  {selectedFields.length === 0 ? 'All mapped fields selected' : `${selectedFields.length} selected`}
                </span>
              </div>
              <div className="flex flex-wrap gap-2">
                {selectedEntity?.properties.map((prop) => {
                  const isSelected = selectedFields.includes(prop.name)
                  return (
                    <button
                      key={prop.name}
                      type="button"
                      disabled={!prop.is_mapped}
                      onClick={() => handleToggleField(prop.name)}
                      className={`px-2.5 py-1 rounded-lg text-xs font-mono transition-colors flex items-center gap-1.5 ${
                        !prop.is_mapped
                          ? 'bg-slate-900/50 text-slate-600 border border-slate-800/40 cursor-not-allowed'
                          : isSelected
                            ? 'bg-indigo-600 text-white border border-indigo-500'
                            : 'bg-slate-900 text-slate-300 border border-slate-700 hover:border-slate-500'
                      }`}
                      title={prop.is_mapped ? `Mapped to '${prop.source_column}'` : 'Unmapped property'}
                    >
                      <span>{prop.name}</span>
                      <span className="text-[10px] opacity-75">({prop.data_type})</span>
                    </button>
                  )
                })}
              </div>
            </div>

            {/* Filters Section */}
            <div className="space-y-3 pt-2 border-t border-slate-800/80">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-300">Filter Conditions (AND):</span>
                <button
                  type="button"
                  data-testid="add-filter-btn"
                  onClick={handleAddFilter}
                  disabled={!selectedEntity || mappedProps.length === 0}
                  className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 disabled:opacity-50 text-indigo-400 hover:text-indigo-300 text-xs font-semibold rounded-lg transition-colors flex items-center gap-1"
                >
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                  </svg>
                  <span>Add Filter</span>
                </button>
              </div>

              {filters.length === 0 ? (
                <div className="text-xs text-slate-500 italic py-1">No active filters (returns all records).</div>
              ) : (
                <div className="space-y-2">
                  {filters.map((filter, idx) => (
                    <div key={idx} className="flex flex-wrap items-center gap-2 bg-slate-900/80 p-2.5 rounded-lg border border-slate-800">
                      {/* Field */}
                      <select
                        value={filter.field}
                        onChange={(e) => handleUpdateFilter(idx, { field: e.target.value })}
                        className="px-2.5 py-1 bg-slate-950 border border-slate-700 rounded text-xs text-slate-200"
                      >
                        {mappedProps.map((p) => (
                          <option key={p.name} value={p.name}>
                            {p.name}
                          </option>
                        ))}
                      </select>

                      {/* Operator */}
                      <select
                        value={filter.operator}
                        onChange={(e) => handleUpdateFilter(idx, { operator: e.target.value as QueryOperator })}
                        className="px-2.5 py-1 bg-slate-950 border border-slate-700 rounded text-xs text-slate-200"
                      >
                        {Object.entries(OPERATOR_LABELS).map(([op, label]) => (
                          <option key={op} value={op}>
                            {label}
                          </option>
                        ))}
                      </select>

                      {/* Value */}
                      {!['is_null', 'is_not_null'].includes(filter.operator) && (
                        <input
                          type="text"
                          value={String(filter.value ?? '')}
                          onChange={(e) => handleUpdateFilter(idx, { value: e.target.value })}
                          placeholder="Operand value"
                          className="flex-1 min-w-[120px] px-2.5 py-1 bg-slate-950 border border-slate-700 rounded text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                        />
                      )}

                      {/* Delete */}
                      <button
                        type="button"
                        onClick={() => handleRemoveFilter(idx)}
                        className="p-1 text-slate-400 hover:text-rose-400 transition-colors"
                        title="Remove condition"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Sorting Section */}
            <div className="space-y-3 pt-2 border-t border-slate-800/80">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-300">Ordering (ORDER BY):</span>
                <button
                  type="button"
                  onClick={handleAddSort}
                  disabled={!selectedEntity || mappedProps.length === 0}
                  className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 disabled:opacity-50 text-indigo-400 hover:text-indigo-300 text-xs font-semibold rounded-lg transition-colors flex items-center gap-1"
                >
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                  </svg>
                  <span>Add Sort</span>
                </button>
              </div>

              {sorts.length === 0 ? (
                <div className="text-xs text-slate-500 italic py-1">Default table order.</div>
              ) : (
                <div className="space-y-2">
                  {sorts.map((sort, idx) => (
                    <div key={idx} className="flex items-center gap-2 bg-slate-900/80 p-2.5 rounded-lg border border-slate-800">
                      <select
                        value={sort.field}
                        onChange={(e) => handleUpdateSort(idx, { field: e.target.value })}
                        className="px-2.5 py-1 bg-slate-950 border border-slate-700 rounded text-xs text-slate-200"
                      >
                        {mappedProps.map((p) => (
                          <option key={p.name} value={p.name}>
                            {p.name}
                          </option>
                        ))}
                      </select>

                      <select
                        value={sort.direction}
                        onChange={(e) => handleUpdateSort(idx, { direction: e.target.value as SortDirection })}
                        className="px-2.5 py-1 bg-slate-950 border border-slate-700 rounded text-xs text-slate-200"
                      >
                        <option value="asc">Ascending (ASC)</option>
                        <option value="desc">Descending (DESC)</option>
                      </select>

                      <button
                        type="button"
                        onClick={() => handleRemoveSort(idx)}
                        className="p-1 text-slate-400 hover:text-rose-400 transition-colors"
                        title="Remove sort"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Pagination & Execution Bar */}
            <div className="flex flex-wrap items-center justify-between gap-4 pt-4 border-t border-slate-800">
              <div className="flex items-center gap-4 text-xs text-slate-300">
                <div className="flex items-center gap-2">
                  <label htmlFor="limit-input">Limit:</label>
                  <input
                    id="limit-input"
                    type="number"
                    min={1}
                    max={500}
                    value={limit}
                    onChange={(e) => setLimit(Math.max(1, Math.min(500, Number(e.target.value))))}
                    className="w-16 px-2 py-1 bg-slate-950 border border-slate-700 rounded text-xs text-center text-slate-200"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <label htmlFor="offset-input">Offset:</label>
                  <input
                    id="offset-input"
                    type="number"
                    min={0}
                    value={offset}
                    onChange={(e) => setOffset(Math.max(0, Number(e.target.value)))}
                    className="w-16 px-2 py-1 bg-slate-950 border border-slate-700 rounded text-xs text-center text-slate-200"
                  />
                </div>
              </div>

              <button
                type="button"
                data-testid="execute-query-btn"
                onClick={() => handleExecute()}
                disabled={executing || !selectedEntity || mappedProps.length === 0}
                className="px-5 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-semibold text-xs rounded-lg transition-colors flex items-center gap-2 shadow-lg shadow-indigo-600/20"
              >
                {executing ? (
                  <>
                    <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                    </svg>
                    <span>Executing Sandbox Query...</span>
                  </>
                ) : (
                  <>
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <span>Execute Query</span>
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Results Section */}
          {queryResult && (
            <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-5 space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-slate-800">
                <div className="flex items-center gap-3">
                  <span className="text-sm font-bold text-white">Results</span>
                  <span className="text-xs font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                    {queryResult.rows.length} rows returned ({queryResult.total_count} total matched)
                  </span>
                  <span className="text-xs font-mono text-slate-400">
                    {queryResult.execution_time_ms.toFixed(1)}ms
                  </span>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setQueryPlanOpen((prev) => !prev)}
                    className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold rounded-lg transition-colors flex items-center gap-1.5"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                    </svg>
                    <span>{queryPlanOpen ? 'Hide Query Plan' : 'View Query Plan'}</span>
                  </button>

                  <button
                    type="button"
                    data-testid="export-csv-btn"
                    onClick={handleExportCSV}
                    className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold rounded-lg transition-colors flex items-center gap-1.5"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                    </svg>
                    <span>Export CSV</span>
                  </button>
                </div>
              </div>

              {/* Collapsible Query Plan & Parameterized SQL */}
              {queryPlanOpen && (
                <div className="p-4 bg-slate-900 rounded-lg border border-slate-800 space-y-3">
                  <div>
                    <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block mb-1">
                      Compiled Parameterized SQL (Read-Only Sandbox):
                    </span>
                    <pre className="p-2.5 bg-slate-950 rounded text-xs font-mono text-indigo-300 overflow-x-auto whitespace-pre-wrap">
                      {queryResult.compiled_sql}
                    </pre>
                  </div>

                  <div>
                    <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block mb-1">
                      Parameters:
                    </span>
                    <code className="p-1.5 bg-slate-950 rounded text-xs font-mono text-emerald-400 block overflow-x-auto">
                      {JSON.stringify(queryResult.parameters)}
                    </code>
                  </div>

                  <div>
                    <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block mb-1">
                      EXPLAIN Execution Steps:
                    </span>
                    <ul className="list-disc list-inside text-xs font-mono text-slate-400 space-y-0.5">
                      {queryResult.query_plan.map((step, idx) => (
                        <li key={idx}>{step}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}

              {/* Results Table */}
              {queryResult.rows.length === 0 ? (
                <div className="text-center py-8 text-xs text-slate-400">
                  No records matched the filter criteria in confirmed datasets.
                </div>
              ) : (
                <div className="overflow-x-auto rounded-lg border border-slate-800">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead className="bg-slate-900 border-b border-slate-800 text-slate-300 font-semibold font-mono">
                      <tr>
                        {queryResult.columns.map((col) => (
                          <th key={col} className="px-3 py-2.5">
                            {col}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60 font-sans">
                      {queryResult.rows.map((row, rIdx) => (
                        <tr key={rIdx} className="hover:bg-slate-900/50 transition-colors">
                          {queryResult.columns.map((col) => {
                            const val = row[col]
                            return (
                              <td key={col} className="px-3 py-2 text-slate-200 font-mono text-[11px]">
                                {val === null || val === undefined ? (
                                  <span className="text-slate-600 italic">null</span>
                                ) : (
                                  String(val)
                                )}
                              </td>
                            )
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      ) : (
        /* Audit History Tab */
        <div className="bg-slate-950/60 border border-slate-800 rounded-xl p-5 space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-slate-800">
            <h4 className="text-sm font-bold text-white">Project Query Audit Log</h4>
            <span className="text-xs text-slate-400">Deterministic immutable PostgreSQL audit</span>
          </div>

          {historyLoading ? (
            <div className="text-center py-8 text-xs text-slate-400">Loading audit history...</div>
          ) : history.length === 0 ? (
            <div className="text-center py-8 text-xs text-slate-500">
              No query executions recorded yet for this project.
            </div>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-slate-800">
              <table className="w-full text-left text-xs border-collapse">
                <thead className="bg-slate-900 border-b border-slate-800 text-slate-300 font-semibold font-mono">
                  <tr>
                    <th className="px-3 py-2">Timestamp</th>
                    <th className="px-3 py-2">Entity</th>
                    <th className="px-3 py-2">Mode</th>
                    <th className="px-3 py-2">Rows</th>
                    <th className="px-3 py-2">Latency</th>
                    <th className="px-3 py-2">Compiled SQL</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-sans">
                  {history.map((item) => (
                    <tr key={item.id} className="hover:bg-slate-900/50 transition-colors">
                      <td className="px-3 py-2 text-slate-400 font-mono text-[11px] whitespace-nowrap">
                        {new Date(item.created_at).toLocaleString()}
                      </td>
                      <td className="px-3 py-2 text-slate-200 font-semibold">{item.entity_name}</td>
                      <td className="px-3 py-2">
                        {item.is_nlq ? (
                          <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-purple-500/10 text-purple-400 border border-purple-500/20">
                            AI NLQ
                          </span>
                        ) : (
                          <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-slate-800 text-slate-300">
                            Structured
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-slate-200 font-mono">{item.row_count}</td>
                      <td className="px-3 py-2 text-slate-400 font-mono">{item.execution_time_ms}ms</td>
                      <td className="px-3 py-2 text-indigo-300 font-mono text-[10px] max-w-xs truncate" title={item.compiled_sql}>
                        {item.compiled_sql}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
