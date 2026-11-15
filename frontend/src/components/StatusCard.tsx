import React from 'react'
import { Database, Server, RefreshCw, CheckCircle2, XCircle, Clock } from 'lucide-react'
import type { SystemHealthResponse } from '../types/api'

interface StatusCardProps {
  health: SystemHealthResponse | null
  loading: boolean
  onRefresh: () => void
}

export const StatusCard: React.FC<StatusCardProps> = ({ health, loading, onRefresh }) => {
  const isHealthy = health?.status === 'healthy'
  const isDbConnected = health?.database.status === 'connected'

  return (
    <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-xl backdrop-blur-sm">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-semibold text-white flex items-center gap-2">
            <Server className="w-5 h-5 text-indigo-400" />
            Infrastructure Health Status
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Real-time telemetry and database ping from <code className="text-slate-300">/api/v1/health</code>
          </p>
        </div>
        <button
          onClick={onRefresh}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium border border-slate-700 transition disabled:opacity-50 cursor-pointer"
          title="Refresh health status"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Backend API Service Box */}
        <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-4 flex flex-col justify-between">
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center">
                <Server className="w-4 h-4 text-indigo-400" />
              </div>
              <div>
                <h3 className="text-sm font-medium text-slate-200">FastAPI Backend</h3>
                <p className="text-xs text-slate-400">REST API Gateway & App Engine</p>
              </div>
            </div>
            {isHealthy ? (
              <span className="flex items-center gap-1 text-xs font-medium text-emerald-400">
                <CheckCircle2 className="w-4 h-4" /> Operational
              </span>
            ) : (
              <span className="flex items-center gap-1 text-xs font-medium text-rose-400">
                <XCircle className="w-4 h-4" /> Unreachable
              </span>
            )}
          </div>

          <div className="mt-4 pt-3 border-t border-slate-900 grid grid-cols-2 gap-2 text-xs">
            <div>
              <span className="text-slate-500 block">Version</span>
              <span className="font-mono text-slate-300">{health?.version ?? 'N/A'}</span>
            </div>
            <div>
              <span className="text-slate-500 block">Environment</span>
              <span className="font-mono text-slate-300 capitalize">{health?.environment ?? 'N/A'}</span>
            </div>
          </div>
        </div>

        {/* PostgreSQL Database Box */}
        <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-4 flex flex-col justify-between">
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-sky-500/10 border border-sky-500/20 flex items-center justify-center">
                <Database className="w-4 h-4 text-sky-400" />
              </div>
              <div>
                <h3 className="text-sm font-medium text-slate-200">PostgreSQL 16+</h3>
                <p className="text-xs text-slate-400">Relational Store & Migrations</p>
              </div>
            </div>
            {isDbConnected ? (
              <span className="flex items-center gap-1 text-xs font-medium text-emerald-400">
                <CheckCircle2 className="w-4 h-4" /> Connected
              </span>
            ) : (
              <span className="flex items-center gap-1 text-xs font-medium text-rose-400">
                <XCircle className="w-4 h-4" /> Disconnected
              </span>
            )}
          </div>

          <div className="mt-4 pt-3 border-t border-slate-900 grid grid-cols-2 gap-2 text-xs">
            <div>
              <span className="text-slate-500 block">Ping Latency</span>
              <span className="font-mono text-slate-300 flex items-center gap-1">
                <Clock className="w-3 h-3 text-slate-400" />
                {health?.database.latency_ms !== null && health?.database.latency_ms !== undefined
                  ? `${health.database.latency_ms} ms`
                  : 'N/A'}
              </span>
            </div>
            <div>
              <span className="text-slate-500 block">Status Details</span>
              <span className="text-slate-300 truncate block" title={health?.database.details ?? ''}>
                {health?.database.details ?? 'Awaiting check'}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
