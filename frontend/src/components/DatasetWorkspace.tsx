import { useState, useEffect, useCallback, type FormEvent } from 'react'
import { useAuth } from '../context/AuthContext'
import {
  listProjectDatasets,
  uploadDataset,
  getDatasetPreview,
  deleteDataset,
} from '../services/datasets'
import type { Dataset, DatasetPreview, ColumnProfile } from '../types/dataset'
import type { Project } from '../types/auth'
import { AuthApiError } from '../services/auth'

interface DatasetWorkspaceProps {
  project: Project
  onBack: () => void
}

export function DatasetWorkspace({ project, onBack }: DatasetWorkspaceProps) {
  const { token, activeOrg } = useAuth()
  const [datasets, setDatasets] = useState<Dataset[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Inspection state
  const [selectedDataset, setSelectedDataset] = useState<Dataset | null>(null)
  const [activeTab, setActiveTab] = useState<'schema' | 'profiling' | 'preview'>('schema')
  const [preview, setPreview] = useState<DatasetPreview | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)

  // Upload modal state
  const [showUploadModal, setShowUploadModal] = useState(false)
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [uploadName, setUploadName] = useState('')
  const [uploadDesc, setUploadDesc] = useState('')
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)

  const loadDatasets = useCallback(async () => {
    if (!token || !activeOrg) return
    setLoading(true)
    setError(null)
    try {
      const data = await listProjectDatasets(token, activeOrg.id, project.id)
      setDatasets(data)
    } catch (err: unknown) {
      if (err instanceof AuthApiError) {
        setError(err.message)
      } else {
        setError('Failed to load datasets')
      }
    } finally {
      setLoading(false)
    }
  }, [token, activeOrg?.id, project.id])

  useEffect(() => {
    loadDatasets()
  }, [loadDatasets])

  // Load preview data when entering preview tab
  useEffect(() => {
    if (!token || !activeOrg || !selectedDataset || activeTab !== 'preview') return
    let isMounted = true
    setPreviewLoading(true)
    getDatasetPreview(token, activeOrg.id, project.id, selectedDataset.id, 20)
      .then((data) => {
        if (isMounted) setPreview(data)
      })
      .catch((err) => {
        if (isMounted) console.error('Failed to load preview:', err)
      })
      .finally(() => {
        if (isMounted) setPreviewLoading(false)
      })
    return () => {
      isMounted = false
    }
  }, [token, activeOrg?.id, project.id, selectedDataset?.id, activeTab])

  const handleUpload = async (e: FormEvent) => {
    e.preventDefault()
    if (!token || !activeOrg || !uploadFile) return
    setUploading(true)
    setUploadError(null)

    try {
      const newDataset = await uploadDataset(
        token,
        activeOrg.id,
        project.id,
        uploadFile,
        uploadName.trim() || undefined,
        uploadDesc.trim() || undefined
      )
      setShowUploadModal(false)
      setUploadFile(null)
      setUploadName('')
      setUploadDesc('')
      await loadDatasets()
      setSelectedDataset(newDataset)
      setActiveTab('profiling')
    } catch (err: unknown) {
      if (err instanceof AuthApiError) {
        setUploadError(err.message)
      } else {
        setUploadError('Failed to upload and profile dataset')
      }
    } finally {
      setUploading(false)
    }
  }

  const handleDelete = async (datasetId: string, name: string) => {
    if (!token || !activeOrg) return
    if (!window.confirm(`Delete dataset "${name}"? This removes all historical versions and storage files.`)) {
      return
    }
    try {
      await deleteDataset(token, activeOrg.id, project.id, datasetId)
      if (selectedDataset?.id === datasetId) {
        setSelectedDataset(null)
      }
      await loadDatasets()
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Failed to delete dataset')
    }
  }

  const formatBytes = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / 1048576).toFixed(2)} MB`
  }

  const renderTypeBadge = (type: string) => {
    let color = 'bg-slate-800 text-slate-300 border-slate-700'
    if (type === 'INTEGER' || type === 'FLOAT') {
      color = 'bg-blue-500/10 text-blue-400 border-blue-500/20'
    } else if (type === 'DATETIME' || type === 'DATE') {
      color = 'bg-purple-500/10 text-purple-400 border-purple-500/20'
    } else if (type === 'BOOLEAN') {
      color = 'bg-amber-500/10 text-amber-400 border-amber-500/20'
    } else if (type === 'STRING') {
      color = 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
    }
    return (
      <span className={`text-[10px] font-mono font-semibold px-2 py-0.5 rounded border ${color}`}>
        {type}
      </span>
    )
  }

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-6">
      {/* Workspace Sub-Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <div className="flex items-center gap-3">
            <button
              onClick={onBack}
              className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors flex items-center gap-1 text-xs"
              title="Back to Projects"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
              <span>Projects</span>
            </button>
            <span className="text-slate-600">/</span>
            <h3 className="text-lg font-bold text-white">{project.name}</h3>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
              Data Intelligence
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Ingest tabular P2P datasets, discover column schemas, and inspect deterministic data quality profiles.
          </p>
        </div>

        <button
          onClick={() => setShowUploadModal(true)}
          className="inline-flex items-center gap-2 px-3.5 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold rounded-lg transition-colors shadow-lg shadow-indigo-600/20 shrink-0"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
          </svg>
          <span>Upload Dataset</span>
        </button>
      </div>

      {error && (
        <div className="p-3 bg-rose-950/60 border border-rose-800/80 rounded-lg text-rose-200 text-xs">
          {error}
        </div>
      )}

      {/* Dataset Selection Detail or List */}
      {selectedDataset ? (
        <div className="space-y-6">
          {/* Detail Overview Banner */}
          <div className="p-5 rounded-xl bg-slate-950/60 border border-slate-800 space-y-4">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <div className="flex items-center gap-3">
                  <h4 className="text-xl font-bold text-white">{selectedDataset.name}</h4>
                  <span className="text-xs px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 font-mono">
                    v{selectedDataset.latest_version?.version_number ?? 1}
                  </span>
                  <span className="text-xs px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-mono">
                    {selectedDataset.status}
                  </span>
                </div>
                <p className="text-xs text-slate-400 mt-1">
                  {selectedDataset.description || 'No description provided.'}
                </p>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => setSelectedDataset(null)}
                  className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium rounded-lg transition-colors"
                >
                  Close Inspection
                </button>
              </div>
            </div>

            {/* Snapshot Metrics Bar */}
            <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-6 gap-3 pt-3 border-t border-slate-800/80 text-xs">
              <div className="p-2.5 rounded-lg bg-slate-900 border border-slate-800/60">
                <span className="text-slate-500 block text-[10px]">Total Records</span>
                <span className="font-bold text-slate-200 text-sm">
                  {selectedDataset.latest_version?.record_count?.toLocaleString() ?? '—'}
                </span>
              </div>
              <div className="p-2.5 rounded-lg bg-slate-900 border border-slate-800/60">
                <span className="text-slate-500 block text-[10px]">Columns</span>
                <span className="font-bold text-slate-200 text-sm">
                  {selectedDataset.latest_version?.column_count ?? '—'}
                </span>
              </div>
              <div className="p-2.5 rounded-lg bg-slate-900 border border-slate-800/60">
                <span className="text-slate-500 block text-[10px]">Format</span>
                <span className="font-mono font-semibold text-indigo-400 text-sm">
                  {selectedDataset.latest_version?.file_format ?? '—'}
                </span>
              </div>
              <div className="p-2.5 rounded-lg bg-slate-900 border border-slate-800/60">
                <span className="text-slate-500 block text-[10px]">File Size</span>
                <span className="font-semibold text-slate-200 text-sm">
                  {selectedDataset.latest_version
                    ? formatBytes(selectedDataset.latest_version.file_size_bytes)
                    : '—'}
                </span>
              </div>
              <div className="p-2.5 rounded-lg bg-slate-900 border border-slate-800/60 col-span-2">
                <span className="text-slate-500 block text-[10px]">SHA-256 Checksum</span>
                <span className="font-mono text-[11px] text-slate-300 truncate block" title={selectedDataset.latest_version?.checksum_hash}>
                  {selectedDataset.latest_version?.checksum_hash ?? '—'}
                </span>
              </div>
            </div>
          </div>

          {/* Inspection Tabs */}
          <div className="flex border-b border-slate-800 space-x-6 text-xs">
            <button
              onClick={() => setActiveTab('schema')}
              className={`pb-3 font-semibold transition-colors flex items-center gap-1.5 ${
                activeTab === 'schema'
                  ? 'border-b-2 border-indigo-500 text-indigo-400'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <span>Discovered Schema</span>
              <span className="px-1.5 py-0.2 rounded-full bg-slate-800 text-[10px]">
                {selectedDataset.latest_version?.column_count ?? 0}
              </span>
            </button>
            <button
              onClick={() => setActiveTab('profiling')}
              className={`pb-3 font-semibold transition-colors flex items-center gap-1.5 ${
                activeTab === 'profiling'
                  ? 'border-b-2 border-indigo-500 text-indigo-400'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <span>Data Profiling Metrics</span>
              {selectedDataset.latest_version?.profiling_summary?.dataset_quality_warnings.length ? (
                <span className="w-2 h-2 rounded-full bg-amber-400" />
              ) : null}
            </button>
            <button
              onClick={() => setActiveTab('preview')}
              className={`pb-3 font-semibold transition-colors ${
                activeTab === 'preview'
                  ? 'border-b-2 border-indigo-500 text-indigo-400'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <span>Raw Preview (First 20)</span>
            </button>
          </div>

          {/* Tab 1: Schema View */}
          {activeTab === 'schema' && (
            <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/40">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-900/80 text-slate-400 uppercase tracking-wider text-[10px] border-b border-slate-800">
                  <tr>
                    <th className="px-4 py-3 font-semibold">#</th>
                    <th className="px-4 py-3 font-semibold">Column Name</th>
                    <th className="px-4 py-3 font-semibold">Detected Type</th>
                    <th className="px-4 py-3 font-semibold">Nullable</th>
                    <th className="px-4 py-3 font-semibold">Sample Non-Null Values</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-mono">
                  {selectedDataset.latest_version?.schema_metadata?.map((col, idx) => (
                    <tr key={col.name} className="hover:bg-slate-900/40 transition-colors">
                      <td className="px-4 py-3 text-slate-500 text-[11px]">{idx + 1}</td>
                      <td className="px-4 py-3 font-bold text-white text-[12px]">{col.name}</td>
                      <td className="px-4 py-3">{renderTypeBadge(col.data_type)}</td>
                      <td className="px-4 py-3">
                        <span
                          className={`px-1.5 py-0.5 rounded text-[10px] ${
                            col.nullable ? 'bg-amber-500/10 text-amber-400' : 'bg-emerald-500/10 text-emerald-400'
                          }`}
                        >
                          {col.nullable ? 'YES' : 'NO'}
                        </span>
                      </td>
                      <td className="px-4 py-3 font-sans">
                        <div className="flex flex-wrap gap-1.5">
                          {col.sample_values.slice(0, 4).map((s, sIdx) => (
                            <span
                              key={sIdx}
                              className="text-[11px] bg-slate-800 px-2 py-0.5 rounded text-slate-300 border border-slate-700/60"
                            >
                              {String(s)}
                            </span>
                          ))}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Tab 2: Profiling Dashboard */}
          {activeTab === 'profiling' && (
            <div className="space-y-6">
              {/* Quality Warnings Banner (if any) */}
              {selectedDataset.latest_version?.profiling_summary?.dataset_quality_warnings.length ? (
                <div className="p-4 bg-amber-950/40 border border-amber-800/60 rounded-xl space-y-2">
                  <div className="flex items-center gap-2 text-amber-400 font-bold text-xs">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                    <span>Deterministic Data Quality Alerts</span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {selectedDataset.latest_version.profiling_summary.dataset_quality_warnings.map((w, wIdx) => (
                      <span
                        key={wIdx}
                        className="text-[11px] px-2.5 py-1 rounded-lg bg-amber-900/40 text-amber-200 border border-amber-800/80 font-mono"
                      >
                        {w}
                      </span>
                    ))}
                  </div>
                </div>
              ) : null}

              {/* Column Profiling Cards Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {selectedDataset.latest_version?.profiling_summary?.columns.map((col: ColumnProfile) => (
                  <div
                    key={col.column_name}
                    className="p-4 rounded-xl bg-slate-950/60 border border-slate-800/80 hover:border-slate-700/80 transition-colors space-y-4"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <h5 className="font-bold text-white text-sm">{col.column_name}</h5>
                        <div className="flex items-center gap-2 mt-1">
                          {renderTypeBadge(col.detected_type)}
                          <span className="text-[10px] text-slate-500 font-mono">
                            {col.distinct_count.toLocaleString()} distinct ({col.unique_percentage}%)
                          </span>
                        </div>
                      </div>

                      {col.quality_warnings.length > 0 && (
                        <span className="px-2 py-0.5 text-[9px] font-bold rounded bg-amber-500/20 text-amber-300 border border-amber-500/30">
                          {col.quality_warnings.length} alert{col.quality_warnings.length > 1 ? 's' : ''}
                        </span>
                      )}
                    </div>

                    {/* Missing Values Bar */}
                    <div className="space-y-1">
                      <div className="flex justify-between text-[11px] text-slate-400">
                        <span>Missing / Nulls</span>
                        <span className="font-mono text-slate-200">
                          {col.null_count.toLocaleString()} ({col.null_percentage}%)
                        </span>
                      </div>
                      <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden flex">
                        <div
                          className="bg-indigo-500 h-full"
                          style={{ width: `${100 - col.null_percentage}%` }}
                        />
                        <div
                          className="bg-rose-500 h-full"
                          style={{ width: `${col.null_percentage}%` }}
                        />
                      </div>
                    </div>

                    {/* Specific Metrics by Type */}
                    {col.numeric_stats && (
                      <div className="grid grid-cols-4 gap-2 pt-2 border-t border-slate-800/60 text-xs">
                        <div className="bg-slate-900/60 p-2 rounded">
                          <span className="text-[10px] text-slate-500 block">Min</span>
                          <span className="font-mono font-semibold text-slate-200">
                            {col.numeric_stats.min}
                          </span>
                        </div>
                        <div className="bg-slate-900/60 p-2 rounded">
                          <span className="text-[10px] text-slate-500 block">Max</span>
                          <span className="font-mono font-semibold text-slate-200">
                            {col.numeric_stats.max}
                          </span>
                        </div>
                        <div className="bg-slate-900/60 p-2 rounded">
                          <span className="text-[10px] text-slate-500 block">Mean</span>
                          <span className="font-mono font-semibold text-slate-200">
                            {col.numeric_stats.mean}
                          </span>
                        </div>
                        <div className="bg-slate-900/60 p-2 rounded">
                          <span className="text-[10px] text-slate-500 block">Sum</span>
                          <span className="font-mono font-semibold text-slate-200">
                            {col.numeric_stats.sum}
                          </span>
                        </div>
                        <div className="bg-slate-900/60 p-2 rounded">
                          <span className="text-[10px] text-slate-500 block">Std Dev</span>
                          <span className="font-mono text-slate-300">
                            {col.numeric_stats.stddev ?? '—'}
                          </span>
                        </div>
                        <div className="bg-slate-900/60 p-2 rounded">
                          <span className="text-[10px] text-slate-500 block">Median</span>
                          <span className="font-mono text-slate-300">
                            {col.numeric_stats.median ?? '—'}
                          </span>
                        </div>
                        <div className="bg-slate-900/60 p-2 rounded col-span-2">
                          <span className="text-[10px] text-slate-500 block">Zeros</span>
                          <span className="font-mono text-slate-300">
                            {col.numeric_stats.zeros_count}
                          </span>
                        </div>
                      </div>
                    )}

                    {col.datetime_stats && (
                      <div className="grid grid-cols-2 gap-2 pt-2 border-t border-slate-800/60 text-xs">
                        <div className="bg-slate-900/60 p-2 rounded">
                          <span className="text-[10px] text-slate-500 block">Earliest</span>
                          <span className="font-mono text-slate-200 text-[11px]">
                            {col.datetime_stats.earliest?.split('T')[0] ?? '—'}
                          </span>
                        </div>
                        <div className="bg-slate-900/60 p-2 rounded">
                          <span className="text-[10px] text-slate-500 block">Latest</span>
                          <span className="font-mono text-slate-200 text-[11px]">
                            {col.datetime_stats.latest?.split('T')[0] ?? '—'}
                          </span>
                        </div>
                        <div className="bg-slate-900/60 p-2 rounded col-span-2">
                          <span className="text-[10px] text-slate-500 block">Span (Days)</span>
                          <span className="font-mono text-slate-300">
                            {col.datetime_stats.range_days ?? '—'} days
                          </span>
                        </div>
                      </div>
                    )}

                    {col.string_stats && !col.numeric_stats && !col.datetime_stats && (
                      <div className="grid grid-cols-3 gap-2 pt-2 border-t border-slate-800/60 text-xs">
                        <div className="bg-slate-900/60 p-2 rounded">
                          <span className="text-[10px] text-slate-500 block">Min Len</span>
                          <span className="font-mono text-slate-300">{col.string_stats.min_length}</span>
                        </div>
                        <div className="bg-slate-900/60 p-2 rounded">
                          <span className="text-[10px] text-slate-500 block">Max Len</span>
                          <span className="font-mono text-slate-300">{col.string_stats.max_length}</span>
                        </div>
                        <div className="bg-slate-900/60 p-2 rounded">
                          <span className="text-[10px] text-slate-500 block">Avg Len</span>
                          <span className="font-mono text-slate-300">{col.string_stats.avg_length}</span>
                        </div>
                      </div>
                    )}

                    {/* Column Warnings */}
                    {col.quality_warnings.length > 0 && (
                      <div className="flex flex-wrap gap-1 pt-1">
                        {col.quality_warnings.map((w, i) => (
                          <span
                            key={i}
                            className="text-[10px] px-2 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/20 font-mono"
                          >
                            {w}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Tab 3: Data Preview */}
          {activeTab === 'preview' && (
            <div className="space-y-2">
              {previewLoading ? (
                <div className="py-12 text-center text-xs text-slate-500 flex items-center justify-center gap-2">
                  <svg className="w-4 h-4 animate-spin text-indigo-400" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                  </svg>
                  <span>Loading dataset preview...</span>
                </div>
              ) : preview && preview.rows.length > 0 ? (
                <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/40">
                  <table className="w-full text-left text-xs font-mono">
                    <thead className="bg-slate-900/80 text-slate-400 uppercase tracking-wider text-[10px] border-b border-slate-800 sticky top-0">
                      <tr>
                        <th className="px-3 py-2.5 font-semibold">#</th>
                        {preview.columns.map((col) => (
                          <th key={col} className="px-3 py-2.5 font-semibold text-slate-200">
                            {col}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60">
                      {preview.rows.map((row, rIdx) => (
                        <tr key={rIdx} className="hover:bg-slate-900/40 transition-colors">
                          <td className="px-3 py-2 text-slate-500 text-[11px]">{rIdx + 1}</td>
                          {preview.columns.map((col) => (
                            <td key={col} className="px-3 py-2 text-slate-300 text-[11px] truncate max-w-xs">
                              {row[col] !== null && row[col] !== undefined ? String(row[col]) : (
                                <span className="text-slate-600 italic">null</span>
                              )}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="p-8 text-center text-xs text-slate-500">
                  No preview rows available.
                </div>
              )}
            </div>
          )}
        </div>
      ) : (
        /* Datasets List Table */
        <div className="space-y-4">
          {loading ? (
            <div className="py-12 text-center text-xs text-slate-500 flex items-center justify-center gap-2">
              <svg className="w-4 h-4 animate-spin text-indigo-400" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
              </svg>
              <span>Loading project datasets...</span>
            </div>
          ) : datasets.length === 0 ? (
            <div className="py-12 text-center text-slate-400 space-y-3 bg-slate-950/40 rounded-xl border border-slate-800/80 p-8">
              <div className="w-12 h-12 mx-auto rounded-full bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              </div>
              <div>
                <h4 className="text-sm font-bold text-white">No Datasets Ingested Yet</h4>
                <p className="text-xs text-slate-500 max-w-sm mx-auto mt-1">
                  Upload baseline P2P datasets (suppliers, purchase orders, goods receipts, or invoices) in CSV, JSON, or Excel format.
                </p>
              </div>
              <button
                onClick={() => setShowUploadModal(true)}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold rounded-lg transition-colors shadow-lg shadow-indigo-600/20"
              >
                Upload First Dataset
              </button>
            </div>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/40">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-900/80 text-slate-400 uppercase tracking-wider text-[10px] border-b border-slate-800">
                  <tr>
                    <th className="px-4 py-3 font-semibold">Dataset Name</th>
                    <th className="px-4 py-3 font-semibold">Format</th>
                    <th className="px-4 py-3 font-semibold">Version</th>
                    <th className="px-4 py-3 font-semibold">Rows</th>
                    <th className="px-4 py-3 font-semibold">Columns</th>
                    <th className="px-4 py-3 font-semibold">Status</th>
                    <th className="px-4 py-3 font-semibold text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {datasets.map((d) => (
                    <tr key={d.id} className="hover:bg-slate-900/40 transition-colors">
                      <td className="px-4 py-3">
                        <button
                          onClick={() => {
                            setSelectedDataset(d)
                            setActiveTab('schema')
                          }}
                          className="font-bold text-white hover:text-indigo-400 text-left transition-colors"
                        >
                          {d.name}
                        </button>
                        {d.description && (
                          <span className="block text-[11px] text-slate-500 truncate max-w-xs mt-0.5">
                            {d.description}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 font-mono text-indigo-400 text-[11px]">
                        {d.latest_version?.file_format ?? '—'}
                      </td>
                      <td className="px-4 py-3 font-mono text-slate-400">
                        v{d.latest_version?.version_number ?? 1}
                      </td>
                      <td className="px-4 py-3 font-mono text-slate-200">
                        {d.latest_version?.record_count?.toLocaleString() ?? '—'}
                      </td>
                      <td className="px-4 py-3 font-mono text-slate-200">
                        {d.latest_version?.column_count ?? '—'}
                      </td>
                      <td className="px-4 py-3">
                        <span className="px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                          {d.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right space-x-2">
                        <button
                          onClick={() => {
                            setSelectedDataset(d)
                            setActiveTab('profiling')
                          }}
                          className="px-2.5 py-1 bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-300 rounded text-[11px] font-medium transition-colors"
                        >
                          Inspect Profile
                        </button>
                        <button
                          onClick={() => handleDelete(d.id, d.name)}
                          className="px-2.5 py-1 bg-rose-600/10 hover:bg-rose-600/20 text-rose-400 rounded text-[11px] font-medium transition-colors"
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Upload Dataset Modal */}
      {showUploadModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
          <div className="relative w-full max-w-lg bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl p-6 text-slate-100">
            <button
              onClick={() => setShowUploadModal(false)}
              className="absolute top-4 right-4 text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors"
              aria-label="Close"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>

            <h3 className="text-xl font-bold text-white mb-1">Upload & Profile Dataset</h3>
            <p className="text-xs text-slate-400 mb-4">
              Upload a CSV, JSON, or Excel dataset into <span className="font-semibold text-slate-200">{project.name}</span>. Column schema and deterministic statistical profiles are generated automatically.
            </p>

            {uploadError && (
              <div className="mb-4 p-3 bg-rose-950/60 border border-rose-800/80 rounded-lg text-rose-200 text-xs">
                {uploadError}
              </div>
            )}

            <form onSubmit={handleUpload} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1" htmlFor="dataset-file">
                  Select Tabular File (.csv, .json, .jsonl, .xlsx)
                </label>
                <input
                  id="dataset-file"
                  type="file"
                  required
                  accept=".csv,.json,.jsonl,.xlsx"
                  onChange={(e) => {
                    const f = e.target.files?.[0] || null
                    setUploadFile(f)
                    if (f && !uploadName) {
                      setUploadName(f.name.replace(/\.[^/.]+$/, ''))
                    }
                  }}
                  className="w-full text-xs text-slate-300 file:mr-3 file:py-2 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-slate-800 file:text-indigo-400 hover:file:bg-slate-700 cursor-pointer"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1" htmlFor="dataset-name">
                  Dataset Name (Optional)
                </label>
                <input
                  id="dataset-name"
                  type="text"
                  value={uploadName}
                  onChange={(e) => setUploadName(e.target.value)}
                  placeholder="e.g. suppliers, purchase_orders, invoices"
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1" htmlFor="dataset-description">
                  Description (Optional)
                </label>
                <textarea
                  id="dataset-description"
                  rows={2}
                  value={uploadDesc}
                  onChange={(e) => setUploadDesc(e.target.value)}
                  placeholder="Source vendor records or operational transaction dataset."
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <div className="flex gap-3 justify-end pt-2">
                <button
                  type="button"
                  onClick={() => setShowUploadModal(false)}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 font-semibold text-xs rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={uploading || !uploadFile}
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-semibold text-xs rounded-lg transition-colors flex items-center gap-2"
                >
                  {uploading && (
                    <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                    </svg>
                  )}
                  <span>{uploading ? 'Profiling Dataset...' : 'Upload & Profile'}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
